"""Unit tests for the reseller free-config API (Task 8).

Proves four behaviors:
  1. PUT rejects daily_limit_mb > global ceiling  -> 422
  2. PUT accepts daily_limit_mb <= ceiling        -> 200 + echoed
  3. POST /channels rejected when verification bot
     is not admin / not configured                -> 400
  4. POST /channels ok + appears in GET list       -> 200

Auth: the endpoint's admin dependency (`_require_admin`, a
RoleChecker(["admin"]) instance) is overridden via app.dependency_overrides
so no JWT is minted; it returns {"id": <seeded admin id>, "role": "admin"}.

Telegram: MembershipVerifier.from_global and resolve_channel are patched in
their source module (app.services.free_config.membership_verifier) — the
endpoint imports them at call time — so no live Telegram call happens.
"""

import pytest

from app.api.v1.endpoints import free_config_api
from app.core.crypto import encrypt_token
from app.models.admins import Admin
from app.models.free_config_channel import FreeConfigChannel
from app.models.free_config_global import FreeConfigGlobal


@pytest.fixture
def seed_admin(db_session):
    """Mint a real active reseller row and return it."""
    admin = Admin(
        username="reseller_free_cfg",
        password_hash="x",
        status="active",
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    return admin


@pytest.fixture
def admin_client(client, app, seed_admin):
    """TestClient with the admin dependency overridden to the seeded reseller."""
    def _fake_admin():
        return {"id": seed_admin.id, "role": "admin"}

    app.dependency_overrides[free_config_api._require_admin] = _fake_admin
    yield client
    app.dependency_overrides.pop(free_config_api._require_admin, None)


@pytest.fixture
def seed_global_ceiling_200(db_session):
    """Seed the superadmin singleton with a 200 MB ceiling + verification token."""
    g = FreeConfigGlobal(
        is_enabled=True,
        default_daily_limit_mb=200,
        verification_bot_token_enc=encrypt_token("123:fake-bot-token"),
    )
    db_session.add(g)
    db_session.commit()
    return g


@pytest.fixture
def patch_resolve_channel_raises(monkeypatch):
    """from_global succeeds (fake verifier) but resolve_channel raises -> 400."""
    from app.services.free_config import membership_verifier as mv

    class _FakeVerifier:
        _bot = object()

    monkeypatch.setattr(mv.MembershipVerifier, "from_global",
                        classmethod(lambda cls, db: _FakeVerifier()))

    async def _raise(bot, identifier):
        raise ValueError("verification bot is not an admin of this channel")

    monkeypatch.setattr(mv, "resolve_channel", _raise)


@pytest.fixture
def patch_resolve_channel_ok(monkeypatch):
    """from_global succeeds and resolve_channel returns a fake channel -> 200."""
    from app.services.free_config import membership_verifier as mv

    class _FakeVerifier:
        _bot = object()

    monkeypatch.setattr(mv.MembershipVerifier, "from_global",
                        classmethod(lambda cls, db: _FakeVerifier()))

    async def _ok(bot, identifier):
        return {
            "chat_id": -100123456,
            "title": "Test Channel",
            "username": "@x",
            "invite_url": "https://t.me/x",
        }

    monkeypatch.setattr(mv, "resolve_channel", _ok)


# ---------------------------------------------------------------------------
# Per-user field / ceiling behaviors
# ---------------------------------------------------------------------------


def test_put_rejects_limit_above_ceiling(admin_client, seed_global_ceiling_200):
    r = admin_client.put(
        "/api/v1/admin/free-config",
        json={"kind": "per_user", "daily_limit_mb": 5000},
    )
    assert r.status_code == 422, r.text


def test_put_accepts_limit_at_or_below_ceiling(admin_client, seed_global_ceiling_200):
    r = admin_client.put(
        "/api/v1/admin/free-config",
        json={"kind": "per_user", "daily_limit_mb": 150},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["daily_limit_mb"] == 150
    assert body["global_ceiling_mb"] == 200


# ---------------------------------------------------------------------------
# Channels CRUD behaviors
# ---------------------------------------------------------------------------


def test_channel_save_rejected_when_bot_not_admin(
    admin_client, patch_resolve_channel_raises
):
    r = admin_client.post(
        "/api/v1/admin/free-config/channels", json={"identifier": "@x"}
    )
    assert r.status_code == 400, r.text


def test_channel_save_rejected_when_bot_not_configured(admin_client):
    # No FreeConfigGlobal row -> from_global returns None -> 400.
    r = admin_client.post(
        "/api/v1/admin/free-config/channels", json={"identifier": "@x"}
    )
    assert r.status_code == 400, r.text


def test_channel_save_ok_and_list(admin_client, patch_resolve_channel_ok):
    r = admin_client.post(
        "/api/v1/admin/free-config/channels", json={"identifier": "@x"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["username"] == "@x"

    lst = admin_client.get("/api/v1/admin/free-config/channels").json()
    assert any(c["username"] == "@x" for c in lst)


# ---------------------------------------------------------------------------
# Multi-tenant isolation: channels are scoped per admin
# ---------------------------------------------------------------------------


def test_channels_are_scoped_per_admin(client, app, db_session):
    """Admin A must never see admin B's channels in the list."""
    admin_a = Admin(username="reseller_a", password_hash="x", status="active")
    admin_b = Admin(username="reseller_b", password_hash="x", status="active")
    db_session.add_all([admin_a, admin_b])
    db_session.commit()
    db_session.refresh(admin_a)
    db_session.refresh(admin_b)

    b_channel = FreeConfigChannel(
        admin_id=admin_b.id, chat_id=-100, title="B", is_active=True
    )
    db_session.add(b_channel)
    db_session.commit()

    def _fake_admin_a():
        return {"id": admin_a.id, "role": "admin"}

    app.dependency_overrides[free_config_api._require_admin] = _fake_admin_a
    try:
        lst = client.get("/api/v1/admin/free-config/channels").json()
    finally:
        app.dependency_overrides.pop(free_config_api._require_admin, None)

    assert len(lst) == 0
    assert not any(c["chat_id"] == -100 for c in lst)


def test_delete_channel_404_when_not_owned(client, app, db_session):
    """Admin A deleting admin B's channel gets 404 and B's channel survives."""
    admin_a = Admin(username="reseller_a2", password_hash="x", status="active")
    admin_b = Admin(username="reseller_b2", password_hash="x", status="active")
    db_session.add_all([admin_a, admin_b])
    db_session.commit()
    db_session.refresh(admin_a)
    db_session.refresh(admin_b)

    b_channel = FreeConfigChannel(
        admin_id=admin_b.id, chat_id=-100, title="B", is_active=True
    )
    db_session.add(b_channel)
    db_session.commit()
    db_session.refresh(b_channel)
    b_channel_id = b_channel.id

    def _fake_admin_a():
        return {"id": admin_a.id, "role": "admin"}

    app.dependency_overrides[free_config_api._require_admin] = _fake_admin_a
    try:
        r = client.delete(f"/api/v1/admin/free-config/channels/{b_channel_id}")
    finally:
        app.dependency_overrides.pop(free_config_api._require_admin, None)

    assert r.status_code == 404, r.text
    still_there = (
        db_session.query(FreeConfigChannel)
        .filter(FreeConfigChannel.id == b_channel_id)
        .first()
    )
    assert still_there is not None
