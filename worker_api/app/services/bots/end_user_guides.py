"""Per-platform setup guides (Android / iOS / Windows).

Each handler opens when user taps the corresponding button from the hero
message or My Connections view. Uses templates from templates_fa/en.py
to render the message; download URLs come from settings (per-deployment).
"""

import logging

from telegram import InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.admin_users import AdminUser
from app.services.notifications.templates_fa import template_for

logger = logging.getLogger(__name__)


def _android_urls() -> dict:
    return {
        "throne": settings.THRONE_ANDROID_URL,
        "hiddify": settings.HIDDIFY_ANDROID_URL,
        "nekobox": settings.NEKOBOX_ANDROID_URL,
    }


def _ios_urls() -> dict:
    return {
        "throne": settings.THRONE_IOS_URL,
        "hiddify": settings.HIDDIFY_IOS_URL,
        "streisand": settings.STREISAND_IOS_URL,
    }


def _windows_urls() -> dict:
    return {
        "throne": settings.THRONE_WINDOWS_URL,
        "nekoray": settings.NEKORAY_WINDOWS_URL,
        "hiddify": settings.HIDDIFY_WINDOWS_URL,
    }


async def _user_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    admin_id = context.application.bot_data["admin_id"]
    # Reached only via the CallbackQueryHandler guide flow; a callback query
    # always carries a user, so effective_user is present.
    tg_user = update.effective_user
    assert tg_user is not None
    db = SessionLocal()
    try:
        user = (
            db.query(AdminUser)
            .filter(
                AdminUser.admin_id == admin_id,
                AdminUser.telegram_id == tg_user.id,
            )
            .first()
        )
        return getattr(user, "language", "fa") or "fa"
    finally:
        db.close()


async def _render_guide(update, context, platform: str) -> None:
    """Common rendering path for all 3 platforms."""
    query = update.callback_query
    await query.answer()
    lang = await _user_lang(update, context)
    tpl = template_for(lang)

    if platform == "android":
        msg = tpl.format_guide_android(_android_urls())
    elif platform == "ios":
        msg = tpl.format_guide_ios(_ios_urls())
    elif platform == "windows":
        msg = tpl.format_guide_windows(_windows_urls())
    else:
        logger.warning(f"Unknown guide platform: {platform}")
        return

    from app.services.bots.end_user_keyboards import nav_footer

    kb = InlineKeyboardMarkup(nav_footer(lang, back_to="my_sub"))
    await query.edit_message_text(msg, reply_markup=kb)


async def guide_android_callback(update, context):
    """Show Android setup guide."""
    await _render_guide(update, context, "android")


async def guide_ios_callback(update, context):
    """Show iOS setup guide."""
    await _render_guide(update, context, "ios")


async def guide_windows_callback(update, context):
    """Show Windows setup guide."""
    await _render_guide(update, context, "windows")


def register(application: Application) -> None:
    """Register all 3 guide handlers. Called from register_end_user_handlers."""
    application.add_handler(
        CallbackQueryHandler(guide_android_callback, pattern=r"^guide:android$")
    )
    application.add_handler(
        CallbackQueryHandler(guide_ios_callback, pattern=r"^guide:ios$")
    )
    application.add_handler(
        CallbackQueryHandler(guide_windows_callback, pattern=r"^guide:windows$")
    )
