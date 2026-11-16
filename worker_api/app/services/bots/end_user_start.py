"""End-user /start handler — auto-registers on first contact.

Tasks 15-18 will extend register_end_user_handlers with purchase,
connections, settings, and referral handlers respectively.
"""

import logging
import secrets

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from app.core.auth.password import set_password
from app.core.database import SessionLocal
from app.models.admin_bots import AdminBot
from app.models.admin_users import AdminUser
from app.services.bots.end_user_keyboards import main_menu
from app.services.credentials.username_generator import generate_unique_username
from app.services.notifications.templates_fa import format_user_welcome

logger = logging.getLogger(__name__)


def _menu_caption(lang: str) -> str:
    return "منو اصلی:" if lang == "fa" else "Main menu:"


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start — auto-register end-user if first contact."""
    bot_data = context.application.bot_data
    admin_id = bot_data["admin_id"]
    bot_id = bot_data["bot_id"]

    tg_user = update.effective_user
    tg_chat = update.effective_chat
    tg_message = update.effective_message
    # CommandHandler("start", ...) only fires on incoming text messages,
    # which always carry a sender, a chat, and the message object itself.
    assert tg_user is not None
    assert tg_chat is not None
    assert tg_message is not None

    db: Session = SessionLocal()
    try:
        bot = db.query(AdminBot).filter(AdminBot.id == bot_id).first()
        if not bot:
            await tg_message.reply_text("Bot not configured.")
            return

        user = (
            db.query(AdminUser)
            .filter(
                AdminUser.admin_id == admin_id,
                AdminUser.telegram_id == tg_user.id,
            )
            .first()
        )
        if not user:
            try:
                username = generate_unique_username(db, admin_id)
            except RuntimeError:
                logger.exception(
                    "username generation exhausted for admin_id=%s on /start",
                    admin_id,
                )
                await tg_message.reply_text(
                    "⚠️ Something went wrong. Please tap /start to try again."
                )
                return
            portal_pw = secrets.token_urlsafe(6)[:8]

            user = AdminUser(
                admin_id=admin_id,
                username=username,
                # password_hash + password_enc set below via set_password
                # to maintain the dual-storage invariant (verify + display).
                display_name=(tg_user.first_name or None),
                status="lead",
                telegram_id=tg_user.id,
                telegram_chat_id=tg_chat.id,
                registered_bot_id=bot_id,
                language="fa",
                # Token used in /api/v1/user/sub/<token> subscription URLs.
                # Generated at creation so display paths always have a value.
                subscription_token=secrets.token_hex(16),
            )
            set_password(user, portal_pw)
            db.add(user)
            db.commit()
            db.refresh(user)
            logger.info(
                f"Auto-registered end-user {user.id} ({username}) on bot {bot_id}"
            )

        user.telegram_chat_id = tg_chat.id

        # Deep-link referral: parse /start ref_XXX (t.me/<bot>?start=ref_CODE)
        if context.args and context.args[0].startswith("ref_"):
            ref_code = context.args[0][4:]
            referrer = (
                db.query(AdminUser)
                .filter(
                    AdminUser.admin_id == admin_id,
                    AdminUser.referral_code == ref_code,
                )
                .first()
            )
            if referrer and referrer.id != user.id and not user.referred_by_user_id:
                user.referred_by_user_id = referrer.id
                logger.info(f"User {user.id} referred by {referrer.id} via deep-link")

        db.commit()

        # Deep-link straight to the referral view: t.me/<bot>?start=referral
        # (used by broadcast CTA buttons). Show it and stop before the menu.
        if context.args and context.args[0] == "referral":
            from app.services.bots.end_user_referral import open_referral_from_start

            await open_referral_from_start(update, context)
            return

        display_name = bot.bot_display_name or "FluxVPN"
        custom_welcome = bot.welcome_message_fa
        if custom_welcome:
            welcome = custom_welcome
        else:
            welcome = format_user_welcome(
                bot_display_name=display_name,
                first_name=tg_user.first_name or "",
            )
        lang = getattr(user, "language", "fa") or "fa"
        from app.services.free_config.free_config_service import FreeConfigService
        from app.services.free_config.policy import resolve_free_config_policy

        show_free_config = (
            resolve_free_config_policy(db, admin_id).enabled
            or FreeConfigService(db).get_or_create(admin_id).is_enabled
        )
        await tg_message.reply_text(
            welcome,
            reply_markup=main_menu(lang, show_free_config=show_free_config),
        )
    finally:
        db.close()


async def main_menu_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Re-show main menu when user taps a 'back' button."""
    query = update.callback_query
    # CallbackQueryHandler guarantees the update carries a callback_query,
    # and a callback query always has a from_user.
    assert query is not None
    tg_user = update.effective_user
    assert tg_user is not None
    await query.answer()
    # Returning to the main menu cancels any in-progress wallet top-up flow,
    # so clear its transient state to avoid stale awaiting_* keys.
    if context.user_data is not None:
        from app.services.bots.end_user_wallet import clear_flow_state

        clear_flow_state(context.user_data)
    bot_data = context.application.bot_data
    admin_id = bot_data["admin_id"]
    bot_id = bot_data["bot_id"]

    db = SessionLocal()
    try:
        bot = db.query(AdminBot).filter(AdminBot.id == bot_id).first()
        user = (
            db.query(AdminUser)
            .filter(
                AdminUser.admin_id == admin_id,
                AdminUser.telegram_id == tg_user.id,
            )
            .first()
        )
        lang = getattr(user, "language", "fa") or "fa"
        display_name = bot.bot_display_name if bot else "FluxVPN"
        from app.services.free_config.free_config_service import FreeConfigService
        from app.services.free_config.policy import resolve_free_config_policy

        show_free_config = (
            resolve_free_config_policy(db, admin_id).enabled
            or FreeConfigService(db).get_or_create(admin_id).is_enabled
        )
        await query.edit_message_text(
            f"═══ 🔐 {display_name} ═══\n" + _menu_caption(lang),
            reply_markup=main_menu(lang, show_free_config=show_free_config),
        )
    finally:
        db.close()


def register_end_user_handlers(application: Application) -> None:
    """Wire end-user handlers into the given Application.

    Called by ResellerBotManager.get_or_create_app() on each bot.

    Task 14: /start + main_menu callback.
    Task 15: purchase flow (buy/package/region callbacks + receipt photo).
    Task 16: my-subscription + my-connections views.
    Task 17: settings (language toggle) + support contact display.
    Task 18: referral view + /start ref_XXX deep-link referrer linkage.
    """
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(
        CallbackQueryHandler(main_menu_callback, pattern=r"^main_menu$")
    )

    from app.services.bots.end_user_pagination import noop_callback

    application.add_handler(CallbackQueryHandler(noop_callback, pattern=r"^noop$"))

    from app.services.bots.end_user_purchase import register as register_purchase

    register_purchase(application)

    from app.services.bots.end_user_connections import register as register_connections

    register_connections(application)

    from app.services.bots.end_user_settings import register as register_settings

    register_settings(application)

    from app.services.bots.end_user_referral import register as register_referral

    register_referral(application)

    from app.services.bots.end_user_guides import register as register_guides

    register_guides(application)

    from app.services.bots.end_user_orders import register as register_orders

    register_orders(application)

    from app.services.bots.end_user_wallet import register_wallet

    register_wallet(application)

    from app.services.bots.end_user_free_config import register_free_config

    register_free_config(application)
