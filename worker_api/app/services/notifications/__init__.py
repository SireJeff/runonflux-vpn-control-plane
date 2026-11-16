"""
Notification Service Package

Provides unified notification delivery via multiple channels (Telegram, Email, etc.)
"""

from app.services.notifications.client import (
    NotificationChannel,
    NotificationClient,
    get_notification_client,
    send_notification_sync,
)
from app.services.notifications.telegram import TelegramChannel

__all__ = [
    "NotificationClient",
    "NotificationChannel",
    "TelegramChannel",
    "get_notification_client",
    "send_notification_sync",
]
