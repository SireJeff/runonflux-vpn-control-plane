"""
Notification message templates for the reseller Telegram bot.
Plain text, copyable, monospace-friendly. No MarkdownV2.
"""

from typing import Dict, Optional


def format_user_created(
    username: str,
    password: str,
    macro_region: str,
    region_name: str,
    traffic_limit_gb: Optional[float],
    connection_strings: Optional[Dict] = None,
    monitoring_url: Optional[str] = None,
    subscription_url: Optional[str] = None,
) -> str:
    """Format a new VPN user notification with connections grouped by country."""
    from app.core.constants import MACRO_REGIONS, country_flag, get_country_name

    traffic = f"{traffic_limit_gb} GB" if traffic_limit_gb is not None else "Unlimited"
    lines: list[str] = []

    lines.append(f"Username: {username}")
    lines.append(f"Password: {password}")

    if macro_region and macro_region != "N/A":
        info = MACRO_REGIONS.get(macro_region, {})
        lines.append(f"Region: {info.get('flag', '')} {region_name}")

    lines.append(f"Traffic: {traffic}")

    if subscription_url:
        lines.append(f"Subscription: {subscription_url}")

    # connection_strings shape: {country_code: {protocol: {primary, fallbacks}}}
    if connection_strings:
        for country_code, protocols in connection_strings.items():
            flag = country_flag(country_code)
            name = get_country_name(country_code)
            lines.append("")
            lines.append(f"{flag} {name}")
            for proto, pc in protocols.items():
                uri = pc.get("primary", "") if isinstance(pc, dict) else ""
                if uri:
                    lines.append(f"  {proto.upper()}: {uri}")

    if monitoring_url:
        lines.append("")
        lines.append(f"Dashboard: {monitoring_url}")

    return "\n".join(lines)


def format_registration_approved(
    username: str,
    password: str,
    dashboard_url: str,
) -> str:
    """Format admin registration approval notification."""
    lines = [
        "Your admin account has been approved.",
        "",
        f"Username: {username}",
        f"Password: {password}",
        "",
        f"Dashboard: {dashboard_url}",
    ]
    return "\n".join(lines)


def format_new_registration_pending(
    username: str,
    display_name: str,
    telegram_id: int,
) -> str:
    """Format pending registration alert sent to superadmin."""
    lines = [
        "New Registration Pending",
        "",
        f"Username: {username}",
        f"Display Name: {display_name}",
        f"Telegram ID: {telegram_id}",
    ]
    return "\n".join(lines)


def format_wallet_low(balance: float) -> str:
    """Format low wallet balance warning."""
    return f"Wallet balance low: ${balance:.2f}\nPlease top up to avoid service interruption."


def format_wallet_depleted() -> str:
    """Format wallet depleted notification."""
    return "Wallet depleted ($0.00).\nAll users have been suspended. Top up immediately to restore."


def format_traffic_warning(
    username: str,
    used_gb: float,
    limit_gb: float,
    percentage: float,
) -> str:
    """Format traffic usage warning at 80% threshold."""
    return f"Traffic warning: {username}\n{used_gb:.2f} / {limit_gb:.2f} GB ({percentage:.0f}%)"


def format_traffic_exceeded(
    username: str,
    used_gb: float,
    limit_gb: float,
) -> str:
    """Format traffic limit exceeded notification."""
    return f"Traffic limit exceeded: {username}\n{used_gb:.2f} / {limit_gb:.2f} GB\nAccess suspended."


def format_wire_order_approved(
    amount_usd: float,
    new_balance: float,
) -> str:
    """Format wire transfer order approval notification."""
    return f"Wire order approved\nCredit: ${amount_usd:.2f}\nNew balance: ${new_balance:.2f}"


def format_wire_order_rejected(reason: Optional[str] = None) -> str:
    """Format wire transfer order rejection notification."""
    msg = "Wire order rejected."
    if reason:
        msg += f"\nReason: {reason}"
    return msg


def format_user_suspended(
    username: str,
    reason: str,
) -> str:
    """Format user auto-suspension notification."""
    return f"User suspended: {username}\nReason: {reason}"


def format_dns_dark_tld_alert(
    tld_domain: str,
    provider: str,
    failed: int,
    sample: str,
) -> str:
    """Superadmin alert: an fdm TLD is fully DNS-dark (0 healthy domains, DNS
    provider rejecting creates). Routing to it is gated; fix the zone. Plain
    text, monospace-friendly (no MarkdownV2). Spec §4.3."""
    sample_line = f"Provider error: {sample}" if sample else "Provider error: (none)"
    return (
        f"DNS zone down: {tld_domain}\n"
        f"Provider: {provider} — {failed} domain(s) failed this cycle.\n"
        f"{sample_line}\n"
        f"Routing has been gated away from this TLD. Fix the DNS zone."
    )
