"""Reseller-facing API: bot configuration CRUD."""

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth.role_dependencies import RoleChecker
from app.core.crypto import decrypt_token, encrypt_token
from app.core.database import get_db
from app.models.admin_bots import AdminBot
from app.models.admins import Admin
from app.schemas.bot_config import (
    BotConfigResponse,
    BotConfigUpdateRequest,
    BotConfigUpsertRequest,
)
from app.services.bots.bot_lifecycle_service import (
    BotLifecycleError,
    build_webhook_url,
    delete_webhook,
    generate_webhook_secret,
    get_me,
    get_webhook_info,
    send_message,
    set_webhook,
)

if TYPE_CHECKING:
    from app.services.bots.reseller_bot_manager import ResellerBotManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/bot-config", tags=["Bot Config"])

# Injected on app startup (same pattern as webhook module)
_bot_manager: "Optional[ResellerBotManager]" = None


def configure_bot_manager(manager: "ResellerBotManager") -> None:
    """Called once on FastAPI startup to inject the ResellerBotManager."""
    global _bot_manager
    _bot_manager = manager


def _build_response(bot: AdminBot) -> BotConfigResponse:
    return BotConfigResponse(
        id=bot.id,
        admin_id=bot.admin_id,
        bot_username=bot.bot_username,
        bot_user_id=bot.bot_user_id,
        bot_display_name=bot.bot_display_name,
        welcome_message_fa=bot.welcome_message_fa,
        welcome_message_en=bot.welcome_message_en,
        card_number=bot.card_number,
        card_holder_name=bot.card_holder_name,
        crypto_address=bot.crypto_address,
        crypto_network=bot.crypto_network,
        crypto_memo=bot.crypto_memo,
        support_phone=bot.support_phone,
        support_telegram=bot.support_telegram,
        default_macro_region=bot.default_macro_region,
        is_active=bot.is_active,
        webhook_registered_at=bot.webhook_registered_at,
        created_at=bot.created_at,
    )


@router.get("", response_model=BotConfigResponse)
def get_bot_config(
    current: dict = Depends(RoleChecker(["admin", "super_admin"])),
    db: Session = Depends(get_db),
):
    bot = db.query(AdminBot).filter(AdminBot.admin_id == current["id"]).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not configured")
    return _build_response(bot)


@router.post("", response_model=BotConfigResponse, status_code=status.HTTP_201_CREATED)
async def register_bot(
    req: BotConfigUpsertRequest,
    current: dict = Depends(RoleChecker(["admin"])),
    db: Session = Depends(get_db),
):
    """Register or replace the reseller's bot."""
    existing = db.query(AdminBot).filter(AdminBot.admin_id == current["id"]).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Bot already registered. Use PUT to update fields, or deactivate first.",
        )

    # Validate token via getMe
    try:
        bot_info = await get_me(req.bot_token)
    except BotLifecycleError as e:
        raise HTTPException(status_code=422, detail=f"Invalid bot token: {e}")

    webhook_secret = generate_webhook_secret()

    # Insert row first (we need bot_id to build webhook URL)
    bot = AdminBot(
        admin_id=current["id"],
        bot_token_enc=encrypt_token(req.bot_token),
        bot_username=bot_info["username"],
        bot_user_id=bot_info["id"],
        bot_display_name=req.bot_display_name or bot_info.get("first_name"),
        welcome_message_fa=req.welcome_message_fa,
        welcome_message_en=req.welcome_message_en,
        card_number=req.card_number,
        card_holder_name=req.card_holder_name,
        crypto_address=req.crypto_address,
        crypto_network=req.crypto_network,
        crypto_memo=req.crypto_memo,
        support_phone=req.support_phone,
        support_telegram=req.support_telegram,
        default_macro_region=req.default_macro_region,
        webhook_secret=webhook_secret,
        is_active=True,
    )
    db.add(bot)
    db.commit()
    db.refresh(bot)

    # Register webhook with Telegram
    webhook_url = build_webhook_url(bot.id, db)
    try:
        await set_webhook(req.bot_token, webhook_url, webhook_secret)
    except BotLifecycleError as e:
        # Roll back -- token never goes live
        db.delete(bot)
        db.commit()
        raise HTTPException(status_code=502, detail=f"setWebhook failed: {e}")

    bot.webhook_registered_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    db.refresh(bot)

    return _build_response(bot)


@router.put("", response_model=BotConfigResponse)
def update_bot_config(
    req: BotConfigUpdateRequest,
    current: dict = Depends(RoleChecker(["admin"])),
    db: Session = Depends(get_db),
):
    """Update non-token fields (card, support, messages, region)."""
    bot = db.query(AdminBot).filter(AdminBot.admin_id == current["id"]).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not configured")

    update_data = req.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(bot, field, value)

    db.commit()
    db.refresh(bot)
    return _build_response(bot)


@router.post("/deactivate", response_model=BotConfigResponse)
async def deactivate_bot(
    current: dict = Depends(RoleChecker(["admin"])),
    db: Session = Depends(get_db),
):
    """Disable bot: deleteWebhook + is_active=False + evict from cache."""
    bot = db.query(AdminBot).filter(AdminBot.admin_id == current["id"]).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not configured")

    token = decrypt_token(bot.bot_token_enc)
    await delete_webhook(token)
    bot.is_active = False
    db.commit()
    db.refresh(bot)

    if _bot_manager is not None:
        await _bot_manager.evict(bot.id)

    return _build_response(bot)


@router.post("/reactivate", response_model=BotConfigResponse)
async def reactivate_bot(
    current: dict = Depends(RoleChecker(["admin"])),
    db: Session = Depends(get_db),
):
    """Re-enable a deactivated bot: set_webhook + is_active=True + cache restore."""
    bot = db.query(AdminBot).filter(AdminBot.admin_id == current["id"]).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not configured")
    if bot.is_active:
        raise HTTPException(
            status_code=409,
            detail="Bot is already active. Use PUT to update fields.",
        )

    token = decrypt_token(bot.bot_token_enc)
    webhook_url = build_webhook_url(bot.id, db)
    try:
        await set_webhook(token, webhook_url, bot.webhook_secret)
    except BotLifecycleError as e:
        raise HTTPException(status_code=502, detail=f"setWebhook failed: {e}")

    bot.is_active = True
    bot.webhook_registered_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    db.refresh(bot)

    if _bot_manager is not None:
        await _bot_manager.refresh(bot.id)

    return _build_response(bot)


@router.post("/test")
async def send_test_ping(
    current: dict = Depends(RoleChecker(["admin", "super_admin"])),
    db: Session = Depends(get_db),
):
    """Diagnose the reseller's OWN bot end-to-end.

    Checks their bot token (getMe), their webhook health (getWebhookInfo), and
    attempts a live DM through THEIR bot to the reseller's Telegram chat. This
    surfaces a broken reseller bot instead of silently pinging the platform bot
    (the old behaviour, which reported success even when the reseller's bot was
    completely dead).
    """
    admin: Admin = current["entity"]
    bot = db.query(AdminBot).filter(AdminBot.admin_id == current["id"]).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not configured")

    token = decrypt_token(bot.bot_token_enc)

    result: dict = {
        "ok": False,
        "bot_username": bot.bot_username,
        "webhook_url": None,
        "pending_update_count": None,
        "last_error_message": None,
        "dm_sent": False,
        "detail": "",
    }

    # 1. Token validity.
    try:
        me = await get_me(token)
        result["bot_username"] = me.get("username") or bot.bot_username
    except BotLifecycleError as e:
        result["detail"] = f"Bot token is invalid or was revoked in @BotFather: {e}"
        return result

    # 2. Webhook health (is Telegram pointed at us, any delivery errors?).
    try:
        wi = await get_webhook_info(token)
        result["webhook_url"] = wi.get("url") or None
        result["pending_update_count"] = wi.get("pending_update_count")
        result["last_error_message"] = wi.get("last_error_message") or None
    except BotLifecycleError:
        pass

    # 3. Live DM via the reseller's OWN bot (proves it can actually send).
    if admin.telegram_id:
        try:
            result["dm_sent"] = await send_message(
                token,
                int(admin.telegram_id),
                f"✅ Test message from your bot @{result['bot_username']}. "
                "If you can read this, your bot can message you.",
            )
        except (TypeError, ValueError):
            result["dm_sent"] = False

    # 4. Verdict + actionable guidance.
    if not result["webhook_url"]:
        result["detail"] = (
            "⚠️ Telegram is not pointed at our server, so your bot will not "
            "receive messages. Try Reactivate, or re-register the bot."
        )
    elif result["last_error_message"]:
        result["ok"] = True
        result["detail"] = (
            f"⚠️ Telegram reported a delivery error: "
            f"{result['last_error_message']} "
            f"(pending updates: {result['pending_update_count']}). "
            "This is often transient; if it persists, contact support."
        )
    elif admin.telegram_id and not result["dm_sent"]:
        result["ok"] = True
        result["detail"] = (
            "Your bot's webhook is healthy, but it could not message you. "
            "Open YOUR bot in Telegram and press Start, then test again."
        )
    else:
        result["ok"] = True
        result[
            "detail"
        ] = "✅ Your bot is working. A test message was sent to your Telegram."

    return result
