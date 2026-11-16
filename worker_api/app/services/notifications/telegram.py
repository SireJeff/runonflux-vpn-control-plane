"""
Telegram notification channel implementation
"""

import logging
from typing import TYPE_CHECKING, Any, Dict, Optional

import httpx

from app.core.config import settings

from .client import NotificationChannel

if TYPE_CHECKING:
    from app.models import User

logger = logging.getLogger(__name__)


class TelegramChannel(NotificationChannel):
    """Telegram notification channel using Bot API"""

    def __init__(self):
        self.bot_token = settings.TELEGRAM_BOT_TOKEN
        if not self.bot_token:
            logger.warning("Telegram bot token not configured")
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}/"

    async def send(
        self,
        user: "User",
        message: str,
        data: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> bool:
        """
        Send a Telegram message to user

        Args:
            user: Target user
            message: Message text
            data: Additional data (not used for Telegram)
            **kwargs: Additional parameters

        Returns:
            bool: True if message was sent successfully
        """
        if not self.bot_token or not user.telegram_user_id:
            logger.warning("Telegram bot token or user ID missing")
            return False

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    f"{self.api_url}sendMessage",
                    json={
                        "chat_id": user.telegram_user_id,
                        "text": message,
                        "parse_mode": "Markdown",
                        **kwargs,
                    },
                )
                response.raise_for_status()
                logger.info(f"Telegram message sent to user {user.id}")
                return True

        except httpx.RequestError as e:
            logger.error(f"Telegram API request failed: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending Telegram message: {str(e)}")
            return False

    async def send_inline_keyboard(
        self,
        user: "User",
        message: str,
        keyboard_data: Dict[str, Any],
        data: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> bool:
        """
        Send a Telegram message with inline keyboard

        Args:
            user: Target user
            message: Message text
            keyboard_data: Keyboard configuration
            data: Additional data (not used for Telegram)
            **kwargs: Additional parameters

        Returns:
            bool: True if message was sent successfully
        """
        if not self.bot_token or not user.telegram_user_id:
            logger.warning("Telegram bot token or user ID missing")
            return False

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    f"{self.api_url}sendMessage",
                    json={
                        "chat_id": user.telegram_user_id,
                        "text": message,
                        "parse_mode": "Markdown",
                        "reply_markup": {"inline_keyboard": [keyboard_data["buttons"]]},
                        **kwargs,
                    },
                )
                response.raise_for_status()
                logger.info(f"Telegram message with keyboard sent to user {user.id}")
                return True

        except httpx.RequestError as e:
            logger.error(f"Telegram API request failed: {str(e)}")
            return False
        except Exception as e:
            logger.error(
                f"Unexpected error sending Telegram message with keyboard: {str(e)}"
            )
            return False
