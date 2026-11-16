"""Super-admin endpoints for managing all reseller bots platform-wide.

These endpoints let the platform owner:
  - List every registered reseller bot (GET /super/bots)
  - Inspect Telegram's view of a bot's webhook (GET /super/bots/{id}/webhook-status)
  - Bulk-re-register webhooks after infrastructure changes (POST /super/bots/reactivate-all)

All endpoints require super_admin role. Reseller admins can only see/modify
their own bot via the /admin/bot-config/* endpoints.
"""
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth.role_dependencies import RoleChecker
from app.core.crypto import decrypt_token
from app.core.database import get_db
from app.models.admin_bots import AdminBot
from app.models.admins import Admin
from app.services.bots.bot_lifecycle_service import (
    BotLifecycleError,
    build_webhook_url,
    get_webhook_info,
    set_webhook,
)

if TYPE_CHECKING:
    from app.services.bots.reseller_bot_manager import ResellerBotManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/super/bots", tags=["Super Admin - Bots"])

# Injected on app startup (same pattern as bot_config_api.py)
_bot_manager: "Optional[ResellerBotManager]" = None


def configure_bot_manager(manager: "ResellerBotManager") -> None:
    global _bot_manager
    _bot_manager = manager


def _bot_to_response(bot: AdminBot, admin_username: Optional[str] = None) -> dict:
    return {
        "id": bot.id,
        "admin_id": bot.admin_id,
        "admin_username": admin_username,
        "bot_username": bot.bot_username,
        "bot_user_id": bot.bot_user_id,
        "bot_display_name": bot.bot_display_name,
        "default_macro_region": bot.default_macro_region,
        "is_active": bot.is_active,
        "webhook_registered_at": bot.webhook_registered_at,
        "created_at": bot.created_at,
    }


@router.get("")
def list_all_bots(
    current: dict = Depends(RoleChecker(["super_admin"])),
    db: Session = Depends(get_db),
):
    """List every reseller bot on the platform, newest first.

    Returns admin_username alongside each bot so the super-admin can see
    which reseller owns which bot without a second round-trip.
    """
    bots = db.query(AdminBot).order_by(AdminBot.id.desc()).all()
    out = []
    for bot in bots:
        admin = db.query(Admin).filter(Admin.id == bot.admin_id).first()
        out.append(
            _bot_to_response(bot, admin_username=admin.username if admin else None)
        )
    return {"bots": out, "count": len(out)}


@router.get("/{bot_id}/webhook-status")
async def get_bot_webhook_status(
    bot_id: int,
    current: dict = Depends(RoleChecker(["super_admin"])),
    db: Session = Depends(get_db),
):
    """Ask Telegram what URL it's currently POSTing updates to for this bot.

    Returns both the actual Telegram-side URL and our expected URL, so the
    caller can immediately see if they match. Also surfaces pending_update_count
    and last_error_message -- the key signals for "is this bot actually working?"
    """
    bot = db.query(AdminBot).filter(AdminBot.id == bot_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    try:
        token = decrypt_token(bot.bot_token_enc)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to decrypt bot token: {e}",
        )

    try:
        telegram_info = await get_webhook_info(token)
    except BotLifecycleError as e:
        raise HTTPException(
            status_code=502, detail=f"Telegram getWebhookInfo failed: {e}"
        )

    expected_url = build_webhook_url(bot.id, db)
    return {
        "bot_id": bot.id,
        "bot_username": bot.bot_username,
        "is_active": bot.is_active,
        "telegram_url": telegram_info.get("url", ""),
        "expected_url": expected_url,
        "url_matches": telegram_info.get("url", "") == expected_url,
        "pending_update_count": telegram_info.get("pending_update_count", 0),
        "last_error_date": telegram_info.get("last_error_date"),
        "last_error_message": telegram_info.get("last_error_message"),
    }


@router.post("/reactivate-all")
async def reactivate_all_bots(
    current: dict = Depends(RoleChecker(["super_admin"])),
    db: Session = Depends(get_db),
):
    """Re-register webhooks for every active bot, using the current build_webhook_url.

    Use this after deploying a fix to build_webhook_url or after migrating
    API domains. Bots that fail set_webhook are reported in `failures` but
    do not abort the operation -- you get a full report of what worked.
    """
    bots = db.query(AdminBot).filter(AdminBot.is_active == True).all()

    succeeded = 0
    failed = 0
    failures = []

    for bot in bots:
        try:
            token = decrypt_token(bot.bot_token_enc)
        except Exception as e:
            failed += 1
            failures.append(
                {
                    "bot_id": bot.id,
                    "bot_username": bot.bot_username,
                    "error": f"decrypt_token failed: {e}",
                }
            )
            logger.warning(f"reactivate_all: bot {bot.id} decrypt failed: {e}")
            continue

        webhook_url = build_webhook_url(bot.id, db)
        try:
            await set_webhook(token, webhook_url, bot.webhook_secret)
            bot.webhook_registered_at = datetime.now(timezone.utc).replace(tzinfo=None)
            succeeded += 1
        except BotLifecycleError as e:
            failed += 1
            failures.append(
                {
                    "bot_id": bot.id,
                    "bot_username": bot.bot_username,
                    "error": str(e),
                }
            )
            logger.warning(f"reactivate_all: bot {bot.id} failed: {e}")

    db.commit()

    # Refresh in-memory Application cache for all succeeded bots
    if _bot_manager is not None:
        for bot in bots:
            try:
                # Only refresh ones that succeeded -- failures didn't change state
                if not any(f["bot_id"] == bot.id for f in failures):
                    await _bot_manager.refresh(bot.id)
            except Exception as e:
                logger.warning(f"refresh manager for bot {bot.id}: {e}")

    return {
        "attempted": len(bots),
        "succeeded": succeeded,
        "failed": failed,
        "failures": failures,
    }
