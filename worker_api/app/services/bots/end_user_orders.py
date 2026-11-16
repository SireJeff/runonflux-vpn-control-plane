"""End-user order-history screen (read-only, paginated).

Reached from a [🧾 My Orders] button on the My Subscription screen. Lists the
user's UserOrder rows newest-first as text lines; no per-order actions.
"""

from typing import Optional

from sqlalchemy.orm import Session
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

from app.core.database import SessionLocal
from app.models.admin_users import AdminUser
from app.models.user_orders import UserOrder
from app.services.bots.end_user_keyboards import _L, nav_footer
from app.services.bots.end_user_pagination import paginate, pagination_row


def _get_user(db: Session, admin_id: int, telegram_id: int) -> Optional[AdminUser]:
    return (
        db.query(AdminUser)
        .filter(
            AdminUser.admin_id == admin_id,
            AdminUser.telegram_id == telegram_id,
        )
        .first()
    )


def _status_label(lang: str, status: str) -> str:
    """Localized status, falling back to the raw value for unmapped statuses."""
    key = f"status_{status}"
    try:
        return _L(lang, key)
    except KeyError:
        return status


def _order_line(order: UserOrder, lang: str) -> str:
    snap = order.package_snapshot or {}
    pkg = snap.get("name", "") if isinstance(snap, dict) else ""
    region = (order.macro_region or "").upper()
    date = order.created_at.strftime("%Y-%m-%d") if order.created_at else "-"
    amount = int(order.amount_tomans) if order.amount_tomans is not None else 0
    return (
        f"#{order.id} · {pkg} · {region} · {amount:,} T · "
        f"{_status_label(lang, order.status)} · {date}"
    )


async def _render_orders(query, db: Session, user: AdminUser, page: int) -> None:
    lang = getattr(user, "language", "fa") or "fa"
    orders = (
        db.query(UserOrder)
        .filter(UserOrder.user_id == user.id)
        .order_by(UserOrder.created_at.desc())
        .all()
    )
    if not orders:
        rows = [[InlineKeyboardButton(_L(lang, "buy"), callback_data="buy")]]
        rows += nav_footer(lang, back_to="my_sub")
        await query.edit_message_text(
            _L(lang, "orders_empty"), reply_markup=InlineKeyboardMarkup(rows)
        )
        return
    page_items, page, total_pages = paginate(orders, page, 6)
    lines = [_L(lang, "orders_title"), ""]
    lines += [_order_line(o, lang) for o in page_items]
    rows = pagination_row("pgorders", page, total_pages, lang)
    rows += nav_footer(lang, back_to="my_sub")
    await query.edit_message_text(
        "\n".join(lines), reply_markup=InlineKeyboardMarkup(rows)
    )


async def orders_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    assert query is not None  # CallbackQueryHandler(pattern=r"^orders$")
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
        await _render_orders(query, db, user, 0)
    finally:
        db.close()


async def pgorders_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    assert query is not None  # CallbackQueryHandler(pattern=r"^pgorders:\d+$")
    await query.answer()
    assert query.data is not None
    page = int(query.data.split(":")[1])
    tg_user = update.effective_user
    assert tg_user is not None
    admin_id = context.application.bot_data["admin_id"]
    db = SessionLocal()
    try:
        user = _get_user(db, admin_id, tg_user.id)
        if not user:
            return
        await _render_orders(query, db, user, page)
    finally:
        db.close()


def register(application: Application) -> None:
    application.add_handler(CallbackQueryHandler(orders_callback, pattern=r"^orders$"))
    application.add_handler(
        CallbackQueryHandler(pgorders_callback, pattern=r"^pgorders:\d+$")
    )
