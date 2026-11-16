"""End-user My Subscription + My Connections handlers (Task 16).

- my_sub_callback: read-only subscription status (status/traffic/expiry)
- connections_callback: country picker view (subscription link + dashboard
  login + decrypted password + per-country buttons). Per-country URIs are
  shown by country_callback (Task 9) when the user taps a country button.

Both are read-only views; no state mutation. ConnectionStringService is
called via generate_all_region_connections(increment_load=False) so merely
viewing connections does not rotate domains or increment load counters, and
every macro-region the user has paid for is shown (not just the primary).
"""

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

from app.core.constants import country_flag, get_country_name
from app.core.database import SessionLocal
from app.models.admin_users import AdminUser
from app.services.credentials.connection_string_service import ConnectionStringService


def _countries_for_user(db, user) -> list:
    """(code, flag, name) tuples for the user's active-region breakdown.
    Mirrors the list connections_callback renders into the country grid."""
    svc = ConnectionStringService(db)
    breakdown = svc.generate_all_region_connections(user, increment_load=False)
    try:
        return [
            (code, country_flag(code), get_country_name(code))
            for code in breakdown.keys()
        ]
    except NameError:
        return [(code, "🌐", code) for code in breakdown.keys()]


def _status_fa(status: str) -> str:
    """Legacy status translation; retained for any external callers."""
    return {
        "active": "فعال ✓",
        "suspended": "معلوق ⛔",
        "expired": "منقضی ⌛",
        "lead": "بدون اشتراک",
    }.get(status, status)


async def my_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Render the v2 hero message (same as on order approval).

    Re-rendering the hero here gives users a consistent experience: tapping
    "اشتراک من" shows the same subscription-link-centric hero with country
    grid, decrypted password, and guide buttons. The password is *not*
    regenerated here — this is a read-only view that decrypts the existing
    ``password_enc`` for display.
    """
    # CallbackQueryHandler(pattern=...) guarantees callback_query; a callback
    # query always carries a user.
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
        if not user:
            await query.edit_message_text("خطا — کاربر یافت نشد.")
            return

        lang = getattr(user, "language", "fa") or "fa"

        if user.status not in ("active", "suspended"):
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup

            from app.services.bots.end_user_keyboards import nav_footer

            if lang == "fa":
                msg = (
                    "═══ 👤 اشتراک من ═══\n"
                    "شما در حال حاضر اشتراک فعالی ندارید.\n"
                    "برای خرید، روی «خرید اشتراک» بزنید."
                )
            else:
                msg = (
                    "═══ 👤 My Subscription ═══\n"
                    "You don't have an active subscription right now.\n"
                    'Tap "Buy" to purchase one.'
                )
            rows = [
                [
                    InlineKeyboardButton(
                        "📦 خرید اشتراک" if lang == "fa" else "📦 Buy",
                        callback_data="buy",
                    )
                ]
            ]
            rows += nav_footer(lang)
            await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(rows))
            return

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        from app.core.constants import MACRO_REGIONS
        from app.core.crypto import decrypt_token
        from app.services.notifications.templates_fa import template_for
        from app.services.url_resolver import (
            get_dashboard_base_url,
            get_subscription_base_url,
        )

        # Decrypt password (may be masked for legacy users pre-migration)
        if user.password_enc:
            try:
                password = decrypt_token(user.password_enc)
            except Exception:
                password = "••••••"
        else:
            password = "••••••"

        # Backfill token for legacy users who fell through before invariant.
        if not user.subscription_token:
            import secrets as _secrets

            user.subscription_token = _secrets.token_hex(16)
            db.commit()

        sub_url = (
            f"{get_subscription_base_url(db, user.admin_id)}"
            f"/api/v1/user/sub/{user.subscription_token}"
        )
        dash_url = get_dashboard_base_url(db, user.admin_id) + "/user/login"

        macro = user.region.macro_region if user.region else "eu"
        svc = ConnectionStringService(db)
        breakdown = svc.generate_all_region_connections(user, increment_load=False)
        countries = [
            (code, country_flag(code), get_country_name(code))
            for code in breakdown.keys()
        ]

        region_info = MACRO_REGIONS.get(
            macro,
            {"flag": "\U0001f310", "name": "Unknown"},
        )
        limit_gb = (
            float(user.traffic_limit_bytes) / 1024**3
            if user.traffic_limit_bytes
            else None
        )
        package_name = ""
        if user.current_order and user.current_order.package_snapshot:
            package_name = user.current_order.package_snapshot.get("name", "")

        tpl = template_for(lang)
        msg = tpl.format_user_activated_v2(
            package_name=package_name,
            limit_gb=limit_gb,
            expiry_date=(
                user.expires_at.strftime("%Y-%m-%d") if user.expires_at else "-"
            ),
            region_flag=region_info["flag"],
            region_name=region_info["name"],
            username=user.username,
            password=password,
            dashboard_url=dash_url,
            subscription_url=sub_url,
            countries=countries,
        )

        from app.services.bots.usage_format import format_remaining
        remaining_block = format_remaining(
            user.traffic_limit_bytes, user.traffic_used_bytes,
            user.expires_at, lang,
        )
        msg = remaining_block + "\n\n" + msg

        guide_labels = {
            "fa": {
                "android": "🤖 اندروید",
                "ios": "🍎 آیفون",
                "windows": "💻 ویندوز",
            },
            "en": {
                "android": "🤖 Android",
                "ios": "🍎 iOS",
                "windows": "💻 Windows",
            },
        }.get(
            lang,
            {
                "android": "🤖 Android",
                "ios": "🍎 iOS",
                "windows": "💻 Windows",
            },
        )
        from app.services.bots.end_user_keyboards import _L, nav_footer

        rows = [
            [
                InlineKeyboardButton(
                    guide_labels["android"], callback_data="guide:android"
                ),
                InlineKeyboardButton(guide_labels["ios"], callback_data="guide:ios"),
                InlineKeyboardButton(
                    guide_labels["windows"], callback_data="guide:windows"
                ),
            ],
        ]
        rows.append(
            [InlineKeyboardButton(_L(lang, "my_orders"), callback_data="orders")]
        )
        rows += nav_footer(lang, quick_switch="connections")
        kb = InlineKeyboardMarkup(rows)

        await query.edit_message_text(msg, reply_markup=kb)
    finally:
        db.close()


async def connections_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show country picker view (replaces old URI dump).

    Displays subscription link + dashboard login + decrypted password at top,
    then inline keyboard with country buttons (3 per row) + reset password + back to sub.
    """
    # CallbackQueryHandler(pattern=...) guarantees callback_query; a callback
    # query always carries a user.
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
        if not user or user.status not in ("active", "suspended"):
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup

            from app.services.bots.end_user_keyboards import nav_footer

            lang = getattr(user, "language", "fa") or "fa"
            if lang == "fa":
                msg = (
                    "═══ 🔗 اتصالات من ═══\n\n"
                    "برای دیدن اتصالات، ابتدا یک اشتراک خریداری کنید."
                )
            else:
                msg = (
                    "═══ 🔗 My Connections ═══\n\n"
                    "Buy a subscription first to see your connections."
                )
            rows = [
                [
                    InlineKeyboardButton(
                        "📦 خرید اشتراک" if lang == "fa" else "📦 Buy",
                        callback_data="buy",
                    )
                ]
            ]
            rows += nav_footer(lang)
            await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(rows))
            return

        # Decrypt password (may be None for legacy users pre-migration)
        from app.core.crypto import decrypt_token

        if user.password_enc:
            try:
                password = decrypt_token(user.password_enc)
            except Exception:
                password = "••••••"  # decrypt failed; user should reset
        else:
            password = "••••••"  # legacy user; needs reset

        # Backfill token for legacy users who fell through before invariant.
        if not user.subscription_token:
            import secrets as _secrets

            user.subscription_token = _secrets.token_hex(16)
            db.commit()

        # Build URLs
        from app.services.url_resolver import (
            get_dashboard_base_url,
            get_subscription_base_url,
        )

        sub_url = f"{get_subscription_base_url(db, user.admin_id)}/api/v1/user/sub/{user.subscription_token}"
        dash_url = get_dashboard_base_url(db, user.admin_id) + "/user/login"

        # Build country list from current region's breakdown
        countries = _countries_for_user(db, user)

        lang = getattr(user, "language", "fa") or "fa"
        from app.services.notifications.templates_fa import template_for

        tpl = template_for(lang)
        msg = tpl.format_my_connections(
            username=user.username,
            password=password,
            dashboard_url=dash_url,
            subscription_url=sub_url,
            countries=countries,
        )

        from app.services.bots.end_user_keyboards import country_picker_keyboard

        kb = country_picker_keyboard(countries, lang=lang)
        await query.edit_message_text(msg, reply_markup=kb)
    finally:
        db.close()


async def pgcty_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Re-render the connections country grid at the requested page (markup only)."""
    query = update.callback_query
    assert query is not None  # CallbackQueryHandler(pattern=r"^pgcty:\d+$")
    await query.answer()
    assert query.data is not None
    page = int(query.data.split(":")[1])
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
        if not user or user.status not in ("active", "suspended"):
            return
        countries = _countries_for_user(db, user)
        lang = getattr(user, "language", "fa") or "fa"
        from app.services.bots.end_user_keyboards import country_picker_keyboard

        await query.edit_message_reply_markup(
            reply_markup=country_picker_keyboard(countries, lang=lang, page=page)
        )
    finally:
        db.close()


async def country_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show one country's 6 protocols. SSH gets field-wise block."""
    # CallbackQueryHandler(pattern=r"^country:") guarantees callback_query and,
    # via the pattern, callback data; a callback query always carries a user.
    query = update.callback_query
    assert query is not None
    await query.answer()
    assert query.data is not None
    tg_user = update.effective_user
    assert tg_user is not None

    country_code = query.data.split(":", 1)[1]  # "country:NL" -> "NL"
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
        if not user:
            await query.edit_message_text("User not found")
            return

        from app.services.credentials.connection_string_service import (
            ConnectionStringService,
            parse_ssh_fields,
        )

        svc = ConnectionStringService(db)
        breakdown = svc.generate_all_region_connections(user, increment_load=False)

        if country_code not in breakdown:
            await query.edit_message_text("Country not available")
            return

        protocols = breakdown[country_code]
        # Build {proto_name: uri} dict + extract SSH fields
        proto_uris = {}
        ssh_fields = None
        for proto, data in protocols.items():
            uri = data.get("primary") if isinstance(data, dict) else ""
            if not uri:
                continue
            proto_uris[proto] = uri
            if proto.lower() == "ssh":
                try:
                    ssh_fields = parse_ssh_fields(uri)
                except ValueError:
                    pass

        lang = getattr(user, "language", "fa") or "fa"
        from app.services.notifications.templates_fa import template_for

        tpl = template_for(lang)
        flag = country_flag(country_code)
        name = get_country_name(country_code)
        msg = tpl.format_country_detail(flag, name, proto_uris, ssh_fields)

        from telegram import InlineKeyboardMarkup

        from app.services.bots.end_user_keyboards import nav_footer

        kb = InlineKeyboardMarkup(nav_footer(lang, back_to="connections"))
        await query.edit_message_text(msg, reply_markup=kb)
    finally:
        db.close()


async def reset_password_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Regenerate password + subscription_token atomically. Reply with both."""
    # CallbackQueryHandler(pattern=...) guarantees callback_query; a callback
    # query always carries a user.
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
        if not user:
            return

        import secrets as _secrets

        from app.core.auth.password import set_password
        from app.services.notifications.templates_fa import template_for
        from app.services.url_resolver import get_subscription_base_url

        new_pw = _secrets.token_urlsafe(6)[:8]
        set_password(user, new_pw)
        user.subscription_token = _secrets.token_hex(16)
        db.commit()

        sub_url = f"{get_subscription_base_url(db, user.admin_id)}/api/v1/user/sub/{user.subscription_token}"
        lang = getattr(user, "language", "fa") or "fa"
        tpl = template_for(lang)
        msg = tpl.format_reset_password_reply(new_pw, sub_url)

        # New message (not edit_message_text) — plaintext password shouldn't get re-edited
        from telegram import InlineKeyboardMarkup

        from app.services.bots.end_user_keyboards import nav_footer

        tg_chat = update.effective_chat
        assert tg_chat is not None
        await context.bot.send_message(
            chat_id=tg_chat.id,
            text=msg,
            reply_markup=InlineKeyboardMarkup(
                nav_footer(lang, quick_switch="connections")
            ),
        )
    finally:
        db.close()


def register(application: Application) -> None:
    """Wire subscription + connections handlers into the Application."""
    application.add_handler(CallbackQueryHandler(my_sub_callback, pattern=r"^my_sub$"))
    application.add_handler(
        CallbackQueryHandler(connections_callback, pattern=r"^connections$")
    )
    application.add_handler(
        CallbackQueryHandler(country_callback, pattern=r"^country:")
    )
    application.add_handler(
        CallbackQueryHandler(reset_password_callback, pattern=r"^reset_password$")
    )
    application.add_handler(
        CallbackQueryHandler(pgcty_callback, pattern=r"^pgcty:\d+$")
    )
