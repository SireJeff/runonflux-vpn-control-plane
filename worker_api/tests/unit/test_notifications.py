"""
Unit tests for Notification Service
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.notifications.client import (
    NotificationChannel,
    NotificationClient,
    get_notification_client,
    send_notification_sync,
)
from app.services.notifications.telegram import TelegramChannel
from tests.factories import UserFactory


class TestNotificationClient:
    """Test cases for NotificationClient"""

    def test_register_channel(self):
        """Test registering a notification channel"""
        client = NotificationClient()
        mock_channel = MagicMock(spec=NotificationChannel)

        client.register_channel("test", mock_channel)

        assert "test" in client.channels

    @pytest.mark.asyncio
    async def test_send_to_unregistered_channel_returns_false(self):
        """Test sending to non-existent channel returns False"""
        client = NotificationClient()
        user = UserFactory.create(telegram_user_id=30001)

        result = await client.send(user, "test message", channel="nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_delegates_to_channel(self):
        """Test that send() delegates to the correct channel"""
        client = NotificationClient()
        mock_channel = AsyncMock(spec=NotificationChannel)
        mock_channel.send.return_value = True
        client.register_channel("mock", mock_channel)

        user = UserFactory.create(telegram_user_id=30002)
        result = await client.send(user, "test message", channel="mock")

        assert result is True
        mock_channel.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_handles_channel_exception(self):
        """Test that exceptions in channels are caught"""
        client = NotificationClient()
        mock_channel = AsyncMock(spec=NotificationChannel)
        mock_channel.send.side_effect = Exception("API down")
        client.register_channel("failing", mock_channel)

        user = UserFactory.create(telegram_user_id=30003)
        result = await client.send(user, "test message", channel="failing")

        assert result is False


class TestTelegramChannel:
    """Test cases for TelegramChannel"""

    @pytest.mark.asyncio
    async def test_send_without_bot_token_returns_false(self):
        """Test that missing bot token returns False"""
        with patch("app.services.notifications.telegram.settings") as mock_settings:
            mock_settings.TELEGRAM_BOT_TOKEN = None
            channel = TelegramChannel()
            user = UserFactory.create(telegram_user_id=40001)

            result = await channel.send(user, "test")
            assert result is False

    @pytest.mark.asyncio
    async def test_send_without_user_telegram_id_returns_false(self):
        """Test that missing telegram_user_id returns False"""
        with patch("app.services.notifications.telegram.settings") as mock_settings:
            mock_settings.TELEGRAM_BOT_TOKEN = "test_token"
            channel = TelegramChannel()
            user = UserFactory.create(telegram_user_id=None)

            result = await channel.send(user, "test")
            assert result is False

    @pytest.mark.asyncio
    async def test_send_success(self):
        """Test successful Telegram message sending"""
        with patch("app.services.notifications.telegram.settings") as mock_settings:
            mock_settings.TELEGRAM_BOT_TOKEN = "test_token"
            channel = TelegramChannel()

            user = UserFactory.create(telegram_user_id=40002)

            with patch("httpx.AsyncClient") as mock_client_class:
                mock_response = MagicMock()
                mock_response.raise_for_status = MagicMock()

                mock_client = AsyncMock()
                mock_client.post.return_value = mock_response
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client_class.return_value = mock_client

                result = await channel.send(user, "Hello!")

                assert result is True
                mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_handles_http_error(self):
        """Test that HTTP errors are caught gracefully"""
        import httpx

        with patch("app.services.notifications.telegram.settings") as mock_settings:
            mock_settings.TELEGRAM_BOT_TOKEN = "test_token"
            channel = TelegramChannel()

            user = UserFactory.create(telegram_user_id=40003)

            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.post.side_effect = httpx.RequestError("Connection failed")
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client_class.return_value = mock_client

                result = await channel.send(user, "Hello!")
                assert result is False


class TestGetNotificationClient:
    """Test cases for singleton factory"""

    def test_returns_notification_client(self):
        """Test that factory returns a NotificationClient"""
        # Reset singleton
        import app.services.notifications.client as mod

        mod._notification_client = None

        client = get_notification_client()
        assert isinstance(client, NotificationClient)

        # Reset for other tests
        mod._notification_client = None

    def test_singleton_returns_same_instance(self):
        """Test that repeated calls return the same instance"""
        import app.services.notifications.client as mod

        mod._notification_client = None

        client1 = get_notification_client()
        client2 = get_notification_client()
        assert client1 is client2

        mod._notification_client = None

    def test_auto_registers_telegram_when_token_set(self):
        """Test that Telegram channel is auto-registered when token is set."""
        import app.services.notifications.client as mod

        mod._notification_client = None

        with patch("app.services.notifications.client.settings") as mock_settings:
            mock_settings.TELEGRAM_BOT_TOKEN = "test_token"
            client = get_notification_client()
            assert "telegram" in client.channels

        mod._notification_client = None


class TestSendNotificationSync:
    """Test cases for sync notification wrapper"""

    def test_nonexistent_user_returns_false(self, db):
        """Test that missing user returns False"""
        with patch("app.core.database.SessionLocal") as mock_session_cls:
            mock_session = MagicMock()
            mock_session.query.return_value.filter_by.return_value.first.return_value = (
                None
            )
            mock_session_cls.return_value = mock_session

            result = send_notification_sync(999999, "test")
            assert result is False
