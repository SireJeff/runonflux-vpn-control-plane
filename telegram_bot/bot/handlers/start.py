import logging

from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from bot.api.client import get_api
from bot.config import get_config
from bot.i18n.translator import t
from bot.keyboards.main_menu import (
    admin_menu_keyboard,
    guest_keyboard,
    pending_keyboard,
    superadmin_menu_keyboard,
)

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start -- detect role and show appropriate menu."""
    telegram_id = update.effective_user.id
    username = update.effective_user.username
    lang = context.user_data.get("language", "en")
    config = get_config()
    api = get_api()

    # Check if this telegram_id is linked to an admin. `username` lets the
    # backend self-heal admin rows whose telegram_id was stored as a handle.
    admin_info = await api.check_telegram_id(telegram_id, username)

    if not admin_info or not admin_info.get("found"):
        # Guest mode -- show telegram ID + registration link
        dashboard_url = config.ADMIN_DASHBOARD_URL
        text = t("welcome_guest", lang, user_id=telegram_id, dashboard_url=dashboard_url)
        keyboard = guest_keyboard(lang)
        context.user_data["role"] = "guest"

    elif admin_info.get("status") == "pending":
        # Pending approval
        text = t("welcome_pending", lang)
        keyboard = pending_keyboard(lang)
        context.user_data["role"] = "pending"

    elif admin_info.get("role") == "super_admin":
        # Super admin mode
        # Authenticate FIRST so subsequent API calls have a JWT
        await api.bot_login(telegram_id, username)
        name = admin_info.get("display_name", admin_info.get("username", "Admin"))
        text = t("welcome_superadmin", lang, name=name)
        # Fetch pending counts for badges
        pending_regs = await api.list_pending_admins(telegram_id)
        reg_count = len(pending_regs) if pending_regs else 0
        pending_orders = await api.list_wire_orders(telegram_id, "pending")
        order_count = 0
        if pending_orders and isinstance(pending_orders, dict):
            order_count = pending_orders.get("total", 0)
        elif pending_orders and isinstance(pending_orders, list):
            order_count = len(pending_orders)
        keyboard = superadmin_menu_keyboard(lang, reg_count, order_count)
        context.user_data["role"] = "super_admin"
        context.user_data["admin_id"] = admin_info.get("id")
        context.user_data["username"] = admin_info.get("username")

    else:
        # Regular admin (reseller) mode
        # Authenticate FIRST
        await api.bot_login(telegram_id, username)
        name = admin_info.get("display_name", admin_info.get("username", "Admin"))
        text = t("welcome_admin", lang, name=name)
        # Fetch pending receipts count for badge
        pending = await api.list_orders(telegram_id, "pending")
        pending_count = len(pending) if pending else 0
        keyboard = admin_menu_keyboard(lang, pending_count)
        context.user_data["role"] = "admin"
        context.user_data["admin_id"] = admin_info.get("id")
        context.user_data["username"] = admin_info.get("username")

    await update.effective_message.reply_text(text, reply_markup=keyboard)


async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Re-show the role-appropriate main menu."""
    query = update.callback_query
    await query.answer()

    telegram_id = update.effective_user.id
    username = update.effective_user.username
    lang = context.user_data.get("language", "en")
    api = get_api()

    admin_info = await api.check_telegram_id(telegram_id, username)

    if not admin_info or not admin_info.get("found"):
        text = t("welcome_guest", lang, user_id=telegram_id, dashboard_url=get_config().ADMIN_DASHBOARD_URL)
        keyboard = guest_keyboard(lang)
    elif admin_info.get("status") == "pending":
        text = t("welcome_pending", lang)
        keyboard = pending_keyboard(lang)
    elif admin_info.get("role") == "super_admin":
        await api.bot_login(telegram_id, username)
        name = admin_info.get("display_name", "")
        text = t("welcome_superadmin", lang, name=name)
        pending_regs = await api.list_pending_admins(telegram_id)
        reg_count = len(pending_regs) if pending_regs else 0
        pending_orders = await api.list_wire_orders(telegram_id, "pending")
        order_count = 0
        if pending_orders and isinstance(pending_orders, dict):
            order_count = pending_orders.get("total", 0)
        elif pending_orders and isinstance(pending_orders, list):
            order_count = len(pending_orders)
        keyboard = superadmin_menu_keyboard(lang, reg_count, order_count)
    else:
        name = admin_info.get("display_name", "")
        text = t("welcome_admin", lang, name=name)
        # Fetch pending receipts count for badge
        pending = await api.list_orders(telegram_id, "pending")
        pending_count = len(pending) if pending else 0
        keyboard = admin_menu_keyboard(lang, pending_count)

    await query.edit_message_text(text, reply_markup=keyboard)


def get_start_handlers() -> list:
    return [
        CommandHandler("start", start_command),
        CallbackQueryHandler(main_menu_callback, pattern="^main_menu$"),
    ]
