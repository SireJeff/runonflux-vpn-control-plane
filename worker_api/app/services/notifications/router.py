"""Routes Telegram messages to the right bot based on recipient.

Admin notifications go via the platform bot token (settings.TELEGRAM_BOT_TOKEN).
End-user notifications go via the reseller admin's own bot token (AdminBot.bot_token_enc).
"""

import logging
from dataclasses import dataclass
from typing import Dict

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.crypto import decrypt_token
from app.models.admin_bots import AdminBot
from app.models.admin_users import AdminUser
from app.models.admins import Admin

logger = logging.getLogger(__name__)


@dataclass
class SendResult:
    status: str  # "sent" | "blocked" | "failed"
    retry_after: float | None = None


class NotificationRouter:
    """Routes messages to platform bot (admins) or reseller bot (end-users)."""

    def __init__(self, db: Session):
        self.db = db
        self._platform_token = settings.TELEGRAM_BOT_TOKEN
        self._bot_token_cache: Dict[int, str] = {}

    # ── Admin recipients (always platform bot) ────────────────────────

    def send_to_admin(self, admin_id: int, message: str) -> bool:
        """Send a message to an admin via the platform bot."""
        admin = self.db.query(Admin).filter(Admin.id == admin_id).first()
        if not admin or not admin.telegram_id:
            return False
        try:
            chat_id = int(admin.telegram_id)
        except (TypeError, ValueError):
            return False
        if not self._platform_token:
            return False
        return self._send(self._platform_token, chat_id, message)

    def send_to_super_admin(self, message: str) -> bool:
        """Send a message to the super admin via the platform bot."""
        sa = (
            self.db.query(Admin)
            .filter(Admin.username == settings.SUPER_ADMIN_USERNAME)
            .first()
        )
        return self.send_to_admin(sa.id, message) if sa else False

    # ── End-user recipients (always reseller bot) ──────────────────────

    def send_to_end_user(
        self,
        user_id: int,
        message: str,
        reply_markup=None,
    ) -> bool:
        """Send a message to an end-user via their reseller's bot.

        Optional ``reply_markup`` may be:
        - a python-telegram-bot ``InlineKeyboardMarkup`` (has ``.to_dict()``)
        - a plain dict already in Telegram API format
        """
        user = self.db.query(AdminUser).filter(AdminUser.id == user_id).first()
        if not user or not user.telegram_chat_id:
            return False
        bot = (
            self.db.query(AdminBot)
            .filter(
                AdminBot.admin_id == user.admin_id,
                AdminBot.is_active == True,
            )
            .first()
        )
        if not bot:
            return False
        token = self._get_bot_token(bot.id)
        return self._send(
            token, user.telegram_chat_id, message, reply_markup=reply_markup
        )

    # ── Dual routing (traffic alerts go to both parties) ──────────────

    def send_traffic_alert(self, user_id: int, message: str) -> None:
        """Send a traffic alert to both the end-user and their admin."""
        user = self.db.query(AdminUser).filter(AdminUser.id == user_id).first()
        if not user:
            return
        self.send_to_end_user(user_id, message)
        self.send_to_admin(user.admin_id, message)

    # ── Internal ──────────────────────────────────────────────────────

    def _get_bot_token(self, bot_id: int) -> str:
        """Decrypt and cache a bot token by bot ID."""
        if bot_id not in self._bot_token_cache:
            bot = self.db.query(AdminBot).filter(AdminBot.id == bot_id).first()
            if not bot:
                raise ValueError(f"Bot {bot_id} not found")
            self._bot_token_cache[bot_id] = decrypt_token(bot.bot_token_enc)
        return self._bot_token_cache[bot_id]

    @staticmethod
    def _send(token: str, chat_id: int, message: str, reply_markup=None) -> bool:
        """Low-level Telegram sendMessage. Synchronous, catches all exceptions.

        ``reply_markup`` is normalized into a Telegram-API-compatible dict:
        python-telegram-bot objects expose ``.to_dict()``; plain dicts pass
        through unchanged.
        """
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
        }
        if reply_markup is not None:
            if hasattr(reply_markup, "to_dict"):
                payload["reply_markup"] = reply_markup.to_dict()
            else:
                payload["reply_markup"] = reply_markup
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json=payload,
                )
                resp.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"Telegram send failed for chat {chat_id}: {e}")
            return False

    @staticmethod
    def send_raw(
        token: str,
        chat_id: int,
        text: str,
        reply_markup=None,
        parse_mode: str = "HTML",
    ) -> "SendResult":
        """Send one message and classify the outcome for broadcast accounting.

        200 -> sent; 403 -> blocked (user blocked the bot); 429 -> failed with
        retry_after (caller may re-send); any other status/exception -> failed.
        ``reply_markup`` may be a plain Telegram-API dict or a python-telegram-bot
        object exposing ``.to_dict()``.
        """
        payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
        if reply_markup is not None:
            if hasattr(reply_markup, "to_dict"):
                payload["reply_markup"] = reply_markup.to_dict()
            else:
                payload["reply_markup"] = reply_markup
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json=payload,
                )
            if resp.status_code == 200:
                return SendResult("sent")
            try:
                body = resp.json()
            except Exception:
                body = {}
            if resp.status_code == 403:
                return SendResult("blocked")
            if resp.status_code == 429:
                retry = (body.get("parameters") or {}).get("retry_after")
                return SendResult("failed", float(retry) if retry is not None else 1.0)
            logger.warning(
                f"Broadcast send to chat {chat_id} failed: "
                f"{resp.status_code} {body.get('description')}"
            )
            return SendResult("failed")
        except Exception as e:
            logger.error(f"Broadcast send raised for chat {chat_id}: {e}")
            return SendResult("failed")
