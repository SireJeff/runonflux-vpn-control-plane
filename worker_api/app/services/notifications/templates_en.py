"""English notification templates for end-user bot.

Plain text. No MarkdownV2 (Telegram parses message text as plain text when
parse_mode is unset, which is what we want).

Functions share identical names with templates_fa.py so template_for() can
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
    """Sent to end-user when admin approves their receipt."""
    traffic = f"{limit_gb} GB" if limit_gb else "Unlimited"
    expiry = (
        expiry_date.strftime("%Y-%m-%d")
        if hasattr(expiry_date, "strftime") and expiry_date
        else "---"
    )
    return (
        f"== Order #{order_id} Approved ==\n"
        f"Plan: {package_name}\n"
        f"Traffic: {traffic}\n"
        f"Region: {region_flag} {region_name}\n"
        f"Expiry: {expiry}\n"
        "Your subscription is active. Connections in next message."
    )


def format_user_order_rejected(order_id: int, reason: Optional[str]) -> str:
    msg = f"== Order #{order_id} Rejected ==\n"
    if reason:
        msg += f"Reason: {reason}\n"
    msg += "Please contact support for assistance."
    return msg


def format_user_activated(
    package_name: str,
    limit_gb: Optional[float],
    expiry_date: Any,
    region_flag: str,
    region_name: str,
    connections: Any,
) -> str:
    """Sent to end-user after approve_order generates credentials."""
    from app.core.constants import country_flag, get_country_name

    traffic = f"{limit_gb} GB" if limit_gb else "Unlimited"
    expiry = (
        expiry_date.strftime("%Y-%m-%d")
        if hasattr(expiry_date, "strftime") and expiry_date
        else "---"
    )

    lines = [
        "== Your Subscription is Active ==",
        f"Plan: {package_name}",
        f"Traffic: {traffic}",
        f"Region: {region_flag} {region_name}",
        f"Expiry: {expiry}",
        "",
        "Your connections:",
    ]

    if connections:
        for country_code, protocols in connections.items():
            try:
                flag = country_flag(country_code)
                name = get_country_name(country_code)
            except Exception:
                flag = "GL"
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
            'You can retrieve your connections later from "My Subscription" menu.',
        ]
    )
    return "\n".join(lines)


def format_referral_reward(reward: Decimal, new_balance: Decimal) -> str:
    """Sent to referrer when their referral commission lands."""
    reward_f = float(reward)
    balance_f = float(new_balance)
    return (
        "== Referral Reward ==\n"
        f"You earned {reward_f:,.0f} Tomans as a referral reward.\n"
        f"Your current wallet balance: {balance_f:,.0f} Tomans"
    )


# ---------------------------------------------------------------------------
# Wallet top-up (Task 6)
# ---------------------------------------------------------------------------


def format_wallet_topup_approved(amount_tomans, new_balance) -> str:
    return (
        "═══ ✅ Wallet Topped Up ═══\n"
        f"{float(amount_tomans):,.0f} T was added to your wallet.\n"
        f"Current balance: {float(new_balance):,.0f} T"
    )


def format_user_topup_received(order_id: int, amount_tomans: float) -> str:
    return (
        "═══ ✅ Top-up Submitted ═══\n"
        f"Ref: #{order_id}\n"
        f"Amount: {amount_tomans:,.0f} T\n\n"
        "Your balance will increase after admin approval."
    )


def format_admin_new_topup(order_id: int, username: str, amount: float, method: str) -> str:
    return (
        "═══ 💰 Wallet Top-up Request ═══\n"
        f"Order: #{order_id}\nUser: {username}\n"
        f"Amount: {amount:,.0f} T\nMethod: {method}"
    )


def format_wallet_screen(balance, recent: list) -> str:
    lines = ["═══ 💰 Wallet ═══", "", f"Balance: {float(balance):,.0f} T"]
    if recent:
        lines += ["", "Recent transactions:"]
        label = {"topup": "Top-up", "spend": "Purchase",
                 "referral": "Referral reward", "refund": "Refund"}
        for t, amt, created in recent:
            sign = "+" if float(amt) >= 0 else ""
            lines.append(f"• {label.get(t, t)}: {sign}{float(amt):,.0f} T")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Traffic alerts
# ---------------------------------------------------------------------------


def format_user_traffic_80(used_gb: float, limit_gb: float, pct: float) -> str:
    return (
        "== Traffic Alert ==\n"
        f"You have used {pct:.0f}% of your traffic.\n"
        f"Usage: {used_gb:.2f} of {limit_gb:.2f} GB\n"
        "To continue, please purchase a new plan."
    )


def format_user_traffic_100() -> str:
    return (
        "== Traffic Depleted ==\n"
        "Your subscription has reached its traffic limit.\n"
        "To continue using the service, please purchase a new plan."
    )


def format_user_suspended_wallet_depleted() -> str:
    """When reseller admin's own wallet runs out and their users get suspended."""
    return (
        "== Service Suspended ==\n"
        "Your service has been temporarily suspended due to the reseller's\n"
        "wallet being depleted. Please try again later or contact support."
    )


# ---------------------------------------------------------------------------
# Subscription lifecycle
# ---------------------------------------------------------------------------


def format_user_subscription_expiring(days_left: int) -> str:
    return (
        "== Subscription Expiring ==\n"
        f"Your subscription expires in {days_left} days.\n"
        "To renew, please purchase a new plan."
    )


def format_user_subscription_expired() -> str:
    return (
        "== Subscription Expired ==\n"
        "Your subscription has ended.\n"
        "To continue, please purchase a new plan."
    )


def format_user_receipt_received(order_id: int, amount_tomans: float) -> str:
    return (
        "== Order Submitted ==\n"
        f"Order ID: #{order_id}\n"
        f"Amount: {amount_tomans:,.0f} Tomans\n\n"
        "Please wait for admin confirmation. Usually within 1 hour."
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
        "== New Receipt ==\n"
        f"Order: #{order_id}\n"
        f"User: {username}\n"
        f"Plan: {package_name}\n"
        f"Region: {region}\n"
        f"Amount: {int(amount):,} Tomans"
    )


def format_user_crypto_received(order_id: int, amount_tomans: float) -> str:
    return (
        f"✅ Your transaction ID for order #{order_id} was recorded.\n"
        f"Amount: {int(amount_tomans):,} Tomans\n"
        "Your subscription activates once it is verified."
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
        f"🪙 New crypto payment — order #{order_id}\n"
        f"User: {username}\nPackage: {package_name} ({region})\n"
        f"Amount: {int(amount):,} Tomans\nTxID: {txid}"
    )


# ---------------------------------------------------------------------------
# Welcome
# ---------------------------------------------------------------------------


def format_user_welcome(bot_display_name: str, first_name: str) -> str:
    return (
        f"== {bot_display_name} ==\n"
        f"Hi {first_name}\n\n"
        "Welcome to the VPN service.\n"
        "Choose one of the options below to get started:"
    )


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
    countries: list,  # list of (code, flag, name) tuples
) -> str:
    """Hero message sent on order approval. Subscription-link-centric."""
    lines = []
    for i, (code, flag, name) in enumerate(countries):
        if i % 3 == 0 and i > 0:
            lines.append("")
        lines.append(f"{flag} {name}   ")
    country_grid = "".join(lines).strip()

    return f"""═══ ✅ Subscription Activated ═══

📦 Package: {package_name}
📊 Data: {limit_gb} GB
🗓 Expires: {expiry_date}
🌍 Region: {region_flag} {region_name}

━━━━━━━━━━━━━━━━━━
👤 User Portal

🔗 URL: {dashboard_url}
🆔 Username: {username}
🔑 Password: {password}

» Change your password in portal settings after first login.

━━━━━━━━━━━━━━━━━━
🔗 Subscription Link

Paste this into your client to auto-import all configs:

👉 {subscription_url}

━━━━━━━━━━━━━━━━━━
🌐 Available Countries

{country_grid}

━━━━━━━━━━━━━━━━━━
📱 Protocols
SSH • SS • VLESS • Trojan • Outline • HTTP Proxy

» Tap "My Connections" to view per-country links."""


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

    return f"""═══ 🔗 My Connections ═══

🔗 Subscription Link:
👉 {subscription_url}

👤 User Portal:
🔗 {dashboard_url}
🆔 {username}
🔑 {password}

━━━━━━━━━━━━━━━━━━
🌐 Select a country via the buttons below:

{country_grid}"""


# ---------------------------------------------------------------------------
# Country detail + guides + reset (v3 — connections redesign)
# ---------------------------------------------------------------------------


def format_country_detail(
    country_flag: str,
    country_name_fa: str,  # param name kept for parity; receives English name when called from en template
    protocols: dict,
    ssh_fields: Optional[dict] = None,
) -> str:
    """Per-country detail view (English). SSH gets field-wise block."""
    lines = [f"═══ {country_flag} {country_name_fa} ═══", ""]

    for proto, uri in protocols.items():
        lines.append(f"━━━ {proto.upper()} ━━━")
        lines.append(f"🔗 {uri}")
        if proto.lower() == "ssh" and ssh_fields:
            lines.append("")
            lines.append("📋 Connection Details (for PuTTY/Termius):")
            lines.append(f"🌐 Host: {ssh_fields['host']}")
            lines.append(f"🔌 Port: {ssh_fields['port']}")
            lines.append(f"🆔 Username: {ssh_fields['username']}")
            lines.append(f"🔑 Password: {ssh_fields['password']}")
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
    apps = _render_apps_block(
        [
            ("1️⃣", "Throne (Free)", android_urls.get("throne", "")),
            ("2️⃣", "Hiddify (Free)", android_urls.get("hiddify", "")),
            ("3️⃣", "NekoBox (Free)", android_urls.get("nekobox", "")),
        ]
    )
    return f"""═══ 🤖 Android Setup ═══

📱 Recommended Clients:

{apps}

━━━━━━━━━━━━━━━━━━
📋 Setup Steps:

1. Install one of the clients above.
2. Open the app, tap "+".
3. Select "Subscription URL".
4. Copy your subscription link and paste here.
5. Tap "Update".
6. Pick a country.
7. Tap connect. ✓

━━━━━━━━━━━━━━━━━━
⚠️ Common Issues:

• Drops? Set DNS to 1.1.1.1.
• Slow? Try a different country.
• Not working? Enable Safemode in app settings."""


def format_guide_ios(ios_urls: dict) -> str:
    apps = _render_apps_block(
        [
            ("1️⃣", "Throne (Free)", ios_urls.get("throne", "")),
            ("2️⃣", "Hiddify (Free)", ios_urls.get("hiddify", "")),
            ("3️⃣", "Streisand (Free)", ios_urls.get("streisand", "")),
        ]
    )
    return f"""═══ 🍎 iOS Setup ═══

📱 Recommended Clients:

{apps}

━━━━━━━━━━━━━━━━━━
📋 Setup Steps:

1. Install one of the clients above.
2. Open the app.
3. Tap "+" → "Add Subscription".
4. Paste your subscription link.
5. Tap "Update".
6. Pick a country.
7. Tap connect. ✓

━━━━━━━━━━━━━━━━━━
⚠️ Notes:

• First connection: iOS will ask to add VPN profile — approve.
• If connection fails: check Settings → General → VPN & Device Management."""


def format_guide_windows(windows_urls: dict) -> str:
    apps = _render_apps_block(
        [
            ("1️⃣", "Throne (Free)", windows_urls.get("throne", "")),
            ("2️⃣", "Nekoray (Free)", windows_urls.get("nekoray", "")),
            ("3️⃣", "Hiddify (Free)", windows_urls.get("hiddify", "")),
        ]
    )
    return f"""═══ 💻 Windows Setup ═══

💻 Recommended Clients:

{apps}

━━━━━━━━━━━━━━━━━━
📋 Setup Steps:

1. Download and run the installer.
2. Open the app.
3. Program menu → "Add profile from subscription URL".
4. Paste your subscription link and tap Update.
5. Pick a server from the list.
6. Tap "Start". ✓
7. Enable "Tun Mode" or "System Proxy" for system-wide routing.

━━━━━━━━━━━━━━━━━━
⚠️ Notes:

• Sites not loading? Check System Proxy.
• Cert error? Enable Settings → Allow Insecure."""


def format_reset_password_reply(new_password: str, new_subscription_url: str) -> str:
    return f"""✅ Password and subscription link reset

🔑 New password: {new_password}
🔗 New subscription link: {new_subscription_url}

» Previous links no longer work. Update your client with the new link."""


# ---------------------------------------------------------------------------
# Phase 3: effective-TLD change notice (per-purpose, changed-domain).
# ---------------------------------------------------------------------------

TLD_PURPOSE_LABELS = {
    "fdm": "VPN connection",
    "subscription": "subscription link",
    "dashboard": "user panel",
    "admin_panel": "admin panel",
}


def format_tld_effective_changed(purpose_label: str, new_domain: str) -> str:
    """Sent to end-users when their effective TLD for a purpose changes
    (deactivate/delete migration or pin change). Bilingual counterpart lives
    in templates_fa.format_tld_effective_changed."""
    return (
        f"🔗 Your {purpose_label} is now {new_domain}.\n"
        "Tap 🔗 My Connections to refresh your link."
    )


def format_tld_changed_notice() -> str:
    """Sent to end-users when the subscription/dashboard TLD changes."""
    return (
        "✨ Your connection links have been updated.\n"
        "Tap “🔗 My Connections” to view the new links."
    )
