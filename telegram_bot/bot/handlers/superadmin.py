import logging
import secrets
from datetime import datetime

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bot.api.client import get_api
from bot.i18n.translator import t
from bot.keyboards.common import (
    approve_reject_keyboard,
    back_button,
    back_keyboard,
    cancel_button,
    confirm_button,
    make_keyboard,
)

logger = logging.getLogger(__name__)

# Conversation states
WAITING_PASSWORD, WAITING_RATE, WAITING_REASON, WAITING_CONFIRM = range(4)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _format_date(date_str: str) -> str:
    """Parse ISO datetime and return a short display string."""
    if not date_str:
        return "-"
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, AttributeError):
        return date_str[:16]


# ---------------------------------------------------------------------------
# Menu callbacks (non-conversation)
# ---------------------------------------------------------------------------

async def menu_registrations_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List pending admin registrations with approve/reject buttons."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("language", "en")
    telegram_id = update.effective_user.id
    api = get_api()

    result = await api.list_pending_admins(telegram_id)

    if not result:
        await query.edit_message_text(
            t("error_general", lang),
            reply_markup=back_keyboard("main_menu", lang),
        )
        return

    # result may be a list directly or {"items": [...]}
    if isinstance(result, dict):
        admins = result.get("items", [])
    else:
        admins = result

    title = t("super_registrations_title", lang, count=len(admins))

    if not admins:
        await query.edit_message_text(
            f"{title}\n\n{t('super_registrations_empty', lang)}",
            reply_markup=back_keyboard("main_menu", lang),
        )
        return

    lines = [title, ""]
    keyboard_rows = []

    for admin in admins:
        username = admin.get("username", "-")
        display_name = admin.get("display_name", "-")
        telegram_admin_id = admin.get("telegram_id", "-")
        created_at = _format_date(admin.get("created_at", ""))

        item_text = t(
            "super_registration_item", lang,
            username=username,
            display_name=display_name,
            telegram_id=telegram_admin_id,
            created_at=created_at,
        )
        lines.append(item_text)

        admin_db_id = admin.get("id")
        if admin_db_id is not None:
            keyboard_rows.append(
                approve_reject_keyboard(f"reg", admin_db_id, lang).inline_keyboard[0]
            )

    keyboard_rows.append([back_button("main_menu", lang)])

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=make_keyboard(keyboard_rows),
    )


async def menu_wire_orders_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List pending wire orders with approve/reject buttons."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("language", "en")
    telegram_id = update.effective_user.id
    api = get_api()

    result = await api.list_wire_orders(telegram_id, status_filter="pending")

    if not result:
        await query.edit_message_text(
            t("error_general", lang),
            reply_markup=back_keyboard("main_menu", lang),
        )
        return

    orders = result.get("items", [])
    total = result.get("total", len(orders))

    title = t("super_wire_orders_title", lang, count=total)

    if not orders:
        await query.edit_message_text(
            f"{title}\n\n{t('super_wire_orders_empty', lang)}",
            reply_markup=back_keyboard("main_menu", lang),
        )
        return

    lines = [title, ""]
    keyboard_rows = []

    for order in orders:
        order_id = order.get("id", "-")
        admin_name = order.get("admin_name", "-")
        amount_tomans = order.get("amount_tomans", 0)
        contact = order.get("contact", "-")
        created_at = _format_date(order.get("created_at", ""))

        item_text = t(
            "super_wire_order_item", lang,
            id=order_id,
            admin_name=admin_name,
            amount_tomans=f"{amount_tomans:,}" if isinstance(amount_tomans, (int, float)) else str(amount_tomans),
            contact=contact,
            created_at=created_at,
        )
        lines.append(item_text)

        keyboard_rows.append(
            approve_reject_keyboard(f"order", order_id, lang).inline_keyboard[0]
        )

    keyboard_rows.append([back_button("main_menu", lang)])

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=make_keyboard(keyboard_rows),
    )


async def menu_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show platform statistics."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("language", "en")
    telegram_id = update.effective_user.id
    api = get_api()

    result = await api.get_platform_analytics(telegram_id)

    if not result:
        await query.edit_message_text(
            t("error_general", lang),
            reply_markup=back_keyboard("main_menu", lang),
        )
        return

    lines = [t("super_stats_title", lang), ""]

    lines.append(t("super_stats_admins", lang, count=result.get("total_admins", 0)))
    lines.append(t("super_stats_users", lang, count=result.get("total_users", 0)))
    lines.append(t("super_stats_active_users", lang, count=result.get("active_users", 0)))

    revenue = result.get("total_revenue", 0)
    if isinstance(revenue, (int, float)):
        revenue = f"{revenue:,.2f}"
    lines.append(t("super_stats_revenue", lang, amount=revenue))

    traffic_gb = result.get("total_traffic_gb", 0)
    if isinstance(traffic_gb, (int, float)):
        traffic_gb = round(traffic_gb, 1)
    lines.append(t("super_stats_traffic", lang, gb=traffic_gb))

    lines.append(t("super_stats_pending_orders", lang, count=result.get("pending_orders", 0)))

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=back_keyboard("main_menu", lang),
    )


async def reject_reg_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reject a pending admin registration (no conversation needed)."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("language", "en")
    telegram_id = update.effective_user.id
    api = get_api()

    callback_data = query.data
    try:
        admin_id = int(callback_data.split("_")[-1])
    except (ValueError, IndexError):
        await query.edit_message_text(
            t("error_general", lang),
            reply_markup=back_keyboard("main_menu", lang),
        )
        return

    result = await api.reject_admin(telegram_id, admin_id)

    if result:
        username = result.get("username", "-")
        await query.edit_message_text(
            t("super_reject_success", lang, username=username),
            reply_markup=back_keyboard("menu_registrations", lang),
        )
    else:
        await query.edit_message_text(
            t("error_general", lang),
            reply_markup=back_keyboard("menu_registrations", lang),
        )


# ---------------------------------------------------------------------------
# Registration Approval ConversationHandler
# ---------------------------------------------------------------------------

async def approve_reg_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Auto-approve a pending registration with a generated password."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("language", "en")
    telegram_id = update.effective_user.id
    api = get_api()

    try:
        admin_id = int(query.data.split("_")[-1])
    except (ValueError, IndexError):
        await query.edit_message_text(
            t("error_general", lang),
            reply_markup=back_keyboard("menu_registrations", lang),
        )
        return

    # Auto-generate an 8-char password
    password = secrets.token_urlsafe(6)[:8]

    result = await api.approve_admin(telegram_id, admin_id, password)

    if result:
        username = result.get("username", f"#{admin_id}")
        await query.edit_message_text(
            t("super_approve_success", lang, username=username) + f"\nPassword: {password}",
            reply_markup=back_keyboard("menu_registrations", lang),
        )
    else:
        await query.edit_message_text(
            t("error_general", lang),
            reply_markup=back_keyboard("menu_registrations", lang),
        )


# ---------------------------------------------------------------------------
# Wire Order Approval ConversationHandler
# ---------------------------------------------------------------------------

async def start_approve_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry: ask superadmin to enter exchange rate."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("language", "en")
    callback_data = query.data

    try:
        order_id = int(callback_data.split("_")[-1])
    except (ValueError, IndexError):
        await query.edit_message_text(
            t("error_general", lang),
            reply_markup=back_keyboard("menu_wire_orders", lang),
        )
        return ConversationHandler.END

    context.user_data["approve_order_id"] = order_id

    await query.edit_message_text(
        t("super_wire_approve_prompt_rate", lang),
        reply_markup=make_keyboard([[cancel_button(lang)]]),
    )
    return WAITING_RATE


async def receive_rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive and validate exchange rate, show confirmation."""
    lang = context.user_data.get("language", "en")
    text = update.message.text.strip()

    try:
        rate = float(text.replace(",", ""))
    except ValueError:
        await update.message.reply_text(t("error_general", lang))
        return WAITING_RATE

    if rate <= 0:
        await update.message.reply_text(t("error_general", lang))
        return WAITING_RATE

    order_id = context.user_data.get("approve_order_id")
    context.user_data["approve_order_rate"] = rate

    # Calculate USD amount for display (need order amount — fetch or use placeholder)
    # We stored order_id; for now show rate
    confirm_text = f"Approve order #{order_id}\nExchange rate: {rate:,.0f} Tomans/USD\n\nConfirm?"

    await update.message.reply_text(
        confirm_text,
        reply_markup=make_keyboard([
            [confirm_button(lang), cancel_button(lang)],
        ]),
    )
    return WAITING_CONFIRM


async def confirm_approve_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirm wire order approval."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("language", "en")
    telegram_id = update.effective_user.id
    api = get_api()

    order_id = context.user_data.pop("approve_order_id", None)
    rate = context.user_data.pop("approve_order_rate", None)

    if not order_id or not rate:
        await query.edit_message_text(
            t("error_general", lang),
            reply_markup=back_keyboard("menu_wire_orders", lang),
        )
        return ConversationHandler.END

    result = await api.approve_wire_order(telegram_id, order_id, rate)

    if result:
        amount_tomans = result.get("amount_tomans", 0)
        amount_usd = result.get("amount_usd", 0)
        await query.edit_message_text(
            t("super_wire_approved", lang, id=order_id,
              amount_tomans=f"{amount_tomans:,}",
              amount_usd=f"{amount_usd:,.2f}"),
            reply_markup=back_keyboard("menu_wire_orders", lang),
        )
    else:
        await query.edit_message_text(
            t("error_general", lang),
            reply_markup=back_keyboard("menu_wire_orders", lang),
        )

    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Wire Order Rejection ConversationHandler
# ---------------------------------------------------------------------------

async def start_reject_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry: ask superadmin for rejection reason."""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("language", "en")
    callback_data = query.data

    try:
        order_id = int(callback_data.split("_")[-1])
    except (ValueError, IndexError):
        await query.edit_message_text(
            t("error_general", lang),
            reply_markup=back_keyboard("menu_wire_orders", lang),
        )
        return ConversationHandler.END

    context.user_data["reject_order_id"] = order_id

    await query.edit_message_text(
        t("super_wire_reject_prompt_reason", lang),
        reply_markup=make_keyboard([[cancel_button(lang)]]),
    )
    return WAITING_REASON


async def receive_reject_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive rejection reason and submit."""
    lang = context.user_data.get("language", "en")
    telegram_id = update.effective_user.id
    api = get_api()

    reason = update.message.text.strip()
    if reason == "-":
        reason = ""

    order_id = context.user_data.pop("reject_order_id", None)

    if not order_id:
        await update.message.reply_text(t("error_general", lang))
        return ConversationHandler.END

    result = await api.reject_wire_order(telegram_id, order_id, admin_notes=reason)

    if result:
        text = t("super_wire_rejected", lang, id=order_id)
    else:
        text = t("error_general", lang)

    await update.message.reply_text(
        text,
        reply_markup=back_keyboard("menu_wire_orders", lang),
    )
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Shared cancel handler for conversations
# ---------------------------------------------------------------------------

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the current conversation and return to main menu."""
    query = update.callback_query
    await query.answer()

    # Clean up any pending context data
    for key in list(context.user_data.keys()):
        if key.startswith("approve_") or key.startswith("reject_"):
            context.user_data.pop(key, None)

    await query.edit_message_text(
        t("loading", lang=context.user_data.get("language", "en")),
        reply_markup=back_keyboard("main_menu", context.user_data.get("language", "en")),
    )
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def get_superadmin_handlers() -> list:
    return [
        CallbackQueryHandler(menu_registrations_callback, pattern="^menu_registrations$"),
        CallbackQueryHandler(menu_wire_orders_callback, pattern="^menu_wire_orders$"),
        CallbackQueryHandler(menu_stats_callback, pattern="^menu_stats$"),
        CallbackQueryHandler(reject_reg_callback, pattern=r"^reject_reg_(\d+)$"),
        CallbackQueryHandler(approve_reg_callback, pattern=r"^approve_reg_(\d+)$"),
        ConversationHandler(
            entry_points=[CallbackQueryHandler(start_approve_order, pattern=r"^approve_order_(\d+)$")],
            states={
                WAITING_RATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_rate)],
                WAITING_CONFIRM: [CallbackQueryHandler(confirm_approve_order, pattern=r"^confirm_approve_order_(\d+)$")],
            },
            fallbacks=[CallbackQueryHandler(cancel_conversation, pattern="^cancel$")],
            per_message=False,
        ),
        ConversationHandler(
            entry_points=[CallbackQueryHandler(start_reject_order, pattern=r"^reject_order_(\d+)$")],
            states={
                WAITING_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_reject_reason)],
            },
            fallbacks=[CallbackQueryHandler(cancel_conversation, pattern="^cancel$")],
            per_message=False,
        ),
    ]
