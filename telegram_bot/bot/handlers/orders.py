import io
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from bot.api.client import get_api
from bot.i18n.translator import get_translator, t
from bot.keyboards.common import back_button, main_menu_button

logger = logging.getLogger(__name__)

MAX_ORDERS_PER_LIST = 10


async def pending_receipts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show list of pending end-user orders with approve/reject/view-receipt buttons."""
    query = update.callback_query
    await query.answer()

    telegram_id = update.effective_user.id
    lang = context.user_data.get("language", "en")
    api = get_api()

    orders = await api.list_orders(telegram_id, "pending")

    if not orders:
        await query.edit_message_text(
            t("pending_receipts_empty", lang),
            reply_markup=InlineKeyboardMarkup([[main_menu_button(lang)]]),
        )
        return

    # Cap at MAX_ORDERS_PER_LIST to avoid rate limits
    total = len(orders)
    capped = orders[:MAX_ORDERS_PER_LIST]

    for order in capped:
        order_id = order.get("id")
        username = order.get("username", order.get("user_username", "-"))
        package_name = "-"
        snapshot = order.get("package_snapshot")
        if isinstance(snapshot, dict):
            package_name = snapshot.get("name", "-")
        amount_raw = order.get("amount_tomans", "0")
        try:
            amount_int = int(float(str(amount_raw)))
        except (ValueError, TypeError):
            amount_int = 0

        translator = get_translator()
        amount_display = translator.format_number(amount_int, lang)

        text = t(
            "pending_receipt_item",
            lang,
            order_id=order_id,
            username=username,
            package_name=package_name,
            amount=amount_display,
        )

        has_receipt = bool(order.get("receipt_local_path"))

        buttons = []
        row1 = []
        row2 = []
        if has_receipt:
            row1.append(InlineKeyboardButton(
                t("btn_view_receipt", lang),
                callback_data=f"view_receipt:{order_id}",
            ))
        row1.append(InlineKeyboardButton(
            t("btn_approve", lang),
            callback_data=f"approve_order:{order_id}",
        ))
        row1.append(InlineKeyboardButton(
            t("btn_reject", lang),
            callback_data=f"reject_order:{order_id}",
        ))
        buttons.append(row1)

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    # If there were more orders than shown, add a note
    if total > MAX_ORDERS_PER_LIST:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=t("pending_receipts_capped", lang, total=total),
        )

    # Edit the original menu message to remove the button (prevent re-triggering)
    await query.edit_message_reply_markup(reply_markup=None)


async def approve_order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Approve a pending order."""
    query = update.callback_query
    await query.answer()

    telegram_id = update.effective_user.id
    lang = context.user_data.get("language", "en")
    api = get_api()

    try:
        order_id = int(query.data.split(":")[1])
    except (ValueError, IndexError):
        logger.warning(f"Could not parse order_id from callback_data: {query.data}")
        return

    # Strip action buttons BEFORE the API call to close the double-tap race window.
    # If the API call fails, the user re-opens the pending list to retry.
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception as e:
        logger.warning(f"Could not strip reply markup: {e}")

    result = await api.approve_order(telegram_id, order_id)

    if result:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=t("order_approved", lang, order_id=order_id),
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=t("order_action_error", lang, error="approve failed"),
        )


async def reject_order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reject a pending order."""
    query = update.callback_query
    await query.answer()

    telegram_id = update.effective_user.id
    lang = context.user_data.get("language", "en")
    api = get_api()

    try:
        order_id = int(query.data.split(":")[1])
    except (ValueError, IndexError):
        logger.warning(f"Could not parse order_id from callback_data: {query.data}")
        return

    # Strip action buttons BEFORE the API call to close the double-tap race window.
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception as e:
        logger.warning(f"Could not strip reply markup: {e}")

    result = await api.reject_order(telegram_id, order_id, reason=None)

    if result:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=t("order_rejected", lang, order_id=order_id),
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=t("order_action_error", lang, error="reject failed"),
        )


async def view_receipt_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """View the receipt image for an order."""
    query = update.callback_query
    await query.answer()

    telegram_id = update.effective_user.id
    lang = context.user_data.get("language", "en")
    api = get_api()

    try:
        order_id = int(query.data.split(":")[1])
    except (ValueError, IndexError):
        logger.warning(f"Could not parse order_id from callback_data: {query.data}")
        return

    receipt_bytes = await api.get_order_receipt_bytes(telegram_id, order_id)

    if receipt_bytes:
        try:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=io.BytesIO(receipt_bytes),
                caption=t("receipt_caption", lang, order_id=order_id),
            )
        except Exception as e:
            logger.error(f"Failed to send receipt photo: {e}")
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=t("receipt_fetch_error", lang),
            )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=t("receipt_unavailable", lang),
        )


def get_orders_handlers() -> list:
    return [
        CallbackQueryHandler(pending_receipts_callback, pattern="^menu_pending_receipts$"),
        CallbackQueryHandler(approve_order_callback, pattern=r"^approve_order:"),
        CallbackQueryHandler(reject_order_callback, pattern=r"^reject_order:"),
        CallbackQueryHandler(view_receipt_callback, pattern=r"^view_receipt:"),
    ]
