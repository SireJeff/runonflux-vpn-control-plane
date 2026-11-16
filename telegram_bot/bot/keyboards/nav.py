from telegram import InlineKeyboardButton
from bot.keyboards.common import back_button, main_menu_button

# Reseller screen -> parent (callback_data of the parent screen).
PARENT = {
    "menu_users": "main_menu",
    "menu_wallet": "main_menu",
    "menu_connections": "main_menu",
    "menu_settings": "main_menu",
    "menu_packages": "main_menu",
    "menu_registrations": "main_menu",
    "menu_wire_orders": "main_menu",
    "menu_stats": "main_menu",
    "menu_pending_receipts": "main_menu",
}


def parent_of(screen: str) -> str:
    return PARENT.get(screen, "main_menu")


def nav_row(back_to: str | None, lang: str = "en", home: bool = True):
    """One nav row: [🔙 Back(back_to)] when back_to given + [🏠 Main Menu] when home."""
    row = []
    if back_to:
        row.append(back_button(back_to, lang))
    if home:
        row.append(main_menu_button(lang))
    return row
