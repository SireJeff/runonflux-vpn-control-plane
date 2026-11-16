"""End-user referral view (Task 18).

- referral_callback: show referral code, total earned, wallet, share link
- open_referral_from_start: same view opened via /start referral deep-link

Deep-link referrer linkage (the /start ref_XXX path) is handled inline in
end_user_start.start_command — see the context.args parse there.
"""

import logging
from urllib.parse import quote

from sqlalchemy import func
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

from app.core.database import SessionLocal
from app.models.admin_bots import AdminBot
from app.models.admin_referral import AdminReferralConfig, AdminReferralEarning
from app.models.admin_users import AdminUser

logger = logging.getLogger(__name__)


def _build_referral_view(db, admin_id, bot_id, tg_user):
    """Compose the referral view (text + keyboard) for a Telegram user.

    Returns (text, reply_markup). reply_markup is None for the error/disabled
    cases so both callers can render a plain message. Shared by the callback
    (edit) and the /start referral deep-link (reply) entry points.
    """
    cfg = (
        db.query(AdminReferralConfig)
        .filter(
            AdminReferralConfig.admin_id == admin_id,
            AdminReferralConfig.is_enabled == True,  # noqa: E712
        )
        .first()
    )
    if not cfg:
        return (
            "═══ 🎁 دعوت دوستان ═══\n" "برنامه دعوت توسط مدیر غیرفعال شده است.",
            None,
        )

    user = (
        db.query(AdminUser)
        .filter(
            AdminUser.admin_id == admin_id,
            AdminUser.telegram_id == tg_user.id,
        )
        .first()
    )
    if not user:
        return (
            "═══ 🎁 دعوت دوستان ═══\n" "ابتدا ربات را با /start فعال کنید.",
            None,
        )
    from app.services.referral.codes import ensure_referral_code

    ensure_referral_code(user)
    db.commit()

    total_earned = (
        db.query(func.coalesce(func.sum(AdminReferralEarning.amount_tomans), 0))
        .filter(AdminReferralEarning.referrer_user_id == user.id)
        .scalar()
    ) or 0

    bot = db.query(AdminBot).filter(AdminBot.id == bot_id).first()
    bot_username = bot.bot_username if bot else ""
    share_link = f"https://t.me/{bot_username}?start=ref_{user.referral_code}"

    wallet = float(user.wallet_credit_tomans or 0)
    reward_pct = float(cfg.reward_percentage)

    from app.services.referral.bonus_service import ReferralBonusService

    bonus_line = ""
    if cfg.reward_type in ("traffic", "both"):
        svc = ReferralBonusService(db)
        friends = svc.count_qualifying(user.id, admin_id)
        bonus_mb = svc.compute_bonus_mb(user)
        bonus_line = f"ترافیک هدیه: +{bonus_mb} مگابایت در روز از {friends} دوست\n"

    # Share button: hand Telegram a t.me/share/url deep link so tapping it
    # opens the "select a chat" picker pre-filled with the referral link and
    # a call-to-action. The advertised figure is the base free-config daily
    # allowance the NEW friend receives just for starting + enrolling.
    from app.services.free_config.policy import resolve_free_config_policy

    friend_daily_mb = resolve_free_config_policy(db, admin_id).daily_limit_mb
    share_cta = (
        "🎁 با این ربات استارت کن و روزانه "
        f"{friend_daily_mb} مگابایت ترافیک رایگان VPN بگیر!"
    )
    share_prompt_url = (
        "https://t.me/share/url?url="
        + quote(share_link, safe="")
        + "&text="
        + quote(share_cta, safe="")
    )

    text = (
        "═══ 🎁 دعوت دوستان ═══\n"
        f"کد دعوت شما: {user.referral_code}\n"
        f"مجموع پاداش: {int(total_earned):,} تومان\n"
        f"موجودی کیف پول: {int(wallet):,} تومان\n"
        f"{bonus_line}"
        f"\nلینک اشتراک:\n{share_link}\n\n"
        f"درصد پاداش هر خرید: {reward_pct:.0f}%"
    )
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📤 اشتراک‌گذاری", url=share_prompt_url)],
            [InlineKeyboardButton("↩️ منوی اصلی", callback_data="main_menu")],
        ]
    )
    return text, keyboard


async def referral_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show referral code + total earnings + wallet + shareable link."""
    # CallbackQueryHandler(pattern=r"^referral$") guarantees callback_query;
    # a callback query always carries a user.
    query = update.callback_query
    assert query is not None
    await query.answer()
    tg_user = update.effective_user
    assert tg_user is not None

    admin_id = context.application.bot_data["admin_id"]
    bot_id = context.application.bot_data["bot_id"]
    db = SessionLocal()
    try:
        text, keyboard = _build_referral_view(db, admin_id, bot_id, tg_user)
        await query.edit_message_text(text, reply_markup=keyboard)
    finally:
        db.close()


async def open_referral_from_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Render the referral view as a new message (via /start referral deep-link)."""
    tg_user = update.effective_user
    tg_message = update.effective_message
    assert tg_user is not None
    assert tg_message is not None

    admin_id = context.application.bot_data["admin_id"]
    bot_id = context.application.bot_data["bot_id"]
    db = SessionLocal()
    try:
        text, keyboard = _build_referral_view(db, admin_id, bot_id, tg_user)
        await tg_message.reply_text(text, reply_markup=keyboard)
    finally:
        db.close()


def register(application: Application) -> None:
    """Wire referral handler into the Application."""
    application.add_handler(
        CallbackQueryHandler(referral_callback, pattern=r"^referral$")
    )
