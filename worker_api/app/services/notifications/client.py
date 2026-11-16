"""
Notification Service Client Implementation

Provides a unified notification system with multiple channels:
- Telegram (primary channel)
- Email (future)
- SMS (future)
"""

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict, Optional

from app.core.config import settings

if TYPE_CHECKING:
    from app.models import User

logger = logging.getLogger(__name__)


class NotificationChannel(ABC):
    """Abstract base class for notification channels"""

    @abstractmethod
    async def send(
        self,
        user: "User",
        message: str,
        data: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> bool:
        """
        Send a notification to a user

        Args:
            user: Target user
            message: Notification message
            data: Additional data for the notification
            **kwargs: Channel-specific parameters

        Returns:
            bool: True if notification was sent successfully
        """
        pass

    @abstractmethod
    async def send_inline_keyboard(
        self,
        user: "User",
        message: str,
        keyboard_data: Dict[str, Any],
        data: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> bool:
        """
        Send a notification with inline keyboard

        Args:
            user: Target user
            message: Notification message
            keyboard_data: Keyboard configuration
            data: Additional data for the notification
            **kwargs: Channel-specific parameters

        Returns:
            bool: True if notification was sent successfully
        """
        pass


class NotificationClient:
    """Notification client that routes to multiple channels"""

    def __init__(self):
        self.channels: Dict[str, NotificationChannel] = {}

    def register_channel(self, name: str, channel: NotificationChannel):
        """Register a notification channel"""
        self.channels[name] = channel
        logger.info(f"Registered notification channel: {name}")

    async def send(
        self,
        user: "User",
        message: str,
        channel: str = "telegram",
        data: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> bool:
        """
        Send notification through specified channel

        Args:
            user: Target user
            message: Notification message
            channel: Channel name (default: telegram)
            data: Additional data for the notification
            **kwargs: Channel-specific parameters

        Returns:
            bool: True if notification was sent successfully
        """
        if channel not in self.channels:
            logger.warning(f"Channel {channel} not registered")
            return False

        try:
            return await self.channels[channel].send(user, message, data, **kwargs)
        except Exception as e:
            logger.error(f"Failed to send notification via {channel}: {str(e)}")
            return False

    async def send_inline_keyboard(
        self,
        user: "User",
        message: str,
        keyboard_data: Dict[str, Any],
        channel: str = "telegram",
        data: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> bool:
        """
        Send notification with inline keyboard through specified channel

        Args:
            user: Target user
            message: Notification message
            keyboard_data: Keyboard configuration
            channel: Channel name (default: telegram)
            data: Additional data for the notification
            **kwargs: Channel-specific parameters

        Returns:
            bool: True if notification was sent successfully
        """
        if channel not in self.channels:
            logger.warning(f"Channel {channel} not registered")
            return False

        try:
            return await self.channels[channel].send_inline_keyboard(
                user, message, keyboard_data, data, **kwargs
            )
        except Exception as e:
            logger.error(f"Failed to send inline keyboard via {channel}: {str(e)}")
            return False


# Singleton instance
_notification_client: Optional[NotificationClient] = None


def get_notification_client() -> NotificationClient:
    """Get the singleton notification client instance with channels auto-registered"""
    global _notification_client
    if _notification_client is None:
        _notification_client = NotificationClient()
        # Auto-register Telegram channel if token is configured
        if settings.TELEGRAM_BOT_TOKEN:
            from app.services.notifications.telegram import TelegramChannel

            _notification_client.register_channel("telegram", TelegramChannel())
    return _notification_client


def send_notification_sync(
    user_id: int, message: str, channel: str = "telegram"
) -> bool:
    """
    Synchronous wrapper for sending notifications from Celery tasks.

    Loads the user from DB, then runs the async send() in a new event loop.

    Args:
        user_id: Target user ID
        message: Notification message
        channel: Channel name (default: telegram)

    Returns:
        True if notification was sent successfully
    """
    import asyncio

    from app.core.database import SessionLocal
    from app.models import User

    db = SessionLocal()
    try:
        user = db.query(User).filter_by(id=user_id).first()
        if not user:
            logger.warning(f"User {user_id} not found for notification")
            return False

        client = get_notification_client()
        return asyncio.run(client.send(user, message, channel=channel))

    except Exception as e:
        logger.error(f"Sync notification failed for user {user_id}: {str(e)}")
        return False
    finally:
        db.close()
