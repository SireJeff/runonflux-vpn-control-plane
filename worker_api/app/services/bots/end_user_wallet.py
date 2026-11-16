"""End-user wallet + top-up flow.

Screens:
- wallet_callback: render balance + last ~5 wallet txns, [افزایش موجودی] / [تاریخچه]
- topup_callback: preset amount buttons (topup_amt:<n>) + [مبلغ دلخواه]
- topup_amount_callback: stash chosen amount, show reseller card details, await receipt
- topup_custom_callback: prompt for a custom numeric amount
- wallet_history_callback: list recent txns
- handle_topup_receipt: photo entry point (called from purchase's receipt_photo_handler
  when awaiting_topup_receipt is set) — creates a kind='topup' order.
- custom_amount_text_handler: group-0 text handler that only acts when
  awaiting_topup_amount is set (does NOT clash with purchase's group -1 crypto_txid handler).

State keys (context.user_data): awaiting_topup_amount, topup_amount, awaiting_topup_receipt.
"""

import asyncio
import logging
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.core.database import SessionLocal
from app.models.admin_bots import AdminBot
from app.models.admin_user_wallet_txn import AdminUserWalletTxn
from app.models.admin_users import AdminUser
from app.models.user_orders import UserOrder
from app.services.billing.topup_config import effective_min_topup_tomans
from app.services.bots.bidi_fa import num_unit
from app.services.bots.bot_lifecycle_service import _bot_token_for_admin
from app.services.bots.end_user_keyboards import nav_footer
from app.services.notifications.router import NotificationRouter
from app.services.notifications.templates_fa import template_for
from app.services.orders.order_service import OrderError, OrderService
from app.services.orders.receipt_storage import download_and_store, persist_path

logger = logging.getLogger(__name__)

_PRESETS = [100000, 200000, 500000, 1000000]
# Map Persian digits to ASCII for amount parsing.
_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")


def parse_topup_amount(raw: str, minimum: Decimal) -> Decimal:
    """Parse a user-entered amount (allowing fa digits + separators). Raises
    ValueError if non-numeric or below the minimum."""
    cleaned = (
        (raw or "").translate(_FA_DIGITS).replace(",", "").replace("،", "").strip()
    )
    try:
        amount = Decimal(cleaned)
    except (InvalidOperation, ValueError):
        raise ValueError("non-numeric")
    if amount < minimum:
        raise ValueError("below-min")
    return amount


def _get_user(db: Session, admin_id: int, telegram_id: int):
    return (
        db.query(AdminUser)
        .filter(
            AdminUser.admin_id == admin_id,
            AdminUser.telegram_id == telegram_id,
        )
        .first()
    )


def _recent_txns(db: Session, user_id: int, limit: int = 5):
    """Return the last `limit` wallet txns as (type, amount, created) tuples,
    newest first — the shape format_wallet_screen expects."""
    rows = (
        db.query(AdminUserWalletTxn)
        .filter(AdminUserWalletTxn.user_id == user_id)
        .order_by(AdminUserWalletTxn.created_at.desc(), AdminUserWalletTxn.id.desc())
        .limit(limit)
        .all()
    )
    return [(r.type, r.amount_tomans, r.created_at) for r in rows]


async def _safe_download_and_persist(
    bot_token: str, file_id: str, order_id: int
) -> None:
    """Wrap download_and_store: on success persist path, on failure log loud."""
    try:
        path = await download_and_store(bot_token, file_id, order_id)
        persist_path(order_id, path)
        logger.info("Top-up receipt stored for order %s -> %s", order_id, path)
    except Exception:
        logger.exception("Top-up receipt download failed for order %s", order_id)


def clear_flow_state(ud: dict) -> None:
    """Clear all wallet top-up state keys."""
    ud.pop("awaiting_topup_amount", None)
    ud.pop("awaiting_topup_receipt", None)
    ud.pop("topup_amount", None)


async def wallet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Render the wallet screen: balance + recent txns + top-up/history buttons."""
    query = update.callback_query
    assert query is not None  # CallbackQueryHandler(pattern=r"^wallet$")
    await query.answer()
    tg_user = update.effective_user
    assert tg_user is not None
    admin_id = context.application.bot_data["admin_id"]

    db = SessionLocal()
    try:
        user = _get_user(db, admin_id, tg_user.id)
        if not user:
            await query.edit_message_text("خطا — کاربر یافت نشد.")
            return
        lang = getattr(user, "language", "fa") or "fa"
        tpl = template_for(lang)
        balance = user.wallet_credit_tomans or Decimal("0")
        recent = _recent_txns(db, user.id)
        rows = [
            [
                InlineKeyboardButton(
                    "💳 افزایش موجودی", callback_data="topup"
                ),
                InlineKeyboardButton(
                    "🧾 تاریخچه", callback_data="wallet_history"
                ),
            ],
        ]
        rows += nav_footer(lang, screen="wallet")
        await query.edit_message_text(
            tpl.format_wallet_screen(balance, recent),
            reply_markup=InlineKeyboardMarkup(rows),
        )
    finally:
        db.close()


async def topup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show preset top-up amounts + custom option, honoring the effective minimum."""
    query = update.callback_query
    assert query is not None  # CallbackQueryHandler(pattern=r"^topup$")
    await query.answer()
    tg_user = update.effective_user
    assert tg_user is not None
    admin_id = context.application.bot_data["admin_id"]

    db = SessionLocal()
    try:
        user = _get_user(db, admin_id, tg_user.id)
        lang = getattr(user, "language", "fa") or "fa" if user else "fa"
        minimum = effective_min_topup_tomans(db, admin_id)
        presets = [p for p in _PRESETS if Decimal(p) >= minimum]
        if not presets:
            presets = [int(minimum)]
        rows: list[list[InlineKeyboardButton]] = []
        row: list[InlineKeyboardButton] = []
        for amt in presets:
            row.append(
                InlineKeyboardButton(
                    num_unit(amt, "تومان"), callback_data=f"topup_amt:{amt}"
                )
            )
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        rows.append(
            [InlineKeyboardButton("✏️ مبلغ دلخواه", callback_data="topup_custom")]
        )
        rows += nav_footer(lang, screen="topup")
        text = (
            "═══ 💳 افزایش موجودی ═══\n\n"
            f"حداقل مبلغ: {num_unit(int(minimum), 'تومان')}\n\n"
            "مبلغ مورد نظر را انتخاب کنید یا مبلغ دلخواه وارد کنید:"
        )
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows))
    finally:
        db.close()


async def _show_topup_card(update, context, db, amount: Decimal) -> None:
    """Stash the amount, mark awaiting_topup_receipt, show reseller card details."""
    query = update.callback_query
    admin_id = context.application.bot_data["admin_id"]
    ud = context.user_data
    assert ud is not None
    tg_user = update.effective_user
    user = _get_user(db, admin_id, tg_user.id) if tg_user else None
    lang = getattr(user, "language", "fa") or "fa" if user else "fa"

    bot = db.query(AdminBot).filter(AdminBot.admin_id == admin_id).first()
    if not bot:
        await query.edit_message_text("خطا — لطفاً دوباره شروع کنید.")
        return

    ud["topup_amount"] = str(amount)
    ud["awaiting_topup_receipt"] = True
    ud.pop("awaiting_topup_amount", None)

    lines = [
        "═══ 💳 افزایش موجودی ═══",
        f"مبلغ: {num_unit(int(amount), 'تومان')}",
        "",
        "کارت به کارت به:",
        bot.card_number or "(کارتی ثبت نشده)",
    ]
    if bot.card_holder_name:
        lines.append(f"بنام: {bot.card_holder_name}")
    lines.extend(
        [
            "",
            "پس از پرداخت، عکس رسید را اینجا بفرستید.",
        ]
    )
    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(nav_footer(lang, screen="topup")),
    )


async def topup_amount_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """A preset amount button was tapped — show the card + await receipt."""
    query = update.callback_query
    assert query is not None  # CallbackQueryHandler(pattern=r"^topup_amt:\d+$")
    await query.answer()
    assert query.data is not None  # data guaranteed by pattern
    amount = Decimal(query.data.split(":")[1])

    db = SessionLocal()
    try:
        await _show_topup_card(update, context, db, amount)
    finally:
        db.close()


async def topup_custom_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """User wants to type a custom amount — prompt and await a text message."""
    query = update.callback_query
    assert query is not None  # CallbackQueryHandler(pattern=r"^topup_custom$")
    await query.answer()
    tg_user = update.effective_user
    admin_id = context.application.bot_data["admin_id"]
    ud = context.user_data
    assert ud is not None

    db = SessionLocal()
    try:
        user = _get_user(db, admin_id, tg_user.id) if tg_user else None
        lang = getattr(user, "language", "fa") or "fa" if user else "fa"
        minimum = effective_min_topup_tomans(db, admin_id)
    finally:
        db.close()

    ud["awaiting_topup_amount"] = True
    ud.pop("awaiting_topup_receipt", None)
    await query.edit_message_text(
        "═══ ✏️ مبلغ دلخواه ═══\n\n"
        f"حداقل مبلغ: {num_unit(int(minimum), 'تومان')}\n\n"
        "لطفاً مبلغ مورد نظر را (به تومان) ارسال کنید:",
        reply_markup=InlineKeyboardMarkup(nav_footer(lang, screen="topup")),
    )


async def custom_amount_text_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Group-0 text handler: parses a custom top-up amount ONLY when
    awaiting_topup_amount is set; otherwise returns without touching the update
    so purchase's other text handlers stay unaffected."""
    ud = context.user_data
    assert ud is not None
    if not ud.get("awaiting_topup_amount"):
        return  # not our turn — let other handlers process this message

    tg_message = update.message
    assert tg_message is not None
    tg_user = update.effective_user
    assert tg_user is not None
    admin_id = context.application.bot_data["admin_id"]

    db = SessionLocal()
    try:
        minimum = effective_min_topup_tomans(db, admin_id)
        try:
            amount = parse_topup_amount(tg_message.text or "", minimum)
        except ValueError:
            await tg_message.reply_text(
                "مبلغ نامعتبر است. لطفاً یک عدد بزرگ‌تر یا مساوی "
                f"{num_unit(int(minimum), 'تومان')} ارسال کنید."
            )
            return

        bot = db.query(AdminBot).filter(AdminBot.admin_id == admin_id).first()
        if not bot:
            await tg_message.reply_text("خطا — لطفاً دوباره شروع کنید.")
            clear_flow_state(ud)
            return

        ud["topup_amount"] = str(amount)
        ud["awaiting_topup_receipt"] = True
        ud.pop("awaiting_topup_amount", None)

        lines = [
            "═══ 💳 افزایش موجودی ═══",
            f"مبلغ: {num_unit(int(amount), 'تومان')}",
            "",
            "کارت به کارت به:",
            bot.card_number or "(کارتی ثبت نشده)",
        ]
        if bot.card_holder_name:
            lines.append(f"بنام: {bot.card_holder_name}")
        lines.extend(["", "پس از پرداخت، عکس رسید را اینجا بفرستید."])
        await tg_message.reply_text("\n".join(lines))
    finally:
        db.close()


async def wallet_history_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """List a longer window of recent wallet transactions."""
    query = update.callback_query
    assert query is not None  # CallbackQueryHandler(pattern=r"^wallet_history$")
    await query.answer()
    tg_user = update.effective_user
    assert tg_user is not None
    admin_id = context.application.bot_data["admin_id"]

    db = SessionLocal()
    try:
        user = _get_user(db, admin_id, tg_user.id)
        if not user:
            await query.edit_message_text("خطا — کاربر یافت نشد.")
            return
        lang = getattr(user, "language", "fa") or "fa"
        recent = _recent_txns(db, user.id, limit=15)
        if not recent:
            text = "═══ 🧾 تاریخچه کیف پول ═══\n\nتراکنشی ثبت نشده است."
        else:
            label = {
                "topup": "شارژ",
                "spend": "خرید",
                "referral": "پاداش دعوت",
                "refund": "بازگشت وجه",
            }
            lines = ["═══ 🧾 تاریخچه کیف پول ═══", ""]
            for t, amt, _created in recent:
                sign = "+" if float(amt) >= 0 else ""
                lines.append(
                    f"• {label.get(t, t)}: {sign}{float(amt):,.0f} تومان"
                )
            text = "\n".join(lines)
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(nav_footer(lang, screen="wallet_history")),
        )
    finally:
        db.close()


async def handle_topup_receipt(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Photo entry point for a top-up receipt (routed from receipt_photo_handler).

    Creates a kind='topup' order, enforces max-3-pending, notifies admin, and
    schedules the receipt download. Clears wallet state on success/terminal error.
    """
    ud = context.user_data
    assert ud is not None
    tg_eff_message = update.effective_message
    assert tg_eff_message is not None

    amount_raw = ud.get("topup_amount")
    if not amount_raw:
        await tg_eff_message.reply_text(
            "مبلغ شارژ نامشخص است. لطفاً دوباره از «کیف پول» شروع کنید."
        )
        clear_flow_state(ud)
        return
    try:
        amount = Decimal(str(amount_raw))
    except (InvalidOperation, ValueError):
        await tg_eff_message.reply_text("مبلغ نامعتبر است. لطفاً دوباره تلاش کنید.")
        clear_flow_state(ud)
        return

    tg_message = update.message
    assert tg_message is not None
    photo = tg_message.photo[-1]  # highest resolution
    tg_user = update.effective_user
    assert tg_user is not None
    admin_id = context.application.bot_data["admin_id"]

    db = SessionLocal()
    try:
        user = _get_user(db, admin_id, tg_user.id)
        if not user:
            await tg_eff_message.reply_text("خطا — کاربر یافت نشد.")
            return

        pending_count = (
            db.query(UserOrder)
            .filter(
                UserOrder.user_id == user.id,
                UserOrder.status == "pending",  # noqa: E712
            )
            .count()
        )
        if pending_count >= 3:
            await tg_eff_message.reply_text(
                "شما هم‌اکنون ۳ سفارش در انتظار دارید. لطفاً منتظر تایید باشید."
            )
            return

        try:
            order = OrderService(db).create_topup_order(
                user=user,
                amount_tomans=amount,
                receipt_file_id=photo.file_id,
                receipt_file_unique_id=photo.file_unique_id,
                payment_method="card",
            )
        except OrderError:
            await tg_eff_message.reply_text(
                "ثبت درخواست شارژ ناموفق بود. لطفاً دوباره تلاش کنید."
            )
            clear_flow_state(ud)
            return

        clear_flow_state(ud)

        lang = getattr(user, "language", "fa") or "fa"
        tpl = template_for(lang)
        await tg_eff_message.reply_text(
            tpl.format_user_topup_received(order.id, float(order.amount_tomans))
        )

        NotificationRouter(db).send_to_admin(
            admin_id,
            template_for("fa").format_admin_new_topup(
                order.id,
                user.username,
                float(order.amount_tomans),
                "card",
            ),
        )

        bot_token = _bot_token_for_admin(db, admin_id)
        if bot_token:
            asyncio.create_task(
                _safe_download_and_persist(bot_token, photo.file_id, order.id)
            )
    finally:
        db.close()


def register_wallet(application: Application) -> None:
    """Wire wallet handlers into the given Application."""
    application.add_handler(CallbackQueryHandler(wallet_callback, pattern=r"^wallet$"))
    application.add_handler(CallbackQueryHandler(topup_callback, pattern=r"^topup$"))
    application.add_handler(
        CallbackQueryHandler(topup_amount_callback, pattern=r"^topup_amt:\d+$")
    )
    application.add_handler(
        CallbackQueryHandler(topup_custom_callback, pattern=r"^topup_custom$")
    )
    application.add_handler(
        CallbackQueryHandler(wallet_history_callback, pattern=r"^wallet_history$")
    )
    # Group-0 text handler for the custom-amount entry. It returns immediately
    # unless awaiting_topup_amount is set, so it does not clash with purchase's
    # group -1 crypto_txid_handler.
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, custom_amount_text_handler)
    )
