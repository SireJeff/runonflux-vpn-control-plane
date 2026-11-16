"""Integration tests for /admin/bot-config endpoints.

Uses the same module-loading trick as test_webhook_endpoint.py to avoid
pulling in the full app with its heavy dependencies (Stripe, NOWPayments).
We load only the bot_config_api module, build a minimal FastAPI app, and
mock DB / Telegram API calls.

NOTE: These tests use a conftest-free approach to avoid needing a local
PostgreSQL instance. We override the DB dependency via dependency_overrides
on our minimal FastAPI app.
"""

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Load the bot_config_api module directly (avoids heavy __init__.py imports)
# ---------------------------------------------------------------------------
_MOD_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "app"
    / "api"
    / "v1"
    / "endpoints"
    / "bot_config_api.py"
)
_spec = importlib.util.spec_from_file_location(
    "app.api.v1.endpoints.bot_config_api",
    str(_MOD_PATH),
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["app.api.v1.endpoints.bot_config_api"] = _mod
_spec.loader.exec_module(_mod)

# Also ensure the lifecycle service is importable (for monkeypatch targets)
_LIFECYCLE_MOD_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "app"
    / "services"
    / "bots"
    / "bot_lifecycle_service.py"
)
_lc_spec = importlib.util.spec_from_file_location(
    "app.services.bots.bot_lifecycle_service",
    str(_LIFECYCLE_MOD_PATH),
)
_lc_mod = importlib.util.module_from_spec(_lc_spec)
sys.modules["app.services.bots.bot_lifecycle_service"] = _lc_mod
_lc_spec.loader.exec_module(_lc_mod)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ADMIN_AUTH = {"id": 5, "role": "admin", "entity": MagicMock()}


def _fake_admin_call(self, credentials=None, db=None):
    """Stand-in for RoleChecker.__call__ -- returns the admin auth dict.

    Replaces the real __call__ with a plain function whose signature matches
    the original (self, credentials=..., db=...).  Python's
    inspect._signature_bound_method then correctly strips ``self`` and
    FastAPI sees two defaulted params -- no spurious 422 errors.

    NOTE: Cannot use ``staticmethod`` + zero-param function because
    Python 3.11's ``_signature_bound_method`` rejects a first parameter
    whose kind is VAR_KEYWORD (i.e. ``**kwargs``), raising
    ``ValueError: invalid method signature``.
    """
    return ADMIN_AUTH


def _patch_admin_auth(monkeypatch):
    """Patch RoleChecker.__call__ on the actual class (visible via _mod.RoleChecker)."""
    monkeypatch.setattr(_mod.RoleChecker, "__call__", _fake_admin_call)


@pytest.fixture
def client():
    """Build a minimal FastAPI app with only the bot-config router.

    We override get_db to return a mock session so no real DB is needed.
    """
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    _app = FastAPI()
    _app.include_router(_mod.router, prefix="/api/v1")

    def override_get_db():
        yield mock_db

    from app.core.database import get_db

    _app.dependency_overrides[get_db] = override_get_db

    _test_client = TestClient(_app)
    _test_client._mock_db = mock_db
    yield _test_client

    _app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_get_bot_config_returns_404_when_no_bot(client, monkeypatch):
    """Reseller with no bot yet returns 404."""
    _patch_admin_auth(monkeypatch)
    # DB query returns None by default (mock_db setup)

    response = client.get(
        "/api/v1/admin/bot-config",
        headers={"Authorization": "Bearer test"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Bot not configured"


def test_register_bot_calls_get_me_and_set_webhook(client, monkeypatch):
    """POST /admin/bot-config happy path: getMe + setWebhook + DB insert.

    The endpoint creates an AdminBot instance internally. We use
    db.refresh side_effect to set attributes on that instance (mimicking
    what real Postgres would do via autoincrement + server_default).
    """
    _patch_admin_auth(monkeypatch)

    mock_db = client._mock_db
    # Default mock already returns None for first() — no existing bot.

    # When endpoint calls db.refresh(bot), set the attributes Postgres would.
    def fake_refresh(obj):
        obj.id = 42
        obj.admin_id = 5
        obj.created_at = datetime.now(timezone.utc).replace(tzinfo=None)
        # webhook_registered_at set later by endpoint, not here

    mock_db.refresh = MagicMock(side_effect=fake_refresh)

    with patch.object(
        _mod,
        "get_me",
        new_callable=AsyncMock,
        return_value={"username": "test_bot", "id": 123456, "first_name": "Test Bot"},
    ):
        with patch.object(_mod, "set_webhook", new_callable=AsyncMock):
            with patch.object(
                _mod,
                "build_webhook_url",
                return_value="https://api.example.com/bot/42/webhook",
            ):
                with patch.object(_mod, "encrypt_token", return_value=b"encrypted"):
                    response = client.post(
                        "/api/v1/admin/bot-config",
                        json={"bot_token": "123456:ABC-DEF_long_token_value_here"},
                        headers={"Authorization": "Bearer test"},
                    )

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["bot_username"] == "test_bot"
    assert data["bot_user_id"] == 123456
    assert data["is_active"] is True
    assert data["admin_id"] == 5

    mock_db.add.assert_called_once()
    assert mock_db.commit.call_count >= 2  # insert + webhook_registered_at update


def test_register_bot_rolls_back_on_setWebhook_failure(client, monkeypatch):
    """If setWebhook fails, the DB row is deleted and 502 is returned."""
    _patch_admin_auth(monkeypatch)

    mock_db = client._mock_db

    deleted_bots = []

    def fake_delete(bot):
        deleted_bots.append(bot)

    mock_db.delete = MagicMock(side_effect=fake_delete)

    def fake_refresh(obj):
        obj.id = 42
        obj.admin_id = 5

    mock_db.refresh = MagicMock(side_effect=fake_refresh)

    with patch.object(
        _mod,
        "get_me",
        new_callable=AsyncMock,
        return_value={"username": "test_bot", "id": 123456, "first_name": "Test"},
    ):
        with patch.object(
            _mod,
            "set_webhook",
            new_callable=AsyncMock,
            side_effect=_mod.BotLifecycleError("403 Forbidden"),
        ):
            with patch.object(
                _mod,
                "build_webhook_url",
                return_value="https://api.example.com/bot/42/webhook",
            ):
                with patch.object(_mod, "encrypt_token", return_value=b"enc"):
                    response = client.post(
                        "/api/v1/admin/bot-config",
                        json={"bot_token": "123456:ABC-DEF_long_token_value_here"},
                        headers={"Authorization": "Bearer test"},
                    )

    assert response.status_code == 502
    assert "setWebhook failed" in response.json()["detail"]

    # Verify rollback: delete was called with the bot instance endpoint created
    assert len(deleted_bots) == 1
    assert mock_db.commit.call_count >= 1


def test_deactivate_calls_delete_webhook_and_evicts_manager(client, monkeypatch):
    """POST /deactivate calls deleteWebhook, sets is_active=False, evicts manager."""
    _patch_admin_auth(monkeypatch)

    existing_bot = MagicMock()
    existing_bot.id = 42
    existing_bot.admin_id = 5
    existing_bot.bot_username = "test_bot"
    existing_bot.bot_user_id = 123456
    existing_bot.bot_display_name = "Test"
    existing_bot.welcome_message_fa = None
    existing_bot.welcome_message_en = None
    existing_bot.card_number = None
    existing_bot.card_holder_name = None
    existing_bot.crypto_address = None
    existing_bot.crypto_network = None
    existing_bot.crypto_memo = None
    existing_bot.support_phone = None
    existing_bot.support_telegram = None
    existing_bot.default_macro_region = "eu"
    existing_bot.is_active = True
    existing_bot.webhook_registered_at = datetime.now(timezone.utc).replace(tzinfo=None)
    existing_bot.created_at = datetime.now(timezone.utc).replace(tzinfo=None)

    mock_db = client._mock_db
    mock_db.query.return_value.filter.return_value.first.return_value = existing_bot

    mock_manager = MagicMock()
    mock_manager.evict = AsyncMock()
    _mod.configure_bot_manager(mock_manager)

    delete_webhook_mock = AsyncMock()
    with patch.object(_mod, "decrypt_token", return_value="plain_token"):
        with patch.object(_mod, "delete_webhook", new=delete_webhook_mock):
            response = client.post(
                "/api/v1/admin/bot-config/deactivate",
                headers={"Authorization": "Bearer test"},
            )
            # Assert INSIDE the with block while the patch is active
            delete_webhook_mock.assert_awaited_once_with("plain_token")
            mock_manager.evict.assert_awaited_once_with(42)

    assert response.status_code == 200, response.text
    assert response.json()["is_active"] is False

    _mod.configure_bot_manager(None)


def test_reactivate_bot_re_registers_webhook_and_sets_active(client, monkeypatch):
    """POST /reactivate flips is_active=True, calls set_webhook, refreshes manager."""
    _patch_admin_auth(monkeypatch)

    inactive_bot = MagicMock()
    inactive_bot.id = 42
    inactive_bot.admin_id = 5
    inactive_bot.bot_username = "test_bot"
    inactive_bot.bot_user_id = 123456
    inactive_bot.bot_display_name = "Test"
    inactive_bot.welcome_message_fa = None
    inactive_bot.welcome_message_en = None
    inactive_bot.card_number = None
    inactive_bot.card_holder_name = None
    inactive_bot.crypto_address = None
    inactive_bot.crypto_network = None
    inactive_bot.crypto_memo = None
    inactive_bot.support_phone = None
    inactive_bot.support_telegram = None
    inactive_bot.default_macro_region = "eu"
    inactive_bot.is_active = False
    inactive_bot.webhook_registered_at = None
    inactive_bot.webhook_secret = "secret123"
    inactive_bot.created_at = datetime.now(timezone.utc).replace(tzinfo=None)

    mock_db = client._mock_db
    mock_db.query.return_value.filter.return_value.first.return_value = inactive_bot

    mock_manager = MagicMock()
    mock_manager.refresh = AsyncMock()
    _mod.configure_bot_manager(mock_manager)

    with patch.object(_mod, "decrypt_token", return_value="plain_token"):
        with patch.object(
            _mod,
            "build_webhook_url",
            return_value="https://api.example.com/bot/42/webhook",
        ):
            with patch.object(_mod, "set_webhook", new_callable=AsyncMock) as mock_set:
                response = client.post(
                    "/api/v1/admin/bot-config/reactivate",
                    headers={"Authorization": "Bearer test"},
                )
                mock_set.assert_awaited_once()

    assert response.status_code == 200, response.text
    assert response.json()["is_active"] is True
    mock_manager.refresh.assert_awaited_once_with(42)

    _mod.configure_bot_manager(None)


def test_reactivate_bot_404_when_no_bot(client, monkeypatch):
    """No bot row for this admin -> 404."""
    _patch_admin_auth(monkeypatch)

    response = client.post(
        "/api/v1/admin/bot-config/reactivate",
        headers={"Authorization": "Bearer test"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Bot not configured"


def test_reactivate_bot_409_when_already_active(client, monkeypatch):
    """Already-active bot -> 409 (idempotency guard)."""
    _patch_admin_auth(monkeypatch)

    active_bot = MagicMock()
    active_bot.is_active = True

    mock_db = client._mock_db
    mock_db.query.return_value.filter.return_value.first.return_value = active_bot

    response = client.post(
        "/api/v1/admin/bot-config/reactivate",
        headers={"Authorization": "Bearer test"},
    )
    assert response.status_code == 409


def test_send_test_ping_uses_reseller_own_bot(client, monkeypatch):
    """Send Test Ping must exercise the RESELLER'S OWN bot — getMe +
    getWebhookInfo on THEIR token + a DM via THAT bot — not the platform bot.
    """
    _patch_admin_auth(monkeypatch)

    admin_entity = MagicMock()
    admin_entity.id = 5
    admin_entity.telegram_id = "654321"
    monkeypatch.setitem(ADMIN_AUTH, "entity", admin_entity)

    bot = MagicMock()
    bot.bot_token_enc = b"enc"
    bot.bot_username = "erfans_bot"
    client._mock_db.query.return_value.filter.return_value.first.return_value = bot

    monkeypatch.setattr(_mod, "decrypt_token", lambda enc: "PLAINTOKEN")

    getme = AsyncMock(return_value={"username": "erfans_bot", "id": 111})
    getwh = AsyncMock(
        return_value={
            "url": "https://api.operator7.example.invalid/bot/3/webhook",
            "pending_update_count": 0,
            "last_error_message": None,
        }
    )
    sendmsg = AsyncMock(return_value=True)
    monkeypatch.setattr(_mod, "get_me", getme)
    monkeypatch.setattr(_mod, "get_webhook_info", getwh)
    monkeypatch.setattr(_mod, "send_message", sendmsg)

    response = client.post(
        "/api/v1/admin/bot-config/test",
        headers={"Authorization": "Bearer test"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["ok"] is True
    assert data["bot_username"] == "erfans_bot"
    assert data["webhook_url"] == "https://api.operator7.example.invalid/bot/3/webhook"
    assert data["dm_sent"] is True

    # The reseller's OWN decrypted token was used for every call.
    getme.assert_awaited_once_with("PLAINTOKEN")
    getwh.assert_awaited_once_with("PLAINTOKEN")
    sendmsg.assert_awaited_once()
    assert sendmsg.await_args.args[0] == "PLAINTOKEN"
    assert sendmsg.await_args.args[1] == 654321  # admin's own chat


def test_send_test_ping_404_when_no_bot(client, monkeypatch):
    """No bot configured for this reseller -> 404."""
    _patch_admin_auth(monkeypatch)
    # default mock_db.first() returns None
    response = client.post(
        "/api/v1/admin/bot-config/test",
        headers={"Authorization": "Bearer test"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Bot not configured"


def test_send_test_ping_reports_invalid_token(client, monkeypatch):
    """Invalid/revoked token -> ok False with an explanatory detail (not 500)."""
    _patch_admin_auth(monkeypatch)

    admin_entity = MagicMock()
    admin_entity.id = 5
    admin_entity.telegram_id = "1"
    monkeypatch.setitem(ADMIN_AUTH, "entity", admin_entity)

    bot = MagicMock()
    bot.bot_token_enc = b"enc"
    bot.bot_username = "b"
    client._mock_db.query.return_value.filter.return_value.first.return_value = bot

    monkeypatch.setattr(_mod, "decrypt_token", lambda enc: "TOK")
    monkeypatch.setattr(
        _mod,
        "get_me",
        AsyncMock(side_effect=_mod.BotLifecycleError("401 Unauthorized")),
    )

    response = client.post(
        "/api/v1/admin/bot-config/test",
        headers={"Authorization": "Bearer test"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["ok"] is False
    assert "invalid" in data["detail"].lower() or "revoked" in data["detail"].lower()


def test_register_bot_passes_api_domain_url_to_set_webhook(client, monkeypatch):
    """Regression: setWebhook must receive a URL on the API domain, not the
    panel domain. This test exercises the REAL build_webhook_url (no patch)
    and captures what URL the endpoint actually passes to set_webhook.

    Bug history: build_webhook_url used to call get_dashboard_base_url which
    returned USER_PORTAL_URL (panel.operator5.example.invalid). Telegram then POSTed to
    the Next.js container which returned 404, silently breaking all bots.
    """
    _patch_admin_auth(monkeypatch)

    mock_db = client._mock_db
    mock_db.query.return_value.filter.return_value.first.return_value = None

    def fake_refresh(obj):
        obj.id = 42
        obj.admin_id = 5
        obj.created_at = datetime.now(timezone.utc).replace(tzinfo=None)

    mock_db.refresh = MagicMock(side_effect=fake_refresh)

    captured_urls = []

    async def fake_set_webhook(token, url, secret):
        captured_urls.append(url)

    # Patch get_api_base_url so we don't depend on real platform_settings
    # rows. This isolates the test to "does the endpoint wire build_webhook_url
    # into set_webhook correctly" -- the URL value itself is verified in the
    # unit test for build_webhook_url (test_build_webhook_url_*.py).
    from app.services import url_resolver

    monkeypatch.setattr(
        url_resolver, "get_api_base_url", lambda db: "https://api.operator7.example.invalid"
    )

    with patch.object(
        _mod,
        "get_me",
        new_callable=AsyncMock,
        return_value={"username": "test_bot", "id": 123456, "first_name": "Test"},
    ):
        with patch.object(_mod, "set_webhook", new=fake_set_webhook):
            with patch.object(_mod, "encrypt_token", return_value=b"encrypted"):
                response = client.post(
                    "/api/v1/admin/bot-config",
                    json={"bot_token": "123456:ABC-DEF_long_token_value_here"},
                    headers={"Authorization": "Bearer test"},
                )

    assert response.status_code == 201, response.text
    assert len(captured_urls) == 1, f"set_webhook called {len(captured_urls)} times"
    url = captured_urls[0]
    assert (
        url == "https://api.operator7.example.invalid/bot/42/webhook"
    ), f"set_webhook got wrong URL: {url}"
    assert (
        "panel.operator5.example.invalid" not in url
    ), f"Portal domain leaked into set_webhook URL: {url}"


def test_reactivate_bot_passes_api_domain_url_to_set_webhook(client, monkeypatch):
    """Same regression check for the reactivate path."""
    _patch_admin_auth(monkeypatch)

    inactive_bot = MagicMock()
    inactive_bot.id = 42
    inactive_bot.admin_id = 5
    inactive_bot.bot_username = "test_bot"
    inactive_bot.bot_user_id = 123456
    inactive_bot.bot_display_name = "Test"
    inactive_bot.welcome_message_fa = None
    inactive_bot.welcome_message_en = None
    inactive_bot.card_number = None
    inactive_bot.card_holder_name = None
    inactive_bot.crypto_address = None
    inactive_bot.crypto_network = None
    inactive_bot.crypto_memo = None
    inactive_bot.support_phone = None
    inactive_bot.support_telegram = None
    inactive_bot.default_macro_region = "eu"
    inactive_bot.is_active = False
    inactive_bot.webhook_registered_at = None
    inactive_bot.webhook_secret = "secret123"
    inactive_bot.created_at = datetime.now(timezone.utc).replace(tzinfo=None)

    mock_db = client._mock_db
    mock_db.query.return_value.filter.return_value.first.return_value = inactive_bot

    captured_urls = []

    async def fake_set_webhook(token, url, secret):
        captured_urls.append(url)

    from app.services import url_resolver

    monkeypatch.setattr(
        url_resolver, "get_api_base_url", lambda db: "https://api.operator7.example.invalid"
    )

    _mod.configure_bot_manager(MagicMock(refresh=AsyncMock()))

    with patch.object(_mod, "decrypt_token", return_value="plain_token"):
        with patch.object(_mod, "set_webhook", new=fake_set_webhook):
            response = client.post(
                "/api/v1/admin/bot-config/reactivate",
                headers={"Authorization": "Bearer test"},
            )

    assert response.status_code == 200, response.text
    assert len(captured_urls) == 1
    assert captured_urls[0] == "https://api.operator7.example.invalid/bot/42/webhook"

    _mod.configure_bot_manager(None)
