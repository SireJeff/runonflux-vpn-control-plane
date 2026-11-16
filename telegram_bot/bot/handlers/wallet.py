import logging
from datetime import datetime

from telegram import InlineKeyboardButton, Update
from telegram.ext import (
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bot.api.client import get_api
from bot.i18n.translator import t
from bot.keyboards.common import back_button, make_keyboard, pagination_row

logger = logging.getLogger(__name__)

WAITING_AMOUNT, WAITING_CONTACT, WAITING_CONFIRM = range(3)


def _format_tx(tx: dict, lang: str) -> str:
    """Format a single transaction for display."""
    amount = float(tx.get("amount", 0))
    tx_type = tx.get("type", "Unknown")
    date_str = tx.get("created_at", "")

    if date_str:
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            date_display = dt.strftime("%b %d")
        except (ValueError, AttributeError):
            date_display = date_str[:10]
    else:
        date_display = ""

    amount_display = f"{abs(amount):.2f}"
    if amount >= 0:
        return t("wallet_tx_credit", lang, amount=amount_display, type=tx_type, date=date_display)
    else:
        return t("wallet_tx_debit", lang, amount=amount_display, type=tx_type, date=date_display)


async def menu_wallet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show wallet overview: balance + last 5 transactions."""
    query = update.callback_query
    await query.answer()

    telegram_id = update.effective_user.id
    lang = context.user_data.get("language", "en")
    api = get_api()

    wallet_data = await api.get_wallet(telegram_id)
    if not wallet_data:
        await query.edit_message_text(t("error_general", lang))
        return

    balance = wallet_data.get("balance", "0.00")
    if isinstance(balance, (int, float)):
        balance = f"{balance:.2f}"

    lines = [
        t("wallet_title", lang),
        t("wallet_balance", lang, balance=balance),
        "",
        t("wallet_recent", lang),
    ]

    recent = wallet_data.get("recent_transactions", [])
    for tx in recent[:5]:
        lines.append(_format_tx(tx, lang))

    if not recent:
        lines.append(t("no_data", lang))

    text = "\n".join(lines)

    keyboard = make_keyboard([
        [
            InlineKeyboardButton(t("btn_wire_order", lang), callback_data="wire_order_start"),
        ],
        [
            InlineKeyboardButton(t("btn_full_history", lang), callback_data="wallet_history"),
        ],
        [
            back_button("main_menu", lang),
        ],
    ])

    await query.edit_message_text(text, reply_markup=keyboard)


async def wallet_history_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show paginated transaction history (page 1)."""
    await _show_history_page(update, context, page=1)


async def wallet_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle pagination callback for wallet history."""
    query = update.callback_query
    await query.answer()

    try:
        page = int(query.data.split("_")[-1])
    except (ValueError, IndexError):
        page = 1

    await _show_history_page(update, context, page=page)


async def _show_history_page(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int) -> None:
    """Render one page of transaction history."""
    query = update.callback_query
    telegram_id = update.effective_user.id
    lang = context.user_data.get("language", "en")
    api = get_api()

    result = await api.get_wallet_transactions(telegram_id, page=page)
    if not result:
        await query.edit_message_text(t("error_general", lang))
        return

    items = result.get("items", [])
    total = result.get("total", 0)

    # Calculate total pages (10 items per page)
    total_pages = max(1, (total + 9) // 10) if total > 0 else 1

    lines = [t("history_title", lang, total=total), ""]

    for tx in items:
        lines.append(_format_tx(tx, lang))

    if not items:
        lines.append(t("no_data", lang))

    text = "\n".join(lines)

    rows = []
    if total_pages > 1:
        rows.append(pagination_row(page, total_pages, "wallet"))
    rows.append([back_button("menu_wallet", lang)])

    await query.edit_message_text(text, reply_markup=make_keyboard(rows))


# --- Wire Order ConversationHandler ---

async def wire_order_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for wire order flow: prompt for amount."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("language", "en")
    prompt = t("wire_order_prompt_amount", lang)

    keyboard = make_keyboard([[
        InlineKeyboardButton(t("btn_cancel", lang), callback_data="cancel"),
    ]])

    await query.edit_message_text(prompt, reply_markup=keyboard)
    return WAITING_AMOUNT


async def receive_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive and validate the wire order amount."""
    lang = context.user_data.get("language", "en")
    text = update.message.text.strip()

    try:
        amount = int(text.replace(",", "").replace(".", "").strip())
    except ValueError:
        await update.message.reply_text(t("wire_order_invalid_amount", lang))
        return WAITING_AMOUNT

    if amount < 500000:
        await update.message.reply_text(t("wire_order_invalid_amount", lang))
        return WAITING_AMOUNT

    context.user_data["wire_amount"] = amount

    keyboard = make_keyboard([[
        InlineKeyboardButton(t("btn_cancel", lang), callback_data="cancel"),
    ]])

    await update.message.reply_text(
        t("wire_order_prompt_contact", lang),
        reply_markup=keyboard,
    )
    return WAITING_CONTACT


async def receive_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive contact info and show confirmation."""
    lang = context.user_data.get("language", "en")
    contact = update.message.text.strip()

    amount = context.user_data.get("wire_amount", 0)

    confirm_text = t("wire_order_confirm", lang, amount=f"{amount:,}", contact=contact)

    keyboard = make_keyboard([
        [
            InlineKeyboardButton(t("btn_confirm", lang), callback_data="confirm_wire_order"),
            InlineKeyboardButton(t("btn_cancel", lang), callback_data="cancel"),
        ],
    ])

    await update.message.reply_text(confirm_text, reply_markup=keyboard)
    return WAITING_CONFIRM


async def confirm_wire_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Submit the wire order via API."""
    query = update.callback_query
    await query.answer()

    telegram_id = update.effective_user.id
    lang = context.user_data.get("language", "en")
    api = get_api()

    amount = context.user_data.pop("wire_amount", 0)
    contact = context.user_data.pop("wire_contact", "")

    result = await api.submit_wire_order(telegram_id, {
        "amount_tomans": amount,
        "contact": contact,
    })

    if result:
        text = t("wire_order_submitted", lang)
    else:
        text = t("error_general", lang)

    keyboard = make_keyboard([[back_button("menu_wallet", lang)]])

    # Edit the confirmation message (the one with Confirm/Cancel buttons)
    await query.edit_message_text(text, reply_markup=keyboard)
    return ConversationHandler.END


async def cancel_wire_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel wire order flow and return to wallet menu."""
    query = update.callback_query
    await query.answer()

    # Clear any stored wire order data
    context.user_data.pop("wire_amount", None)
    context.user_data.pop("wire_contact", None)

    # Show wallet menu again
    await menu_wallet_callback(update, context)
    return ConversationHandler.END


def get_wallet_handlers() -> list:
    return [
        CallbackQueryHandler(menu_wallet_callback, pattern="^menu_wallet$"),
        CallbackQueryHandler(wallet_history_callback, pattern="^wallet_history$"),
        CallbackQueryHandler(wallet_page_callback, pattern=r"^wallet_page_(\d+)$"),
        ConversationHandler(
            entry_points=[CallbackQueryHandler(wire_order_start, pattern="^wire_order_start$")],
            states={
                WAITING_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_amount)],
                WAITING_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_contact)],
                WAITING_CONFIRM: [CallbackQueryHandler(confirm_wire_order, pattern="^confirm_wire_order$")],
            },
            fallbacks=[
                CallbackQueryHandler(cancel_wire_order, pattern="^cancel$"),
                CallbackQueryHandler(cancel_wire_order, pattern="^menu_wallet$"),
            ],
            per_message=False,
        ),
    ]
