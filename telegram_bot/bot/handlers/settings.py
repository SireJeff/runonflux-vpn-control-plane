import logging

from telegram import InlineKeyboardButton, Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from bot.i18n.translator import t
from bot.keyboards.common import back_button, make_keyboard

logger = logging.getLogger(__name__)

LANGUAGE_NAMES = {"en": "English", "fa": "فارسی"}


async def menu_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show settings menu with current language and notification status."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("language", "en")
    notifications_enabled = context.user_data.get("notifications_enabled", True)

    language_display = LANGUAGE_NAMES.get(lang, lang)
    status_key = "settings_notifications_on" if notifications_enabled else "settings_notifications_off"
    notification_status = t(status_key, lang)

    text = (
        f"━━ {t('settings_title', lang)} ━━\n\n"
        f"{t('settings_language', lang, language=language_display)}\n"
        f"{t('settings_notifications', lang, status=notification_status)}"
    )

    keyboard = make_keyboard([
        [
            InlineKeyboardButton(t("btn_change_language", lang), callback_data="settings_language"),
            InlineKeyboardButton(t("btn_toggle_notifications", lang), callback_data="settings_toggle_notifications"),
        ],
        [back_button("main_menu", lang)],
    ])

    await query.edit_message_text(text, reply_markup=keyboard)


async def settings_language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show language selection grid."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("language", "en")

    text = t("language_select", lang)

    keyboard = make_keyboard([
        [
            InlineKeyboardButton(t("btn_english", lang), callback_data="lang_en"),
            InlineKeyboardButton(t("btn_persian", lang), callback_data="lang_fa"),
        ],
        [back_button("back_to_settings", lang)],
    ])

    await query.edit_message_text(text, reply_markup=keyboard)


async def set_language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set user language from callback data (lang_en or lang_fa)."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("language", "en")
    new_lang = query.data.split("_")[1]

    context.user_data["language"] = new_lang

    language_display = LANGUAGE_NAMES.get(new_lang, new_lang)
    text = t("language_changed", new_lang, language=language_display)

    keyboard = make_keyboard([[back_button("back_to_settings", new_lang)]])

    await query.edit_message_text(text, reply_markup=keyboard)


async def toggle_notifications_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle notifications on/off."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("language", "en")
    notifications_enabled = context.user_data.get("notifications_enabled", True)

    notifications_enabled = not notifications_enabled
    context.user_data["notifications_enabled"] = notifications_enabled

    status_key = "settings_notifications_on" if notifications_enabled else "settings_notifications_off"
    status_display = t(status_key, lang)
    text = t("notifications_toggled", lang, status=status_display)

    keyboard = make_keyboard([[back_button("back_to_settings", lang)]])

    await query.edit_message_text(text, reply_markup=keyboard)


async def back_to_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Re-show settings menu."""
    await menu_settings_callback(update, context)


def get_settings_handlers() -> list:
    return [
        CallbackQueryHandler(menu_settings_callback, pattern="^menu_settings$"),
        CallbackQueryHandler(settings_language_callback, pattern="^settings_language$"),
        CallbackQueryHandler(set_language_callback, pattern=r"^lang_(en|fa)$"),
        CallbackQueryHandler(toggle_notifications_callback, pattern="^settings_toggle_notifications$"),
        CallbackQueryHandler(back_to_settings_callback, pattern="^back_to_settings$"),
    ]
