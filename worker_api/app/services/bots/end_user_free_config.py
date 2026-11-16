"""End-user free config views.

- free_config_callback: dispatcher. Reads the reseller's free-config ``kind``
  and delegates to the per-user CLAIM flow (channel-gated provisioning) or the
  shared public-bundle rendering.
- free_config_claim: channel-gated per-user claim flow (Task 5).
- _free_config_shared: shared public-config bundle (Task 14, moved verbatim).

The main menu shows the 🆓 button only when free config is enabled; that gating
lives in end_user_start where the menu is built.
"""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

from app.core.database import SessionLocal
from app.models.admin_users import AdminUser
from app.services.bots.end_user_keyboards import _L, nav_footer
from app.services.free_config.enrollment_service import (
    FreeConfigEnrollmentService,
    FreeConfigUnavailableError,
    FreeSlotsFullError,
)
from app.services.free_config.free_config_service import FreeConfigService
from app.services.free_config.membership_verifier import MembershipVerifier
from app.services.free_config.policy import resolve_free_config_policy
from app.services.url_resolver import get_subscription_base_url

logger = logging.getLogger(__name__)


async def _verify(db, policy, telegram_id):
    """Wrapper so tests can patch verification. Returns VerificationResult."""
    verifier = MembershipVerifier.from_global(db)
    if verifier is None:
        from app.services.free_config.membership_verifier import VerificationResult

        return VerificationResult(ok=False, unverifiable=list(policy.required_channels))
    return await verifier.check(telegram_id, policy.required_channels)


def build_join_screen(policy, lang):
    rows = []
    for ch in policy.required_channels:
        url = ch.invite_url or (
            f"https://t.me/{ch.username.lstrip('@')}" if ch.username else None
        )
        label = ch.title or (ch.username or "channel")
        if url:
            rows.append([InlineKeyboardButton(f"➡️ {label}", url=url)])
    rows.append(
        [InlineKeyboardButton(_L(lang, "fc_check_again"), callback_data="free_config")]
    )
    return _L(lang, "fc_join_title"), InlineKeyboardMarkup(rows)


def free_config_enabled(db, admin_id) -> bool:
    """Menu-gate helper: True when the per-user policy is fully enabled."""
    return resolve_free_config_policy(db, admin_id).enabled


async def free_config_claim(update, context):
    query = update.callback_query
    await query.answer()
    admin_id = context.application.bot_data["admin_id"]
    tg_user = update.effective_user
    db = SessionLocal()
    try:
        policy = resolve_free_config_policy(db, admin_id)
        user = (
            db.query(AdminUser)
            .filter(AdminUser.admin_id == admin_id, AdminUser.telegram_id == tg_user.id)
            .first()
        )
        lang = getattr(user, "language", "fa") or "fa"
        if not policy.enabled or user is None:
            await query.edit_message_text(
                _L(lang, "fc_unavailable"),
                reply_markup=InlineKeyboardMarkup(
                    nav_footer(lang, screen="free_config")
                ),
            )
            return

        result = await _verify(db, policy, tg_user.id)
        if not result.ok:
            if result.unverifiable:
                await query.edit_message_text(
                    _L(lang, "fc_unavailable"),
                    reply_markup=InlineKeyboardMarkup(
                        nav_footer(lang, screen="free_config")
                    ),
                )
                return
            text, markup = build_join_screen(policy, lang)
            await query.edit_message_text(text, reply_markup=markup)
            return

        try:
            FreeConfigEnrollmentService(db).provision(user, policy)
        except FreeSlotsFullError:
            db.rollback()
            await query.edit_message_text(
                _L(lang, "fc_slots_full"),
                reply_markup=InlineKeyboardMarkup(
                    nav_footer(lang, screen="free_config")
                ),
            )
            return
        except FreeConfigUnavailableError:
            db.rollback()
            await query.edit_message_text(
                _L(lang, "fc_unavailable"),
                reply_markup=InlineKeyboardMarkup(
                    nav_footer(lang, screen="free_config")
                ),
            )
            return

        base = get_subscription_base_url(db, admin_id)
        sub_url = f"{base}/api/v1/user/sub/{user.subscription_token}"
        label = _L(lang, "fc_daily_label").format(mb=policy.daily_limit_mb)
        text = f"═══ {label} ═══\n\n{sub_url}"
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(nav_footer(lang, screen="free_config")),
        )
    finally:
        db.close()


async def _free_config_shared(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show the shared free public config bundle, or a not-available notice."""
    # CallbackQueryHandler(pattern=r"^free_config$") guarantees callback_query;
    # a callback query always carries a user.
    query = update.callback_query
    assert query is not None
    await query.answer()
    tg_user = update.effective_user
    assert tg_user is not None

    admin_id = context.application.bot_data["admin_id"]

    db = SessionLocal()
    try:
        user = (
            db.query(AdminUser)
            .filter(
                AdminUser.admin_id == admin_id,
                AdminUser.telegram_id == tg_user.id,
            )
            .first()
        )
        lang = getattr(user, "language", "fa") or "fa"

        bundle = FreeConfigService(db).public_bundle(admin_id)
        footer = nav_footer(lang, screen="free_config")

        if bundle is None:
            text = (
                "در حال حاضر کانفیگ رایگان فعال نیست."
                if lang == "fa"
                else "Free config is not available right now."
            )
            await query.edit_message_text(
                text, reply_markup=InlineKeyboardMarkup(footer)
            )
            return

        label = bundle.get("label") or (
            "کانفیگ رایگان" if lang == "fa" else "Free Config"
        )
        countries = bundle.get("countries") or []
        if countries:
            country_lines = "\n".join(
                f"• {flag} {name}" for _code, flag, name in countries
            )
        else:
            country_lines = "—"

        countries_title = "کشورها:" if lang == "fa" else "Countries:"
        sub_title = "لینک اشتراک:" if lang == "fa" else "Subscription URL:"

        text = (
            f"═══ 🆓 {label} ═══\n"
            f"{sub_title}\n{bundle['sub_url']}\n\n"
            f"{countries_title}\n{country_lines}"
        )
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(footer))
    finally:
        db.close()


async def free_config_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Dispatch to per-user claim flow or shared-bundle rendering by kind."""
    admin_id = context.application.bot_data["admin_id"]
    db = SessionLocal()
    try:
        cfg = FreeConfigService(db).get_or_create(admin_id)
        kind = cfg.kind
    finally:
        db.close()
    if kind == "per_user":
        return await free_config_claim(update, context)
    return await _free_config_shared(update, context)


def register_free_config(application: Application) -> None:
    """Wire the free-config handler into the Application."""
    application.add_handler(
        CallbackQueryHandler(free_config_callback, pattern=r"^free_config$")
    )
