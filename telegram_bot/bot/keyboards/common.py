from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from bot.i18n.translator import t


def make_button(text: str, callback_data: str, lang: str = "en") -> InlineKeyboardButton:
    return InlineKeyboardButton(text, callback_data=callback_data)


def make_keyboard(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(rows)


def back_button(callback: str, lang: str = "en") -> InlineKeyboardButton:
    return InlineKeyboardButton(t("btn_back", lang), callback_data=callback)


def cancel_button(lang: str = "en") -> InlineKeyboardButton:
    return InlineKeyboardButton(t("btn_cancel", lang), callback_data="cancel")


def main_menu_button(lang: str = "en") -> InlineKeyboardButton:
    return InlineKeyboardButton(t("btn_main_menu", lang), callback_data="main_menu")


def confirm_button(lang: str = "en") -> InlineKeyboardButton:
    return InlineKeyboardButton(t("btn_confirm", lang), callback_data="confirm")


def pagination_row(current_page: int, total_pages: int, prefix: str) -> list[InlineKeyboardButton]:
    buttons = []
    if current_page > 1:
        buttons.append(InlineKeyboardButton("◀", callback_data=f"{prefix}_page_{current_page - 1}"))
    buttons.append(InlineKeyboardButton(f"{current_page}/{total_pages}", callback_data="noop"))
    if current_page < total_pages:
        buttons.append(InlineKeyboardButton("▶", callback_data=f"{prefix}_page_{current_page + 1}"))
    return buttons


def approve_reject_keyboard(item_type: str, item_id: int, lang: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(t("btn_approve", lang), callback_data=f"approve_{item_type}_{item_id}"),
        InlineKeyboardButton(t("btn_reject", lang), callback_data=f"reject_{item_type}_{item_id}"),
    ]])


def back_keyboard(callback: str, lang: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[back_button(callback, lang)]])


def back_to_main_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[main_menu_button(lang)]])


def error_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[main_menu_button(lang)]])
