"""End-user purchase flow: browse packages -> pick regions -> upload receipt.

Handlers:
- buy_callback: list active packages for the bot's admin
- package_callback: stash picked package_id + geo attrs, show availability-filtered
  region multi-select (or auto-select all + jump to payment for all_regions plans)
- region_toggle_callback: toggle a macro-region in the picker
- region_confirm_callback: when the required count is met, show payment instructions
- receipt_photo_handler: create order, reply with receipt template, notify admin

State is held in context.user_data (PTB's per-chat dict). No FSM library —
keys: picked_package_id, picked_regions (list[str]), region_required (int), region_all (bool).
"""

import asyncio
import logging
from decimal import Decimal
from typing import Optional

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
from app.models.admin_packages import AdminPackage
from app.models.admin_users import AdminUser
from app.models.user_orders import UserOrder
from app.services.bots.bidi_fa import ltr, num_unit
from app.services.bots.bot_lifecycle_service import _bot_token_for_admin
from app.services.bots.end_user_keyboards import nav_footer, region_multiselect_keyboard
from app.services.bots.end_user_pagination import paginate, pagination_row
from app.services.bots.plan_catalog import (
    DurationGroup,
    duration_label,
    group_by_duration,
)
from app.services.bots.region_select import (
    can_confirm,
    package_body_line,
    package_button_label,
    required_region_count,
    toggle_region,
)
from app.services.notifications.router import NotificationRouter
from app.services.notifications.templates_fa import (
    format_admin_new_receipt,
    format_user_receipt_received,
    template_for,
)
from app.services.orders.order_service import OrderError, OrderService
from app.services.orders.receipt_storage import download_and_store, persist_path
from app.services.regions.availability import macro_region_availability

logger = logging.getLogger(__name__)


async def _safe_download_and_persist(
    bot_token: str, file_id: str, order_id: int
) -> None:
    """Wrap download_and_store: on success persist path, on failure log loud."""
    try:
        path = await download_and_store(bot_token, file_id, order_id)
        persist_path(order_id, path)
        logger.info("Receipt stored for order %s -> %s", order_id, path)
    except Exception:
        logger.exception("Receipt download failed for order %s", order_id)


def can_pay_from_wallet(balance, price) -> bool:
    """Pure predicate: True when the wallet balance covers the package price."""
    return (balance or 0) >= price


def _get_user(db: Session, admin_id: int, telegram_id: int) -> Optional[AdminUser]:
    return (
        db.query(AdminUser)
        .filter(
            AdminUser.admin_id == admin_id,
            AdminUser.telegram_id == telegram_id,
        )
        .first()
    )


def _active_packages(db: Session, admin_id: int) -> list:
    """Active packages for an admin, ordered for stable display."""
    return (
        db.query(AdminPackage)
        .filter(
            AdminPackage.admin_id == admin_id,
            AdminPackage.is_active == True,  # noqa: E712
        )
        .order_by(AdminPackage.display_order, AdminPackage.id)
        .all()
    )


def _durations_markup(groups: list, lang: str = "fa") -> InlineKeyboardMarkup:
    """Screen 1 keyboard: one button per distinct duration + nav footer.

    Screen "buy" is a root screen (parent main_menu) so the footer stays
    home-only, but uses the caller's real language.
    """
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                duration_label(g.duration_days),
                callback_data=f"dur:{g.duration_days}",
            )
        ]
        for g in groups
    ]
    rows += nav_footer(lang)
    return InlineKeyboardMarkup(rows)


async def _show_plans_for_duration(
    query, group: DurationGroup, page: int, lang: str = "fa"
) -> None:
    """Screen 2 ("plans", parent buy): readable body list + short selector
    buttons for one duration. Back button returns to the duration menu (buy)."""
    page_items, page, total_pages = paginate(group.packages, page, 6)
    body = "\n".join(package_body_line(p) for p in page_items)
    text = (
        f"═══ 📦 پلن‌های {duration_label(group.duration_days)} ═══\n\n"
        f"{body}\n\n"
        "پلن مورد نظر را انتخاب کنید:"
    )
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(package_button_label(p), callback_data=f"pkg:{p.id}")]
        for p in page_items
    ]
    rows += pagination_row(f"pgplans:{group.duration_days}", page, total_pages)
    rows += nav_footer(lang, screen="plans")
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows))


def _crypto_instructions_text(
    address: str,
    network: str | None,
    memo: str | None,
    amount_tomans,
    rate,
) -> str:
    """Persian crypto payment instructions with a USD equivalent."""
    usd = (Decimal(str(amount_tomans)) / Decimal(str(rate))).quantize(Decimal("0.01"))
    lines = [
        "پرداخت با ارز دیجیتال:",
        "",
        f"مبلغ: {num_unit(amount_tomans, 'تومان')} (معادل {ltr(f'${usd}')})",
        "",
        f"شبکه: {network or '-'}",
        "آدرس کیف پول:",
        address,
    ]
    if memo:
        lines.append(f"ممو/تگ: {memo}")
    lines.extend(
        [
            "",
            "پس از پرداخت، شناسه تراکنش (TxID) را همینجا ارسال کنید.",
        ]
    )
    return "\n".join(lines)


async def buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the duration menu (Screen 1). Skip to plans if only one duration."""
    query = update.callback_query
    assert query is not None  # CallbackQueryHandler(pattern=r"^buy$")
    await query.answer()

    admin_id = context.application.bot_data["admin_id"]
    db = SessionLocal()
    try:
        assert update.effective_user is not None  # private chat update
        user = _get_user(db, admin_id, update.effective_user.id)
        lang = getattr(user, "language", "fa") or "fa"
        packages = _active_packages(db, admin_id)
        if not packages:
            await query.edit_message_text(
                "در حال حاضر هیچ پلنی موجود نیست. لطفاً بعداً تلاش کنید."
            )
            return
        groups = group_by_duration(packages)
        if len(groups) == 1:
            await _show_plans_for_duration(query, groups[0], 0, lang)
            return
        await query.edit_message_text(
            "═══ 📦 خرید اشتراک ═══\nمدت اشتراک را انتخاب کنید:",
            reply_markup=_durations_markup(groups, lang),
        )
    finally:
        db.close()


async def duration_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the plans for one duration (Screen 2)."""
    query = update.callback_query
    assert query is not None  # CallbackQueryHandler(pattern=r"^dur:\d+$")
    await query.answer()
    assert query.data is not None  # data guaranteed by pattern
    days = int(query.data.split(":")[1])

    admin_id = context.application.bot_data["admin_id"]
    db = SessionLocal()
    try:
        assert update.effective_user is not None  # private chat update
        user = _get_user(db, admin_id, update.effective_user.id)
        lang = getattr(user, "language", "fa") or "fa"
        packages = [
            p for p in _active_packages(db, admin_id) if p.duration_days == days
        ]
        if not packages:
            await query.edit_message_text("پلنی برای این مدت موجود نیست.")
            return
        await _show_plans_for_duration(query, DurationGroup(days, packages), 0, lang)
    finally:
        db.close()


async def pgplans_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Re-render Screen 2 at the requested page (scoped to a duration)."""
    query = update.callback_query
    assert query is not None  # CallbackQueryHandler(pattern=r"^pgplans:\d+:\d+$")
    await query.answer()
    assert query.data is not None
    _, days_s, page_s = query.data.split(":")
    days, page = int(days_s), int(page_s)
    admin_id = context.application.bot_data["admin_id"]
    db = SessionLocal()
    try:
        assert update.effective_user is not None  # private chat update
        user = _get_user(db, admin_id, update.effective_user.id)
        lang = getattr(user, "language", "fa") or "fa"
        packages = [
            p for p in _active_packages(db, admin_id) if p.duration_days == days
        ]
        if not packages:
            return
        await _show_plans_for_duration(
            query, DurationGroup(days, packages), page, lang
        )
    finally:
        db.close()


async def package_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Stash picked package + geo attrs, show availability-filtered region multi-select."""
    query = update.callback_query
    assert query is not None  # CallbackQueryHandler(pattern=r"^pkg:")
    await query.answer()
    assert query.data is not None  # data guaranteed by pattern
    assert (
        context.user_data is not None
    )  # user_data is always present for a user-update handler

    package_id = int(query.data.split(":")[1])
    context.user_data["picked_package_id"] = package_id
    context.user_data["picked_regions"] = []

    db = SessionLocal()
    try:
        pkg = db.query(AdminPackage).filter(AdminPackage.id == package_id).first()
        if not pkg:
            await query.edit_message_text("خطا — لطفاً دوباره شروع کنید.")
            return

        avail = [e for e in macro_region_availability(db) if e["healthy_instances"] > 0]
        healthy = [e["code"] for e in avail]
        if not healthy:
            await query.edit_message_text(
                "در حال حاضر هیچ منطقه‌ای در دسترس نیست. لطفاً بعداً تلاش کنید."
            )
            return

        required = required_region_count(pkg.region_count, pkg.all_regions, healthy)
        context.user_data["region_required"] = required
        context.user_data["region_all"] = bool(pkg.all_regions)

        if pkg.all_regions:
            # auto-select every healthy region, jump straight to payment
            context.user_data["picked_regions"] = healthy
            await _show_payment_method_choice(update, context, db, pkg, healthy)
            return

        await query.edit_message_text(
            f"═══ 🌍 انتخاب منطقه ═══\nلطفاً {required} منطقه را انتخاب کنید:",
            reply_markup=region_multiselect_keyboard(avail, [], required),
        )
    finally:
        db.close()


async def _show_payment_instructions(update, context, db, pkg, regions) -> None:
    """Render the payment card (card number, wallet credit, amount due) for the picked
    package + regions. Extracted verbatim from the old region_callback payment block;
    only the region line changes (single -> joined list)."""
    query = update.callback_query
    admin_id = context.application.bot_data["admin_id"]
    bot = db.query(AdminBot).filter(AdminBot.admin_id == admin_id).first()
    if not bot:
        await query.edit_message_text("خطا — لطفاً دوباره شروع کنید.")
        return
    user = _get_user(db, admin_id, update.effective_user.id)
    lang = getattr(user, "language", "fa") or "fa"
    credit = (
        float(user.wallet_credit_tomans) if user and user.wallet_credit_tomans else 0.0
    )
    due = max(0.0, float(pkg.price_tomans) - credit)

    gb = f"{float(pkg.traffic_limit_gb):.0f}"
    lines = [
        "═══ 🧾 پرداخت ═══",
        f"پلن: {ltr(pkg.name)} "
        f"({num_unit(gb, 'GB')} / {num_unit(pkg.duration_days, 'روز')})",
        f"منطقه: {ltr(', '.join(r.upper() for r in regions))}",
        "",
        f"مبلغ: {num_unit(pkg.price_tomans, 'تومان')}",
    ]
    if credit > 0:
        lines.append(f"اعتبار کیف پول: {num_unit(credit, 'تومان')}")
        lines.append(f"مبلغ قابل پرداخت: {num_unit(due, 'تومان')}")
    lines.extend(
        [
            "",
            "کارت به کارت به:",
            bot.card_number or "(کارتی ثبت نشده)",
        ]
    )
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
        reply_markup=InlineKeyboardMarkup(nav_footer(lang, screen="payment")),
    )


async def _show_payment_method_choice(update, context, db, pkg, regions) -> None:
    """Let the user pick a payment method.

    A "pay from wallet" button is offered whenever the user's balance covers the
    package price — regardless of whether the reseller has a crypto address. If
    crypto is configured, the user also picks Card vs Crypto; otherwise we fall
    through to the card renderer (with the wallet button prepended when eligible).
    """
    admin_id = context.application.bot_data["admin_id"]
    bot = db.query(AdminBot).filter(AdminBot.admin_id == admin_id).first()

    user = _get_user(db, admin_id, update.effective_user.id)
    balance = user.wallet_credit_tomans if user else None
    wallet_ok = can_pay_from_wallet(balance, pkg.price_tomans)
    wallet_row = [
        InlineKeyboardButton("👛 پرداخت از کیف پول", callback_data="paywallet")
    ]

    context.user_data["picked_package_id"] = pkg.id
    context.user_data["picked_regions"] = regions

    if not bot or not bot.crypto_address:
        # Card-only path: no method choice, but still offer the wallet button
        # (when eligible) before falling through to the card renderer.
        if wallet_ok:
            await update.callback_query.edit_message_text(
                "روش پرداخت را انتخاب کنید:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        wallet_row,
                        [
                            InlineKeyboardButton(
                                "💳 کارت به کارت", callback_data="paymethod:card"
                            )
                        ],
                    ]
                ),
            )
            return
        await _show_payment_instructions(update, context, db, pkg, regions)
        return

    rows = []
    if wallet_ok:
        rows.append(wallet_row)
    rows.append(
        [
            InlineKeyboardButton("💳 کارت به کارت", callback_data="paymethod:card"),
            InlineKeyboardButton("🪙 ارز دیجیتال", callback_data="paymethod:crypto"),
        ]
    )
    await update.callback_query.edit_message_text(
        "روش پرداخت را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def paymethod_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    assert query is not None  # CallbackQueryHandler(pattern=r"^paymethod:")
    await query.answer()
    assert query.data is not None  # data guaranteed by pattern
    choice = query.data.split(":")[1]
    admin_id = context.application.bot_data["admin_id"]
    ud = context.user_data
    assert ud is not None
    db = SessionLocal()
    try:
        pkg_id = ud.get("picked_package_id")
        regions = ud.get("picked_regions") or []
        pkg = (
            db.query(AdminPackage)
            .filter(
                AdminPackage.id == pkg_id,
                AdminPackage.admin_id == admin_id,
            )
            .first()
        )
        if not pkg:
            await query.edit_message_text("بسته یافت نشد.")
            return
        if choice == "crypto":
            await _show_crypto_instructions(update, context, db, pkg, regions)
        else:
            ud["awaiting_crypto_txid"] = False
            await _show_payment_instructions(update, context, db, pkg, regions)
    finally:
        db.close()


async def paywallet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Pay the full package price from the wallet: create an approved, auto-activating
    order. The hero (connections) is delivered by _deliver_connections inside
    create_wallet_paid_order; here we just confirm and clear purchase state."""
    query = update.callback_query
    assert query is not None  # CallbackQueryHandler(pattern=r"^paywallet$")
    await query.answer()

    ud = context.user_data
    assert ud is not None
    admin_id = context.application.bot_data["admin_id"]
    pkg_id = ud.get("picked_package_id")
    regions = ud.get("picked_regions") or []

    def _clear_state() -> None:
        ud.pop("picked_package_id", None)
        ud.pop("picked_regions", None)
        ud.pop("region_required", None)
        ud.pop("region_all", None)

    db = SessionLocal()
    try:
        assert update.effective_user is not None  # private chat update
        user = _get_user(db, admin_id, update.effective_user.id)
        if not (user and pkg_id and regions):
            await query.edit_message_text("سفارش نامعتبر است. دوباره تلاش کنید.")
            _clear_state()
            return
        try:
            OrderService(db).create_wallet_paid_order(user, pkg_id, regions)
        except OrderError:
            await query.edit_message_text(
                "موجودی کیف پول کافی نیست. لطفاً کیف پول خود را شارژ کنید "
                "یا از روش دیگری پرداخت کنید."
            )
            return
        _clear_state()
        await query.edit_message_text("✅ پرداخت انجام شد؛ اشتراک فعال شد.")
    finally:
        db.close()


async def _show_crypto_instructions(update, context, db, pkg, regions) -> None:
    admin_id = context.application.bot_data["admin_id"]
    bot = db.query(AdminBot).filter(AdminBot.admin_id == admin_id).first()

    user = _get_user(db, admin_id, update.effective_user.id)
    lang = getattr(user, "language", "fa") or "fa"
    user_balance = (user.wallet_credit_tomans or Decimal("0")) if user else Decimal("0")
    applied = min(user_balance, pkg.price_tomans)
    amount_due = pkg.price_tomans - applied

    from app.services.billing.conversion import get_toman_per_usd_rate

    rate = get_toman_per_usd_rate(db)
    text = _crypto_instructions_text(
        address=bot.crypto_address,
        network=bot.crypto_network,
        memo=bot.crypto_memo,
        amount_tomans=int(amount_due),
        rate=int(rate),
    )
    context.user_data["awaiting_crypto_txid"] = True
    context.user_data["picked_package_id"] = pkg.id
    context.user_data["picked_regions"] = regions
    await update.callback_query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(nav_footer(lang, screen="payment")),
    )


async def crypto_txid_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Group -1 text handler: consumes a TxID only when awaiting one."""
    from telegram.ext import ApplicationHandlerStop

    # MessageHandler(filters.TEXT & ~filters.COMMAND) guarantees message +
    # effective_user; user_data is the per-chat dict for this update.
    ud = context.user_data
    assert ud is not None
    if not ud.get("awaiting_crypto_txid"):
        return  # let group-0 text handlers process this message

    tg_message = update.message
    assert tg_message is not None
    txid = (tg_message.text or "").strip()
    if not txid:
        await tg_message.reply_text("لطفاً شناسه تراکنش معتبر ارسال کنید.")
        raise ApplicationHandlerStop

    tg_user = update.effective_user
    assert tg_user is not None
    admin_id = context.application.bot_data["admin_id"]
    db = SessionLocal()
    try:
        user = _get_user(db, admin_id, tg_user.id)
        pkg_id = ud.get("picked_package_id")
        regions = ud.get("picked_regions") or []
        if not (user and pkg_id and regions):
            await tg_message.reply_text("سفارش نامعتبر است. دوباره تلاش کنید.")
            ud["awaiting_crypto_txid"] = False
            raise ApplicationHandlerStop

        pending_count = (
            db.query(UserOrder)
            .filter(
                UserOrder.user_id == user.id,
                UserOrder.status == "pending",  # noqa: E712
            )
            .count()
        )
        if pending_count >= 3:
            await tg_message.reply_text(
                "شما هم‌اکنون ۳ سفارش در انتظار دارید. " "لطفاً منتظر تایید باشید."
            )
            ud["awaiting_crypto_txid"] = False
            raise ApplicationHandlerStop

        try:
            order = OrderService(db).create_order(
                user=user,
                package_id=pkg_id,
                macro_regions=regions,
                payment_method="crypto",
                crypto_txid=txid,
            )
        except OrderError:
            ud["awaiting_crypto_txid"] = False
            await tg_message.reply_text(
                "پرداخت ارز دیجیتال برای این فروشنده در حال حاضر در دسترس نیست. "
                "لطفاً از روش کارت به کارت استفاده کنید یا بعداً دوباره تلاش کنید."
            )
            raise ApplicationHandlerStop
        ud.clear()
        tpl = template_for(getattr(user, "language", "fa"))
        await tg_message.reply_text(
            tpl.format_user_crypto_received(order.id, float(order.amount_tomans)),
        )
        NotificationRouter(db).send_to_admin(
            admin_id,
            template_for("fa").format_admin_new_crypto(
                order.id,
                user.username,
                (order.package_snapshot or {}).get("name", ""),
                order.macro_region,
                float(order.amount_tomans),
                txid,
            ),
        )
    finally:
        db.close()
    raise ApplicationHandlerStop


async def region_toggle_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    assert query is not None  # CallbackQueryHandler(pattern=r"^rtoggle:")
    await query.answer()
    assert query.data is not None  # data guaranteed by pattern

    macro = query.data.split(":")[1]
    ud = context.user_data
    assert ud is not None
    required = ud.get("region_required")
    if required is None:
        await query.edit_message_text("نشست منقضی شده. لطفاً دوباره تلاش کنید.")
        return

    selected = toggle_region(ud.get("picked_regions", []), macro, required)
    ud["picked_regions"] = selected

    db = SessionLocal()
    try:
        avail = [e for e in macro_region_availability(db) if e["healthy_instances"] > 0]
    finally:
        db.close()

    await query.edit_message_reply_markup(
        reply_markup=region_multiselect_keyboard(avail, selected, required)
    )


async def region_confirm_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    assert query is not None  # CallbackQueryHandler(pattern=r"^rconfirm$")

    ud = context.user_data
    assert ud is not None
    required = ud.get("region_required", 0)
    selected = ud.get("picked_regions", [])
    if not can_confirm(selected, required):
        await query.answer(
            f"لطفاً دقیقاً {required} منطقه انتخاب کنید.", show_alert=True
        )
        return

    package_id = ud.get("picked_package_id")
    db = SessionLocal()
    try:
        pkg = db.query(AdminPackage).filter(AdminPackage.id == package_id).first()
        if not pkg:
            await query.edit_message_text("خطا — لطفاً دوباره شروع کنید.")
            return
        await _show_payment_method_choice(update, context, db, pkg, selected)
    finally:
        db.close()


async def receipt_photo_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """User uploaded a photo — treat it as a receipt and create the order."""
    # MessageHandler(filters.PHOTO) guarantees message + effective_message +
    # effective_user; user_data is the per-chat dict for this update.
    ud = context.user_data
    assert ud is not None
    if ud.get("awaiting_topup_receipt"):
        from app.services.bots.end_user_wallet import handle_topup_receipt

        await handle_topup_receipt(update, context)
        return
    tg_eff_message = update.effective_message
    assert tg_eff_message is not None
    if "picked_package_id" not in ud or not ud.get("picked_regions"):
        await tg_eff_message.reply_text("لطفاً ابتدا از منوی «خرید اشتراک» شروع کنید.")
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
                "شما هم‌اکنون ۳ سفارش در انتظار دارید. " "لطفاً منتظر تایید باشید."
            )
            return

        order = OrderService(db).create_order(
            user=user,
            package_id=ud["picked_package_id"],
            macro_regions=ud["picked_regions"],
            receipt_file_id=photo.file_id,
            receipt_file_unique_id=photo.file_unique_id,
        )

        ud.pop("picked_package_id", None)
        ud.pop("picked_regions", None)
        ud.pop("region_required", None)
        ud.pop("region_all", None)

        await tg_eff_message.reply_text(
            format_user_receipt_received(order.id, float(order.amount_tomans))
        )

        router = NotificationRouter(db)
        router.send_to_admin(
            admin_id,
            format_admin_new_receipt(
                order_id=order.id,
                username=user.username,
                package_name=(order.package_snapshot or {}).get("name", ""),
                region=(order.macro_region or "").upper(),
                amount=float(order.amount_tomans),
            ),
        )

        bot_token = _bot_token_for_admin(db, admin_id)
        if bot_token:
            asyncio.create_task(
                _safe_download_and_persist(bot_token, photo.file_id, order.id)
            )
    finally:
        db.close()


def register(application: Application) -> None:
    """Wire purchase handlers into the given Application."""
    application.add_handler(CallbackQueryHandler(buy_callback, pattern=r"^buy$"))
    application.add_handler(
        CallbackQueryHandler(pgplans_callback, pattern=r"^pgplans:\d+:\d+$")
    )
    application.add_handler(
        CallbackQueryHandler(duration_callback, pattern=r"^dur:\d+$")
    )
    application.add_handler(CallbackQueryHandler(package_callback, pattern=r"^pkg:"))
    application.add_handler(
        CallbackQueryHandler(region_toggle_callback, pattern=r"^rtoggle:")
    )
    application.add_handler(
        CallbackQueryHandler(region_confirm_callback, pattern=r"^rconfirm$")
    )
    application.add_handler(
        CallbackQueryHandler(paymethod_callback, pattern=r"^paymethod:")
    )
    application.add_handler(
        CallbackQueryHandler(paywallet_callback, pattern=r"^paywallet$")
    )
    application.add_handler(MessageHandler(filters.PHOTO, receipt_photo_handler))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, crypto_txid_handler),
        group=-1,
    )
