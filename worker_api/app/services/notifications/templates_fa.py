"""Persian notification templates for end-user bot.

Plain text, RTL-friendly. No MarkdownV2 (Telegram parses message text as
plain text when parse_mode is unset, which is what we want).

Functions share identical names with templates_en.py so template_for() can
dispatch by user language without callers knowing which module is active.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Order lifecycle (called by order_service.py)
# ---------------------------------------------------------------------------


def format_user_order_approved(
    order_id: int,
    package_name: str,
    limit_gb: Optional[float],
    expiry_date: Any,
    region_flag: str,
    region_name: str,
) -> str:
    """Sent to end-user when admin approves their receipt. Largely superseded
    by format_user_activated (which is sent immediately after), but kept
    for callers that want a short confirmation without connection strings."""
    traffic = f"{limit_gb} گیگابایت" if limit_gb else "نامحدود"
    expiry = (
        expiry_date.strftime("%Y-%m-%d")
        if hasattr(expiry_date, "strftime") and expiry_date
        else "—"
    )
    return (
        f"═══ ✅ سفارش #{order_id} تایید شد ═══\n"
        f"پلن: {package_name}\n"
        f"حجم: {traffic}\n"
        f"منطقه: {region_flag} {region_name}\n"
        f"انقضا: {expiry}\n"
        "اشتراک شما فعال شد. اتصالات در پیام بعدی."
    )


def format_user_order_rejected(order_id: int, reason: Optional[str]) -> str:
    msg = f"═══ ❌ سفارش #{order_id} رد شد ═══\n"
    if reason:
        msg += f"دلیل: {reason}\n"
    msg += "لطفاً با پشتیبانی تماس بگیرید."
    return msg


def format_user_activated(
    package_name: str,
    limit_gb: Optional[float],
    expiry_date: Any,
    region_flag: str,
    region_name: str,
    connections: Any,
) -> str:
    """Sent to end-user after approve_order generates credentials.
    Lists per-country connection strings."""
    from app.core.constants import country_flag, get_country_name

    traffic = f"{limit_gb} گیگابایت" if limit_gb else "نامحدود"
    expiry = (
        expiry_date.strftime("%Y-%m-%d")
        if hasattr(expiry_date, "strftime") and expiry_date
        else "—"
    )

    lines = [
        "═══ ✅ اشتراک شما فعال شد ═══",
        f"پلن: {package_name}",
        f"حجم: {traffic}",
        f"منطقه: {region_flag} {region_name}",
        f"انقضا: {expiry}",
        "",
        "🔗 اتصالات شما:",
    ]

    if connections:
        for country_code, protocols in connections.items():
            try:
                flag = country_flag(country_code)
                name = get_country_name(country_code)
            except Exception:
                flag = "🌐"
                name = country_code
            lines.append(f"\n{flag} {name}")
            if isinstance(protocols, dict):
                for proto, pc in protocols.items():
                    uri = pc.get("primary") if isinstance(pc, dict) else ""
                    if uri:
                        lines.append(f"  {proto.upper()}: {uri}")

    lines.extend(
        [
            "",
            "می‌توانید اتصالات را بعداً از منوی «اشتراک من» دوباره دریافت کنید.",
        ]
    )
    return "\n".join(lines)


def format_referral_reward(reward: Decimal, new_balance: Decimal) -> str:
    """Sent to referrer when their referral commission lands."""
    reward_f = float(reward)
    balance_f = float(new_balance)
    return (
        "═══ 🎁 پاداش دعوت ═══\n"
        f"شما {reward_f:,.0f} تومان پاداش دعوت دریافت کردید.\n"
        f"موجودی فعلی کیف پول شما: {balance_f:,.0f} تومان"
    )


# ---------------------------------------------------------------------------
# Wallet top-up (Task 6)
# ---------------------------------------------------------------------------


def format_wallet_topup_approved(amount_tomans, new_balance) -> str:
    return (
        "═══ ✅ کیف پول شارژ شد ═══\n"
        f"مبلغ {float(amount_tomans):,.0f} تومان به کیف پول شما اضافه شد.\n"
        f"موجودی فعلی: {float(new_balance):,.0f} تومان"
    )


def format_user_topup_received(order_id: int, amount_tomans: float) -> str:
    return (
        "═══ ✅ درخواست شارژ ثبت شد ═══\n"
        f"شماره پیگیری: #{order_id}\n"
        f"مبلغ: {amount_tomans:,.0f} تومان\n\n"
        "پس از تایید مدیر، موجودی کیف پول شما افزایش می‌یابد."
    )


def format_admin_new_topup(order_id: int, username: str, amount: float, method: str) -> str:
    method_fa = "ارز دیجیتال" if method == "crypto" else "کارت به کارت"
    return (
        "═══ 💰 درخواست شارژ کیف پول ═══\n"
        f"سفارش: #{order_id}\n"
        f"کاربر: {username}\n"
        f"مبلغ: {amount:,.0f} تومان\n"
        f"روش: {method_fa}"
    )


def format_wallet_screen(balance, recent: list) -> str:
    lines = ["═══ 💰 کیف پول ═══", "", f"موجودی: {float(balance):,.0f} تومان"]
    if recent:
        lines += ["", "آخرین تراکنش‌ها:"]
        label = {"topup": "شارژ", "spend": "خرید", "referral": "پاداش دعوت",
                 "refund": "بازگشت وجه"}
        for t, amt, created in recent:
            sign = "+" if float(amt) >= 0 else ""
            lines.append(f"• {label.get(t, t)}: {sign}{float(amt):,.0f} تومان")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Traffic alerts (used by Task 12 — wire into TrafficBillingService)
# ---------------------------------------------------------------------------


def format_user_traffic_80(used_gb: float, limit_gb: float, pct: float) -> str:
    return (
        "═══ ⚠️ هشدار حجم ═══\n"
        f"شما به {pct:.0f}% حجم رسیده‌اید.\n"
        f"مصرف: {used_gb:.2f} از {limit_gb:.2f} گیگابایت\n"
        "برای ادامه، لطفاً خرید جدیدی انجام دهید."
    )


def format_user_traffic_100() -> str:
    return (
        "═══ ⛔ حجم به پایان رسید ═══\n"
        "اشتراک شما تمام شده است.\n"
        "برای ادامه استفاده، لطفاً یک پلن جدید خریداری کنید."
    )


def format_user_suspended_wallet_depleted() -> str:
    """When reseller admin's own wallet runs out and their users get suspended."""
    return (
        "═══ ⛔ سرویس متوقف شد ═══\n"
        "سرویس شما به دلیل عدم شارژ کیف پول مدیر موقتاً متوقف شده است.\n"
        "لطفاً بعداً دوباره تلاش کنید یا با مدیر تماس بگیرید."
    )


# ---------------------------------------------------------------------------
# Subscription lifecycle (used by Task 13 — Celery scheduled tasks)
# ---------------------------------------------------------------------------


def format_user_subscription_expiring(days_left: int) -> str:
    return (
        "═══ ⏰ اشتراک در حال انقضا ═══\n"
        f"اشتراک شما در {days_left} روز منقضی می‌شود.\n"
        "برای تمدید، یک پلن جدید خریداری کنید."
    )


def format_user_subscription_expired() -> str:
    return (
        "═══ ⌛ اشتراک منقضی شد ═══\n"
        "اشتراک شما به پایان رسید.\n"
        "برای ادامه، یک پلن جدید خریداری کنید."
    )


def format_user_receipt_received(order_id: int, amount_tomans: float) -> str:
    return (
        "═══ ✅ سفارش ثبت شد ═══\n"
        f"شماره سفارش: #{order_id}\n"
        f"مبلغ: {amount_tomans:,.0f} تومان\n\n"
        "لطفاً منتظر تایید مدیر بمانید. معمولاً کمتر از ۱ ساعت."
    )


def format_admin_new_receipt(
    order_id: int,
    username: str,
    package_name: str,
    region: str,
    amount: float,
) -> str:
    """Sent to the reseller admin (via platform bot) when an end-user uploads a receipt."""
    return (
        "═══ 🧾 رسید جدید ═══\n"
        f"سفارش: #{order_id}\n"
        f"کاربر: {username}\n"
        f"پلن: {package_name}\n"
        f"منطقه: {region}\n"
        f"مبلغ: {int(amount):,} تومان"
    )


def format_user_crypto_received(order_id: int, amount_tomans: float) -> str:
    return (
        f"✅ شناسه تراکنش شما برای سفارش #{order_id} ثبت شد.\n"
        f"مبلغ: {int(amount_tomans):,} تومان\n"
        "پس از تأیید، اشتراک شما فعال می‌شود."
    )


def format_admin_new_crypto(
    order_id,
    username,
    package_name,
    region,
    amount,
    txid,
) -> str:
    """Sent to the reseller admin (via platform bot) when an end-user submits a crypto TxID."""
    return (
        f"🪙 پرداخت ارز دیجیتال جدید — سفارش #{order_id}\n"
        f"کاربر: {username}\nبسته: {package_name} ({region})\n"
        f"مبلغ: {int(amount):,} تومان\nTxID: {txid}"
    )


# ---------------------------------------------------------------------------
# Welcome (used by Task 14 — end-user /start handler)
# ---------------------------------------------------------------------------


def format_user_welcome(bot_display_name: str, first_name: str) -> str:
    return (
        f"═══ 🔐 {bot_display_name} ═══\n"
        f"سلام {first_name} 👋\n\n"
        "به سرویس VPN خوش آمدید.\n"
        "برای شروع، یکی از گزینه‌های زیر را انتخاب کنید:"
    )


# ---------------------------------------------------------------------------
# Language dispatch
# ---------------------------------------------------------------------------


def template_for(user_language: str):
    """Return the templates module matching the user's language, fa fallback."""
    if (user_language or "fa").lower() == "en":
        from app.services.notifications import templates_en

        return templates_en
    import app.services.notifications.templates_fa as templates_fa

    return templates_fa


# ---------------------------------------------------------------------------
# Connections redesign (v2): subscription-link-centric hero + my_connections
# ---------------------------------------------------------------------------


def format_user_activated_v2(
    package_name: str,
    limit_gb: float,
    expiry_date: str,
    region_flag: str,
    region_name: str,
    username: str,
    password: str,
    dashboard_url: str,
    subscription_url: str,
    countries: list,  # list of (code, flag, name_fa) tuples
) -> str:
    """Hero message sent on order approval. Subscription-link-centric."""
    # Build country grid (3 per row)
    lines = []
    for i, (code, flag, name) in enumerate(countries):
        if i % 3 == 0 and i > 0:
            lines.append("")
        lines.append(f"{flag} {name}   ")
    country_grid = "".join(lines).strip()

    return f"""═══ ✅ اشتراک شما فعال شد ═══

📦 پکیج: {package_name}
📊 حجم: {limit_gb} گیگابایت
🗓 انقضا: {expiry_date}
🌍 منطقه: {region_flag} {region_name}

━━━━━━━━━━━━━━━━━━
👤 پنل کاربری

🔗 آدرس: {dashboard_url}
🆔 نام کاربری: {username}
🔑 رمز عبور: {password}

» برای تغییر رمز، پس از ورود به پنل کاربری، به بخش تنظیمات بروید.

━━━━━━━━━━━━━━━━━━
🔗 لینک اشتراک

این لینک را در کلاینت خود وارد کنید تا تمام اتصالات به‌طور خودکار بارگذاری شوند:

👉 {subscription_url}

━━━━━━━━━━━━━━━━━━
🌐 کشورهای قابل دسترسی

{country_grid}

━━━━━━━━━━━━━━━━━━
📱 پروتکل‌ها
SSH • SS • VLESS • Trojan • Outline • HTTP Proxy

» برای دیدن لینک هر کشور، دکمه «🔗 اتصالات من» را بزنید."""


def format_my_connections(
    username: str,
    password: str,
    dashboard_url: str,
    subscription_url: str,
    countries: list,
) -> str:
    """My Connections view (country picker). Replaces URI dump."""
    lines = []
    for i, (code, flag, name) in enumerate(countries):
        if i % 3 == 0 and i > 0:
            lines.append("")
        lines.append(f"{flag} {name}   ")
    country_grid = "".join(lines).strip()

    return f"""═══ 🔗 اتصالات من ═══

🔗 لینک اشتراک:
👉 {subscription_url}

👤 پنل کاربری:
🔗 {dashboard_url}
🆔 {username}
🔑 {password}

━━━━━━━━━━━━━━━━━━
🌐 یک کشور را انتخاب کنید از طریق دکمه‌های زیر:

{country_grid}"""


# ---------------------------------------------------------------------------
# Country detail + guides + reset (v3 — connections redesign)
# ---------------------------------------------------------------------------


def format_country_detail(
    country_flag: str,
    country_name_fa: str,
    protocols: dict,  # {protocol_name: uri}
    ssh_fields: Optional[dict] = None,  # {host, port, username, password}
) -> str:
    """Per-country detail view. SSH gets field-wise block."""
    lines = [f"═══ {country_flag} {country_name_fa} ═══", ""]

    for proto, uri in protocols.items():
        lines.append(f"━━━ {proto.upper()} ━━━")
        lines.append(f"🔗 {uri}")
        if proto.lower() == "ssh" and ssh_fields:
            lines.append("")
            lines.append("📋 جزئیات اتصال (برای PuTTY/Termius):")
            lines.append(f"🌐 هاست: {ssh_fields['host']}")
            lines.append(f"🔌 پورت: {ssh_fields['port']}")
            lines.append(f"🆔 نام کاربری: {ssh_fields['username']}")
            lines.append(f"🔑 رمز عبور: {ssh_fields['password']}")
        lines.append("")

    return "\n".join(lines).rstrip()


def _render_apps_block(apps: list) -> str:
    """Render the recommended-clients block. Skips the URL line when empty.

    Args:
        apps: list of (number_emoji, label, url) — url may be "".
    """
    lines = []
    for num, label, url in apps:
        if url:
            lines.append(f"{num} {label}\n🔗 {url}")
        else:
            lines.append(f"{num} {label}")
    return "\n".join(lines)


def format_guide_android(android_urls: dict) -> str:
    """Android setup guide. URLs come from settings (per-deployment config)."""
    apps = _render_apps_block(
        [
            ("1️⃣", "Throne (رایگان)", android_urls.get("throne", "")),
            ("2️⃣", "Hiddify (رایگان)", android_urls.get("hiddify", "")),
            ("3️⃣", "NekoBox (رایگان)", android_urls.get("nekobox", "")),
        ]
    )
    return f"""═══ 🤖 راهنمای اندروید ═══

📱 کلاینت‌های پیشنهادی:

{apps}

━━━━━━━━━━━━━━━━━━
📋 مراحل اتصال:

۱. یکی از کلاینت‌های بالا را نصب کنید.
۲. اپ را باز کنید و روی «+» بزنید.
۳. گزینه «Subscription URL» را انتخاب کنید.
۴. لینک اشتراک خود را کپی و وارد کنید.
۵. روی «Update» بزنید.
۶. یک کشور را انتخاب کنید.
۷. دکمه اتصال را بزنید. ✓

━━━━━━━━━━━━━━━━━━
⚠️ مشکلات متداول:

• قطع می‌شود: DNS را روی 1.1.1.1 تنظیم کنید.
• کند است: کشور دیگری را امتحان کنید.
• کار نمی‌کند: Safemode را فعال کنید."""


def format_guide_ios(ios_urls: dict) -> str:
    """iOS setup guide."""
    apps = _render_apps_block(
        [
            ("1️⃣", "Throne (رایگان)", ios_urls.get("throne", "")),
            ("2️⃣", "Hiddify (رایگان)", ios_urls.get("hiddify", "")),
            ("3️⃣", "Streisand (رایگان)", ios_urls.get("streisand", "")),
        ]
    )
    return f"""═══ 🍎 راهنمای آیفون ═══

📱 کلاینت‌های پیشنهادی:

{apps}

━━━━━━━━━━━━━━━━━━
📋 مراحل اتصال:

۱. یکی از کلاینت‌های بالا را نصب کنید.
۲. اپ را باز کنید.
۳. روی «+» بزنید → «Add Subscription».
۴. لینک اشتراک را کپی و وارد کنید.
۵. روی «Update» بزنید.
۶. کشور موردنظر را انتخاب کنید.
۷. دکمه اتصال را بزنید. ✓

━━━━━━━━━━━━━━━━━━
⚠️ نکات:

• برای اولین اتصال، iOS اجازه افزودن VPN می‌خواهد — تأیید کنید.
• اگر اتصال برقرار نشد: Settings → General → VPN & Device Management را بررسی کنید."""


def format_guide_windows(windows_urls: dict) -> str:
    """Windows setup guide."""
    apps = _render_apps_block(
        [
            ("1️⃣", "Throne (رایگان)", windows_urls.get("throne", "")),
            ("2️⃣", "Nekoray (رایگان)", windows_urls.get("nekoray", "")),
            ("3️⃣", "Hiddify (رایگان)", windows_urls.get("hiddify", "")),
        ]
    )
    return f"""═══ 💻 راهنمای ویندوز ═══

💻 کلاینت‌های پیشنهادی:

{apps}

━━━━━━━━━━━━━━━━━━
📋 مراحل اتصال:

۱. فایل نصبی را دانلود و اجرا کنید.
۲. اپ را باز کنید.
۳. منوی Program → «Add profile from subscription URL».
۴. لینک اشتراک را وارد و Update بزنید.
۵. سرور موردنظر را از لیست انتخاب کنید.
۶. روی «Start» بزنید. ✓
۷. برای فعال کردن پروکسی سیستم: حالت «Tun Mode» یا «System Proxy» را روشن کنید.

━━━━━━━━━━━━━━━━━━
⚠️ نکات:

• اگر سایت‌ها باز نمی‌شوند: System Proxy را بررسی کنید.
• اگر خطای cert داد: Settings → Allow Insecure را فعال کنید."""


def format_reset_password_reply(new_password: str, new_subscription_url: str) -> str:
    """Reply after user taps Reset Password button. Shows new credentials."""
    return f"""✅ رمز عبور و لینک اشتراک شما بازنشانی شد

🔑 رمز جدید: {new_password}
🔗 لینک اشتراک جدید: {new_subscription_url}

» لینک‌های قبلی دیگر کار نمی‌کنند. کلاینت خود را با لینک جدید به‌روز کنید."""


# ---------------------------------------------------------------------------
# Phase 3: effective-TLD change notice (per-purpose, changed-domain).
# ---------------------------------------------------------------------------

TLD_PURPOSE_LABELS = {
    "fdm": "اتصال",
    "subscription": "لینک اشتراک",
    "dashboard": "پنل کاربر",
    "admin_panel": "پنل مدیریت",
}


def format_tld_effective_changed(purpose_label: str, new_domain: str) -> str:
    """Sent to end-users when their effective TLD for a purpose changes
    (deactivate/delete migration or pin change). Bilingual counterpart lives
    in templates_en.format_tld_effective_changed."""
    return (
        f"🔗 {purpose_label} شما اکنون {new_domain} است.\n"
        "برای به‌روزرسانی، 🔗 اتصالات من را بزنید."
    )


def format_tld_changed_notice() -> str:
    """Sent to end-users when the subscription/dashboard TLD changes."""
    return (
        "✨ لینک‌های اتصال شما به‌روزرسانی شد.\n"
        "برای دیدن لینک‌های جدید، «🔗 اتصالات من» را بزنید."
    )
