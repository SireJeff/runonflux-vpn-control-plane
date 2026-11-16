"""Integration tests for the /bot/{bot_id}/webhook endpoint."""

import importlib.util
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Load the webhook module directly to avoid pulling in the full
# app.api.v1.endpoints package (whose __init__.py eagerly imports
# Stripe, NOWPayments, and other heavy dependencies).
_WEBHOOK_MOD_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "app"
    / "api"
    / "v1"
    / "endpoints"
    / "reseller_bot_webhook.py"
)
_spec = importlib.util.spec_from_file_location(
    "app.api.v1.endpoints.reseller_bot_webhook",
    str(_WEBHOOK_MOD_PATH),
)
_webhook_mod = importlib.util.module_from_spec(_spec)
import sys

sys.modules["app.api.v1.endpoints.reseller_bot_webhook"] = _webhook_mod
_spec.loader.exec_module(_webhook_mod)


@pytest.fixture
def client():
    """Build a minimal FastAPI app with only the webhook router."""
    _app = FastAPI()
    _app.include_router(_webhook_mod.router)
    return TestClient(_app)


def test_webhook_rejects_missing_secret_header(client):
    response = client.post("/bot/1/webhook", json={})
    assert response.status_code == 422  # missing required header


def test_webhook_404_unknown_bot(client, monkeypatch):
    """Unknown bot_id returns 404 before secret validation."""
    monkeypatch.setattr(_webhook_mod, "_get_bot", lambda db, bot_id: None)
    response = client.post(
        "/bot/9999/webhook",
        json={"update_id": 1},
        headers={"X-Telegram-Bot-Api-Secret-Token": "anything"},
    )
    assert response.status_code == 404


def test_webhook_401_wrong_secret(client, monkeypatch):
    from unittest.mock import MagicMock

    bot_mock = MagicMock()
    bot_mock.id = 1
    bot_mock.is_active = True
    bot_mock.webhook_secret = "correct-secret"
    monkeypatch.setattr(_webhook_mod, "_get_bot", lambda db, bot_id: bot_mock)
    response = client.post(
        "/bot/1/webhook",
        json={"update_id": 1},
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
    )
    assert response.status_code == 401


def test_webhook_dispatches_update_on_valid_secret(client, monkeypatch):
    from unittest.mock import MagicMock

    bot_mock = MagicMock()
    bot_mock.id = 1
    bot_mock.is_active = True
    bot_mock.webhook_secret = "correct-secret"
    monkeypatch.setattr(_webhook_mod, "_get_bot", lambda db, bot_id: bot_mock)

    async def fake_process(payload, bot_id):
        return None

    monkeypatch.setattr(_webhook_mod, "_process_update_async", fake_process)

    response = client.post(
        "/bot/1/webhook",
        json={
            "update_id": 1,
            "message": {
                "message_id": 1,
                "from": {"id": 100, "is_bot": False, "first_name": "Test"},
                "chat": {"id": 100, "type": "private"},
                "date": 1700000000,
                "text": "/start",
            },
        },
        headers={"X-Telegram-Bot-Api-Secret-Token": "correct-secret"},
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_webhook_releases_db_session_before_dispatch(client, monkeypatch):
    """The validation DB session must be CLOSED before the (slow) update
    dispatch runs, so a pooled connection is never held across Telegram
    handler I/O. Holding it was the cause of the 2026-09-10 pool-exhaustion
    incident that made reseller bots time out.
    """
    from unittest.mock import MagicMock

    tracker = MagicMock()
    tracker.closed = False

    def _close():
        tracker.closed = True

    tracker.close.side_effect = _close

    # receive_webhook must open its OWN short-lived session via module-level
    # SessionLocal (not a request-scoped Depends held for the whole request).
    monkeypatch.setattr(_webhook_mod, "SessionLocal", lambda: tracker, raising=True)

    bot_mock = MagicMock()
    bot_mock.id = 1
    bot_mock.is_active = True
    bot_mock.webhook_secret = "correct-secret"
    monkeypatch.setattr(_webhook_mod, "_get_bot", lambda db, bot_id: bot_mock)

    seen = {}

    async def fake_process(payload, bot_id):
        seen["closed_at_dispatch"] = tracker.closed

    monkeypatch.setattr(_webhook_mod, "_process_update_async", fake_process)

    response = client.post(
        "/bot/1/webhook",
        json={"update_id": 1},
        headers={"X-Telegram-Bot-Api-Secret-Token": "correct-secret"},
    )
    assert response.status_code == 200
    assert seen.get("closed_at_dispatch") is True
    tracker.close.assert_called_once()
