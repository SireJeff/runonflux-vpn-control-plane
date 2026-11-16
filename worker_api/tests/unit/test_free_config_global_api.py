"""Unit tests for the superadmin global free-config API (Task 9).

Proves four behaviors:
  1. GET response exposes `has_token` and NEVER the token blob.
  2. PUT /global/token validates via getMe (validate_bot_token) -> 200 + username.
  3. Invalid token (validate_bot_token raises) -> 400.
  4. POST /channels (global, admin_id=None) ok + appears in GET list.

Auth: `require_super_admin` (a RoleChecker(["super_admin"]) instance) is
overridden via app.dependency_overrides so no JWT is minted; it returns
{"id": 1, "role": "super_admin"}.

Telegram: validate_bot_token / resolve_channel are patched in their source
module (app.services.free_config.membership_verifier) so no live Telegram
call happens.
"""

import pytest

from app.core.auth.role_dependencies import require_super_admin
from app.core.crypto import encrypt_token
from app.models.free_config_global import FreeConfigGlobal


@pytest.fixture
def super_client(client, app):
    """TestClient with require_super_admin overridden to a fake super admin."""
    def _fake_super():
        return {"id": 1, "role": "super_admin"}

    app.dependency_overrides[require_super_admin] = _fake_super
    yield client
    app.dependency_overrides.pop(require_super_admin, None)


@pytest.fixture
def seeded_global_with_token(db_session):
    """Seed the superadmin singleton with a stored (encrypted) token."""
    g = FreeConfigGlobal(
        is_enabled=True,
        default_daily_limit_mb=200,
        verification_bot_token_enc=encrypt_token("123:fake-bot-token"),
        verification_bot_username="@existingbot",
    )
    db_session.add(g)
    db_session.commit()
    return g


@pytest.fixture
def patch_validate_token_returns_username(monkeypatch):
    """validate_bot_token succeeds and returns a fixed username."""
    from app.services.free_config import membership_verifier as mv

    async def _ok(token):
        return "checkbot"

    monkeypatch.setattr(mv, "validate_bot_token", _ok)


@pytest.fixture
def patch_validate_token_raises(monkeypatch):
    """validate_bot_token raises (invalid token) -> endpoint maps to 400."""
    from app.services.free_config import membership_verifier as mv

    async def _raise(token):
        raise ValueError("Unauthorized: invalid bot token")

    monkeypatch.setattr(mv, "validate_bot_token", _raise)


@pytest.fixture
def patch_resolve_channel_ok(monkeypatch):
    """from_global succeeds and resolve_channel returns a fake channel -> 200."""
    from app.services.free_config import membership_verifier as mv

    class _FakeVerifier:
        _bot = object()

    monkeypatch.setattr(
        mv.MembershipVerifier,
        "from_global",
        classmethod(lambda cls, db: _FakeVerifier()),
    )

    async def _ok(bot, identifier):
        return {
            "chat_id": -100999888,
            "title": "Global Channel",
            "username": "@g",
            "invite_url": "https://t.me/g",
        }

    monkeypatch.setattr(mv, "resolve_channel", _ok)


# ---------------------------------------------------------------------------
# Global settings + token
# ---------------------------------------------------------------------------


def test_response_never_echoes_token(super_client, seeded_global_with_token):
    r = super_client.get("/api/v1/super/free-config/global")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["has_token"] is True
    assert "verification_bot_token_enc" not in body
    assert "token" not in body


def test_set_token_validates_via_getme(
    super_client, patch_validate_token_returns_username
):
    r = super_client.put(
        "/api/v1/super/free-config/global/token", json={"token": "123:abc"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["verification_bot_username"] == "checkbot"
    assert r.json()["has_token"] is True
    assert "token" not in r.json()


def test_set_invalid_token_rejected(super_client, patch_validate_token_raises):
    r = super_client.put(
        "/api/v1/super/free-config/global/token", json={"token": "bad"}
    )
    assert r.status_code == 400, r.text


# ---------------------------------------------------------------------------
# Global channels CRUD (admin_id=None)
# ---------------------------------------------------------------------------


def test_global_channel_add_and_list(super_client, patch_resolve_channel_ok):
    r = super_client.post(
        "/api/v1/super/free-config/channels", json={"identifier": "@g"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["username"] == "@g"

    lst = super_client.get("/api/v1/super/free-config/channels").json()
    assert any(c["username"] == "@g" for c in lst)
