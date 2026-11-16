"""Tests for NotificationRouter routing logic."""

import os

os.environ.setdefault("FLUXVPN_SECRET_KEY", "test-secret-key")

from unittest.mock import MagicMock, patch

import pytest

from app.models.admin_bots import AdminBot
from app.models.admin_users import AdminUser
from app.models.admins import Admin
from app.services.notifications.router import NotificationRouter


@pytest.fixture
def mock_db():
    return MagicMock()


def test_send_to_admin_uses_platform_token(mock_db, monkeypatch):
    """Admin recipients always receive messages from the platform bot token."""
    monkeypatch.setattr(
        "app.services.notifications.router.settings.TELEGRAM_BOT_TOKEN",
        "PLATFORM_TOKEN",
    )

    admin = Admin(id=1, username="x", telegram_id="12345", status="active")
    mock_db.query.return_value.filter.return_value.first.return_value = admin

    router = NotificationRouter(mock_db)
    with patch.object(router, "_send", return_value=True) as mock_send:
        result = router.send_to_admin(admin_id=1, message="hi")

    assert result is True
    mock_send.assert_called_once_with("PLATFORM_TOKEN", 12345, "hi")


def test_send_to_end_user_uses_reseller_bot_token(mock_db, monkeypatch):
    """End-user recipients receive messages from their reseller's bot token."""
    user = AdminUser(
        id=10,
        admin_id=1,
        username="u",
        telegram_chat_id=999,
        status="active",
    )
    bot = AdminBot(
        id=7,
        admin_id=1,
        bot_token_enc=b"\x00" * 28,
        bot_username="x_bot",
        bot_user_id=42,
        is_active=True,
    )

    def query_side_effect(model):
        q = MagicMock()
        if model is AdminUser:
            q.filter.return_value.first.return_value = user
        elif model is AdminBot:
            q.filter.return_value.first.return_value = bot
        return q

    mock_db.query.side_effect = query_side_effect
    router = NotificationRouter(mock_db)
    monkeypatch.setattr(router, "_get_bot_token", lambda bot_id: "DECRYPTED_TOKEN")

    with patch.object(router, "_send", return_value=True) as mock_send:
        result = router.send_to_end_user(user_id=10, message="hello")

    assert result is True
    # _send now accepts an optional reply_markup kwarg (defaults to None when
    # the caller doesn't supply one — e.g. plain-text sends).
    mock_send.assert_called_once_with(
        "DECRYPTED_TOKEN", 999, "hello", reply_markup=None
    )


def test_send_to_end_user_returns_false_when_no_bot_configured(mock_db):
    """Silently returns False if reseller hasn't configured a bot."""
    user = AdminUser(id=10, admin_id=1, username="u", telegram_chat_id=999)
    bot = None

    def query_side_effect(model):
        q = MagicMock()
        if model is AdminUser:
            q.filter.return_value.first.return_value = user
        elif model is AdminBot:
            q.filter.return_value.first.return_value = bot
        return q

    mock_db.query.side_effect = query_side_effect
    router = NotificationRouter(mock_db)

    assert router.send_to_end_user(user_id=10, message="x") is False


def test_send_traffic_alert_routes_to_both_end_user_and_admin(mock_db):
    """Dual-route: end-user via reseller bot, admin via platform bot."""
    user = AdminUser(id=10, admin_id=1, username="u", telegram_chat_id=999)
    admin = Admin(id=1, username="x", telegram_id="12345", status="active")
    bot = AdminBot(
        id=7,
        admin_id=1,
        bot_token_enc=b"\x00" * 28,
        bot_username="x",
        bot_user_id=42,
        is_active=True,
    )

    def query_side_effect(model):
        q = MagicMock()
        if model is AdminUser:
            q.filter.return_value.first.return_value = user
        elif model is AdminBot:
            q.filter.return_value.first.return_value = bot
        elif model is Admin:
            q.filter.return_value.first.return_value = admin
        return q

    mock_db.query.side_effect = query_side_effect
    router = NotificationRouter(mock_db)
    router._platform_token = "PLATFORM"
    router._get_bot_token = lambda bot_id: "RESELLER"

    sent = []
    # _send now accepts an optional reply_markup kwarg; accept **kwargs so the
    # lambda stays compatible with both plain and keyboard-bearing calls.
    router._send = lambda token, chat_id, msg, **kwargs: (
        sent.append((token, chat_id)) or True
    )

    router.send_traffic_alert(user_id=10, message="alert")

    assert ("RESELLER", 999) in sent
    assert ("PLATFORM", 12345) in sent
