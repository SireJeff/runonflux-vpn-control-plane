from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from bot.i18n.translator import t


def guest_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    """Guest users see only a main menu button (after registration prompt)."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(t("btn_main_menu", lang), callback_data="main_menu"),
    ]])


def pending_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    """Pending admin sees just a main menu button."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(t("btn_main_menu", lang), callback_data="main_menu"),
    ]])


def admin_menu_keyboard(lang: str = "en", pending_receipts_count: int = 0) -> InlineKeyboardMarkup:
    """Active admin (reseller) main menu."""
    rows = []
    if pending_receipts_count > 0:
        rows.append([
            InlineKeyboardButton(
                t("menu_pending_receipts", lang, count=pending_receipts_count),
                callback_data="menu_pending_receipts",
            ),
        ])
    rows.append([
        InlineKeyboardButton(t("menu_users", lang), callback_data="menu_users"),
        InlineKeyboardButton(t("menu_wallet", lang), callback_data="menu_wallet"),
    ])
    rows.append([
        InlineKeyboardButton(t("menu_connections", lang), callback_data="menu_connections"),
        InlineKeyboardButton(t("menu_settings", lang), callback_data="menu_settings"),
    ])
    rows.append([
        InlineKeyboardButton("📦 پلن‌ها", callback_data="menu_packages"),
    ])
    return InlineKeyboardMarkup(rows)


def superadmin_menu_keyboard(
    lang: str = "en",
    pending_regs: int = 0,
    pending_orders: int = 0,
) -> InlineKeyboardMarkup:
    """Super admin main menu with badge counts."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                t("menu_registrations", lang, count=pending_regs),
                callback_data="menu_registrations",
            ),
            InlineKeyboardButton(
                t("menu_wire_orders", lang, count=pending_orders),
                callback_data="menu_wire_orders",
            ),
        ],
        [
            InlineKeyboardButton(t("menu_stats", lang), callback_data="menu_stats"),
            InlineKeyboardButton(t("menu_settings", lang), callback_data="menu_settings"),
        ],
    ])
