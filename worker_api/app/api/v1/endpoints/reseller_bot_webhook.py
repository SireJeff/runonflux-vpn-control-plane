"""Single webhook receiver for ALL reseller bots.

Telegram sends updates here when our ``setWebhook`` registration points at:
    https://api.<DOMAIN>/bot/{bot_id}/webhook

We validate the X-Telegram-Bot-Api-Secret-Token header (timing-safe compare),
then dispatch the Update payload to the right Application.process_update().
"""

import hmac
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.admin_bots import AdminBot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bot", tags=["Reseller Bot Webhook"])

# Module-level singletons — set in main.py on app startup
_bot_manager = None


def configure_bot_manager(manager) -> None:
    """Called once on FastAPI startup to inject the ResellerBotManager."""
    global _bot_manager
    _bot_manager = manager


def _get_bot(db: Session, bot_id: int) -> Optional[AdminBot]:
    return (
        db.query(AdminBot)
        .filter(AdminBot.id == bot_id, AdminBot.is_active == True)
        .first()
    )


async def _process_update_async(payload: dict, bot_id: int) -> None:
    """Look up Application and feed the Update to it."""
    if _bot_manager is None:
        logger.error("Bot manager not configured")
        return
    from telegram import Update

    app = await _bot_manager.get_or_create_app(bot_id)
    update = Update.de_json(payload, app.bot)
    await app.process_update(update)


@router.post("/{bot_id}/webhook")
async def receive_webhook(
    bot_id: int,
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(
        ...,
        alias="X-Telegram-Bot-Api-Secret-Token",
    ),
):
    # Load the bot + read its webhook secret using a SHORT-LIVED session that
    # is closed BEFORE dispatching the update. process_update() runs the full
    # handler chain, which awaits slow Telegram API calls and opens its own
    # per-handler sessions; holding this pooled connection across all of that
    # was the cause of the 2026-09-10 QueuePool-exhaustion incident (reseller
    # bots timed out waiting on connections). Handlers manage their own DB
    # sessions, so we do not need one here past validation.
    db = SessionLocal()
    try:
        bot = _get_bot(db, bot_id)
        webhook_secret = bot.webhook_secret if bot is not None else None
    finally:
        db.close()

    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found")

    if webhook_secret is None or not hmac.compare_digest(
        x_telegram_bot_api_secret_token, webhook_secret
    ):
        raise HTTPException(status_code=401, detail="Invalid secret token")

    payload = await request.json()

    try:
        await _process_update_async(payload, bot_id)
    except Exception as e:
        # Telegram retries on non-2xx. We log and swallow to prevent
        # infinite retry loops on handler errors.
        logger.exception(f"Error processing update for bot {bot_id}: {e}")

    return {"ok": True}
