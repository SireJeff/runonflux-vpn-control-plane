"""Telegram setWebhook/deleteWebhook/getMe helpers."""

import logging
import secrets
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class BotLifecycleError(Exception):
    """Raised when Telegram calls fail during bot registration."""


async def get_me(bot_token: str) -> dict:
    """Call /getMe to validate token and fetch bot metadata."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"https://api.telegram.org/bot{bot_token}/getMe")
    if resp.status_code != 200:
        raise BotLifecycleError(f"getMe failed: HTTP {resp.status_code}")
    data = resp.json()
    if not data.get("ok"):
        raise BotLifecycleError(f"getMe returned !ok: {data}")
    return data["result"]


async def set_webhook(bot_token: str, webhook_url: str, secret_token: str) -> None:
    """Register our webhook URL with Telegram for this bot."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"https://api.telegram.org/bot{bot_token}/setWebhook",
            json={
                "url": webhook_url,
                "secret_token": secret_token,
                "allowed_updates": [
                    "message",
                    "callback_query",
                    "pre_checkout_query",
                ],
                "drop_pending_updates": True,
            },
        )
    if resp.status_code != 200 or not resp.json().get("ok"):
        raise BotLifecycleError(f"setWebhook failed: {resp.status_code} {resp.text}")


async def delete_webhook(bot_token: str) -> None:
    """Remove webhook registration (called on bot disable)."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"https://api.telegram.org/bot{bot_token}/deleteWebhook"
        )
    if resp.status_code != 200:
        logger.warning(f"deleteWebhook returned {resp.status_code}")


async def get_webhook_info(bot_token: str) -> dict:
    """Fetch the bot's current webhook config from Telegram.

    Returns the 'result' dict containing: url, has_custom_certificate,
    pending_update_count, max_connections, ip_address, last_error_date,
    last_error_message. Used for diagnostics — checking whether Telegram
    is actually pointed at our receiver, and whether deliveries are failing.
    """
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"https://api.telegram.org/bot{bot_token}/getWebhookInfo"
        )
    if resp.status_code != 200:
        raise BotLifecycleError(
            f"getWebhookInfo failed: HTTP {resp.status_code} {resp.text}"
        )
    data = resp.json()
    if not data.get("ok"):
        raise BotLifecycleError(f"getWebhookInfo returned !ok: {data}")
    return data["result"]


async def send_message(bot_token: str, chat_id: int, text: str) -> bool:
    """Send a Telegram message via the given bot token.

    Returns True only when Telegram accepts the message (HTTP 200 + ok=True).
    Used by the Bot Config "test ping" to prove the reseller's OWN bot can
    deliver a message to the reseller. Never raises — a False result is the
    signal (e.g. the reseller hasn't pressed Start in their own bot).
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": text},
            )
        return resp.status_code == 200 and bool(resp.json().get("ok"))
    except Exception as exc:  # network error, bad chat, etc.
        logger.warning("send_message failed for chat %s: %s", chat_id, exc)
        return False


def generate_webhook_secret() -> str:
    """URL-safe secret for X-Telegram-Bot-Api-Secret-Token validation."""
    return secrets.token_urlsafe(32)


def build_webhook_url(bot_id: int, db) -> str:
    """Build the public URL Telegram should send updates to.

    Uses get_api_base_url (worker-api domain), NOT get_dashboard_base_url
    (Next.js panel domain). The webhook receiver is a FastAPI route, so it
    must land on the API host that Traefik routes to the worker-api container.
    """
    from app.services.url_resolver import get_api_base_url

    base = get_api_base_url(db)
    return f"{base.rstrip('/')}/bot/{bot_id}/webhook"


def _bot_token_for_admin(db, admin_id: int) -> Optional[str]:
    """Decrypt and return bot token for an admin's bot."""
    from app.core.crypto import decrypt_token
    from app.models.admin_bots import AdminBot

    bot = db.query(AdminBot).filter(AdminBot.admin_id == admin_id).first()
    return decrypt_token(bot.bot_token_enc) if bot else None
