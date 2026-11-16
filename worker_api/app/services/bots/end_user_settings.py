"""End-user Settings + Support handlers (Task 17).

- settings_callback: show language picker
- lang_callback: persist language choice (fa/en), return to main menu
- support_callback: show reseller's support_telegram / support_phone

Read-heavy: only writes user.language on lang_callback. No FSM state.
"""

import logging

from telegram import InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

from app.core.database import SessionLocal
from app.models.admin_bots import AdminBot
from app.models.admin_users import AdminUser
from app.services.bots.end_user_keyboards import language_picker, main_menu

logger = logging.getLogger(__name__)


async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show language picker."""
    query = update.callback_query
    # Registered as a CallbackQueryHandler: PTB guarantees callback_query is set.
    assert query is not None
    await query.answer()
    await query.edit_message_text(
        "═══ ⚙️ تنظیمات ═══\nزبان را انتخاب کنید:",
        reply_markup=language_picker(),
    )


async def lang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Persist language choice and return to main menu."""
    query = update.callback_query
    # Registered as a CallbackQueryHandler: PTB guarantees callback_query is set.
    assert query is not None
    await query.answer()

    # Registered with pattern=r"^lang:", so PTB only dispatches here when
    # query.data matches that regex (i.e. is a non-None string).
    assert query.data is not None
    lang = query.data.split(":")[1]  # "fa" or "en"

    # A callback query always carries a sender; effective_user is only None
    # for update kinds (channel posts, polls, etc.) that can't reach a
    # CallbackQueryHandler.
    assert update.effective_user is not None

    admin_id = context.application.bot_data["admin_id"]
    db = SessionLocal()
    try:
        user = (
            db.query(AdminUser)
            .filter(
                AdminUser.admin_id == admin_id,
                AdminUser.telegram_id == update.effective_user.id,
            )
            .first()
        )
        if user:
            user.language = lang
            db.commit()
    finally:
        db.close()

    if lang == "fa":
        msg = "✅ زبان به فارسی تغییر یافت."
    else:
        msg = "✅ Language set to English."
    await query.edit_message_text(msg, reply_markup=main_menu(lang))


async def support_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show reseller's support contact info (telegram/phone)."""
    query = update.callback_query
    # Registered as a CallbackQueryHandler: PTB guarantees callback_query is set.
    assert query is not None
    await query.answer()

    bot_id = context.application.bot_data["bot_id"]
    admin_id = context.application.bot_data["admin_id"]
    # A callback query always carries a sender; resolve the user's language for
    # the nav row (support's parent is main_menu, so the footer stays home-only).
    assert update.effective_user is not None
    db = SessionLocal()
    try:
        user = (
            db.query(AdminUser)
            .filter(
                AdminUser.admin_id == admin_id,
                AdminUser.telegram_id == update.effective_user.id,
            )
            .first()
        )
        lang = getattr(user, "language", "fa") or "fa"
        bot = db.query(AdminBot).filter(AdminBot.id == bot_id).first()
        if not bot:
            await query.edit_message_text(
                "═══ 🎧 پشتیبانی ═══\n" "(اطلاعات پشتیبانی ثبت نشده است)"
            )
            return

        lines = ["═══ 🎧 پشتیبانی ═══"]
        if bot.support_telegram:
            lines.append(f"تلگرام: @{bot.support_telegram}")
        if bot.support_phone:
            lines.append(f"تلفن: {bot.support_phone}")
        if not (bot.support_telegram or bot.support_phone):
            lines.append("(اطلاعات پشتیبانی ثبت نشده است)")
        lines.append("")
        lines.append("برای بازگشت، منوی اصلی را بزنید.")

        from app.services.bots.end_user_keyboards import nav_footer

        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(nav_footer(lang)),
        )
    finally:
        db.close()


def register(application: Application) -> None:
    """Wire settings + support handlers into the Application."""
    application.add_handler(
        CallbackQueryHandler(settings_callback, pattern=r"^settings$")
    )
    application.add_handler(CallbackQueryHandler(lang_callback, pattern=r"^lang:"))
    application.add_handler(
        CallbackQueryHandler(support_callback, pattern=r"^support$")
    )
