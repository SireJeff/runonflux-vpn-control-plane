"""Integration tests for super-admin bot management endpoints.

These endpoints let the platform owner see all reseller bots, check their
Telegram webhook status, and bulk-reactivate them after infrastructure fixes.
"""
import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Grab lifecycle service module -- reuse whatever conftest already loaded
# so that _mod and _lc_mod share the same BotLifecycleError identity.
if "app.services.bots.bot_lifecycle_service" in sys.modules:
    _lc_mod = sys.modules["app.services.bots.bot_lifecycle_service"]
else:
    _LIFECYCLE_PATH = (
        Path(__file__).resolve().parent.parent.parent
        / "app"
        / "services"
        / "bots"
        / "bot_lifecycle_service.py"
    )
    _lc_spec = importlib.util.spec_from_file_location(
        "app.services.bots.bot_lifecycle_service",
        str(_LIFECYCLE_PATH),
    )
    _lc_mod = importlib.util.module_from_spec(_lc_spec)
    sys.modules["app.services.bots.bot_lifecycle_service"] = _lc_mod
    _lc_spec.loader.exec_module(_lc_mod)

# Load the endpoint module AFTER lifecycle service is in sys.modules,
# so its `from app.services.bots.bot_lifecycle_service import ...` resolves
# to the same module object (_lc_mod).
_MOD_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "app"
    / "api"
    / "v1"
    / "endpoints"
    / "super_admin_bots_api.py"
)
if "app.api.v1.endpoints.super_admin_bots_api" in sys.modules:
    _mod = sys.modules["app.api.v1.endpoints.super_admin_bots_api"]
else:
    _spec = importlib.util.spec_from_file_location(
        "app.api.v1.endpoints.super_admin_bots_api",
        str(_MOD_PATH),
    )
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules["app.api.v1.endpoints.super_admin_bots_api"] = _mod
    _spec.loader.exec_module(_mod)


SUPER_ADMIN_AUTH = {"id": 1, "role": "super_admin", "entity": MagicMock()}
ADMIN_AUTH = {"id": 5, "role": "admin", "entity": MagicMock()}


def _fake_super_admin_call(self, credentials=None, db=None):
    return SUPER_ADMIN_AUTH


def _patch_super_admin_auth(monkeypatch):
    monkeypatch.setattr(_mod.RoleChecker, "__call__", _fake_super_admin_call)


def _patch_admin_auth(monkeypatch):
    """Patch RoleChecker to raise 403 for non-super_admin roles."""
    from fastapi import HTTPException

    def _reject_non_super(self, credentials=None, db=None):
        raise HTTPException(status_code=403, detail="Role 'admin' not authorized")

    monkeypatch.setattr(_mod.RoleChecker, "__call__", _reject_non_super)


@pytest.fixture
def client():
    mock_db = MagicMock()
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


def _make_bot_row(bot_id, admin_id, username, is_active=True, has_token=True):
    bot = MagicMock()
    bot.id = bot_id
    bot.admin_id = admin_id
    bot.bot_username = username
    bot.bot_user_id = 1000 + bot_id
    bot.bot_display_name = username
    bot.welcome_message_fa = None
    bot.welcome_message_en = None
    bot.card_number = "1234-5678"
    bot.card_holder_name = "Test"
    bot.support_phone = None
    bot.support_telegram = None
    bot.default_macro_region = "eu"
    bot.is_active = is_active
    bot.webhook_registered_at = datetime.now(timezone.utc).replace(tzinfo=None)
    bot.created_at = datetime.now(timezone.utc).replace(tzinfo=None)
    bot.bot_token_enc = b"encrypted" if has_token else None
    return bot


def test_list_all_bots_requires_super_admin(client, monkeypatch):
    """Reseller admins must NOT be able to list all bots across resellers."""
    _patch_admin_auth(monkeypatch)
    # Verify the patch actually took effect: admin role, not super_admin
    mock_db = client._mock_db
    mock_db.query.return_value.order_by.return_value.all.return_value = []
    response = client.get(
        "/api/v1/super/bots",
        headers={"Authorization": "Bearer test"},
    )
    assert response.status_code == 403


def test_list_all_bots_returns_every_bot(client, monkeypatch):
    """Super-admin sees all bots regardless of admin_id."""
    _patch_super_admin_auth(monkeypatch)
    bots = [
        _make_bot_row(1, 5, "alpha_bot"),
        _make_bot_row(2, 6, "beta_bot"),
        _make_bot_row(3, 7, "gamma_bot", is_active=False),
    ]
    mock_db = client._mock_db
    mock_db.query.return_value.order_by.return_value.all.return_value = bots

    # Each bot also needs to resolve its admin (for admin_username)
    admin_lookup = MagicMock()
    admin_lookup.id = 5
    admin_lookup.username = "reseller_alpha"
    mock_db.query.return_value.filter.return_value.first.return_value = admin_lookup

    response = client.get(
        "/api/v1/super/bots",
        headers={"Authorization": "Bearer test"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["bots"]) == 3
    assert data["bots"][0]["bot_username"] == "alpha_bot"
    assert data["bots"][2]["is_active"] is False


def test_get_webhook_status_calls_get_webhook_info(client, monkeypatch):
    """Per-bot webhook status calls Telegram getWebhookInfo and returns result."""
    _patch_super_admin_auth(monkeypatch)
    bot = _make_bot_row(42, 5, "alpha_bot")
    mock_db = client._mock_db
    mock_db.query.return_value.filter.return_value.first.return_value = bot

    webhook_info_result = {
        "url": "https://api.operator7.example.invalid/bot/42/webhook",
        "pending_update_count": 0,
        "last_error_message": None,
    }
    with patch.object(_mod, "decrypt_token", return_value="plain_token"):
        with patch.object(
            _mod,
            "get_webhook_info",
            new_callable=AsyncMock,
            return_value=webhook_info_result,
        ):
            with patch.object(
                _mod,
                "build_webhook_url",
                return_value="https://api.operator7.example.invalid/bot/42/webhook",
            ):
                response = client.get(
                    "/api/v1/super/bots/42/webhook-status",
                    headers={"Authorization": "Bearer test"},
                )

    assert response.status_code == 200
    data = response.json()
    assert data["telegram_url"] == "https://api.operator7.example.invalid/bot/42/webhook"
    assert data["expected_url"] == "https://api.operator7.example.invalid/bot/42/webhook"
    assert data["url_matches"] is True
    assert data["pending_update_count"] == 0


def test_get_webhook_status_404_for_unknown_bot(client, monkeypatch):
    _patch_super_admin_auth(monkeypatch)
    mock_db = client._mock_db
    mock_db.query.return_value.filter.return_value.first.return_value = None

    response = client.get(
        "/api/v1/super/bots/9999/webhook-status",
        headers={"Authorization": "Bearer test"},
    )
    assert response.status_code == 404


def test_reactivate_all_iterates_active_bots(client, monkeypatch):
    """Bulk reactivation calls set_webhook for each active bot, returns counts."""
    _patch_super_admin_auth(monkeypatch)
    active_bots = [
        _make_bot_row(1, 5, "alpha"),
        _make_bot_row(2, 6, "beta"),
    ]
    mock_db = client._mock_db
    mock_db.query.return_value.filter.return_value.all.return_value = active_bots

    with patch.object(_mod, "decrypt_token", return_value="plain_token"):
        with patch.object(
            _mod,
            "build_webhook_url",
            return_value="https://api.operator7.example.invalid/bot/X/webhook",
        ):
            with patch.object(_mod, "set_webhook", new_callable=AsyncMock) as mock_set:
                response = client.post(
                    "/api/v1/super/bots/reactivate-all",
                    headers={"Authorization": "Bearer test"},
                )

    assert response.status_code == 200
    data = response.json()
    assert data["attempted"] == 2
    assert data["succeeded"] == 2
    assert data["failed"] == 0
    assert mock_set.await_count == 2


def test_reactivate_all_continues_on_per_bot_failure(client, monkeypatch):
    """One bot's set_webhook failure should not abort the bulk operation."""
    _patch_super_admin_auth(monkeypatch)
    bots = [
        _make_bot_row(1, 5, "alpha"),
        _make_bot_row(2, 6, "beta"),
    ]
    mock_db = client._mock_db
    mock_db.query.return_value.filter.return_value.all.return_value = bots

    call_count = [0]

    async def flaky_set_webhook(token, url, secret):
        call_count[0] += 1
        if call_count[0] == 1:
            raise _lc_mod.BotLifecycleError("simulated Telegram 500")

    with patch.object(_mod, "decrypt_token", return_value="plain_token"):
        with patch.object(
            _mod,
            "build_webhook_url",
            return_value="https://api.operator7.example.invalid/bot/X/webhook",
        ):
            with patch.object(_mod, "set_webhook", new=flaky_set_webhook):
                response = client.post(
                    "/api/v1/super/bots/reactivate-all",
                    headers={"Authorization": "Bearer test"},
                )

    assert response.status_code == 200
    data = response.json()
    assert data["attempted"] == 2
    assert data["succeeded"] == 1
    assert data["failed"] == 1
    assert len(data["failures"]) == 1


def test_reactivate_all_handles_decrypt_failure(client, monkeypatch):
    """A corrupted bot_token_enc should not abort reactivate-all.

    The bot with the bad token is reported in failures; other bots proceed normally.
    """
    _patch_super_admin_auth(monkeypatch)
    bots = [
        _make_bot_row(1, 5, "alpha"),
        _make_bot_row(2, 6, "beta"),
    ]
    mock_db = client._mock_db
    mock_db.query.return_value.filter.return_value.all.return_value = bots

    call_count = [0]

    def flaky_decrypt(encrypted_bytes):
        call_count[0] += 1
        if call_count[0] == 1:
            raise ValueError("simulated InvalidTag / corrupted blob")
        return "plain_token_for_beta"

    with patch.object(_mod, "decrypt_token", side_effect=flaky_decrypt):
        with patch.object(
            _mod,
            "build_webhook_url",
            return_value="https://api.operator7.example.invalid/bot/X/webhook",
        ):
            with patch.object(_mod, "set_webhook", new_callable=AsyncMock):
                response = client.post(
                    "/api/v1/super/bots/reactivate-all",
                    headers={"Authorization": "Bearer test"},
                )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["attempted"] == 2
    assert data["succeeded"] == 1
    assert data["failed"] == 1
    assert len(data["failures"]) == 1
    assert "decrypt_token failed" in data["failures"][0]["error"]


def test_get_webhook_status_handles_decrypt_failure(client, monkeypatch):
    """Corrupted bot_token_enc returns 500 with a clear error message."""
    _patch_super_admin_auth(monkeypatch)
    bot = _make_bot_row(42, 5, "alpha_bot")
    mock_db = client._mock_db
    mock_db.query.return_value.filter.return_value.first.return_value = bot

    with patch.object(
        _mod,
        "decrypt_token",
        side_effect=ValueError("simulated corrupted blob"),
    ):
        response = client.get(
            "/api/v1/super/bots/42/webhook-status",
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 500
    assert "Failed to decrypt bot token" in response.json()["detail"]
