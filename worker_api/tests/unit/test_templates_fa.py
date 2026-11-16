"""Unit tests for Persian notification templates.

These verify that the returned strings contain the key data points
(order_id, amount, percentage, etc.) and use Persian copy rather than
the English STUB placeholders from 9A.
"""

from datetime import datetime
from decimal import Decimal

from app.services.notifications.templates_fa import (
    format_admin_new_receipt,
    format_referral_reward,
    format_user_activated,
    format_user_order_approved,
    format_user_order_rejected,
    format_user_receipt_received,
    format_user_subscription_expired,
    format_user_subscription_expiring,
    format_user_suspended_wallet_depleted,
    format_user_traffic_80,
    format_user_traffic_100,
    format_user_welcome,
)

# ---------------------------------------------------------------------------
# Order lifecycle
# ---------------------------------------------------------------------------


def test_format_user_order_approved_fa_contains_key_fields():
    msg = format_user_order_approved(
        order_id=42,
        package_name="Basic",
        limit_gb=20.0,
        expiry_date=datetime(2026, 7, 13),
        region_flag="🇪🇺",
        region_name="Europe",
    )
    assert "#42" in msg
    assert "Basic" in msg
    assert "20" in msg
    assert "2026-07-13" in msg
    assert "🇪🇺" in msg
    assert "Europe" in msg
    # No longer contains the STUB marker
    assert "STUB" not in msg


def test_format_user_order_approved_fa_handles_none_expiry_and_limit():
    msg = format_user_order_approved(
        order_id=99,
        package_name="Premium",
        limit_gb=None,
        expiry_date=None,
        region_flag="🌐",
        region_name="Global",
    )
    # None limit = "نامحدود" (unlimited)
    assert "نامحدود" in msg
    # None expiry = "—"
    assert "—" in msg


def test_format_user_order_rejected_fa_with_reason():
    msg = format_user_order_rejected(42, "فیش نامعتبر")
    assert "#42" in msg
    assert "فیش نامعتبر" in msg
    assert "STUB" not in msg


def test_format_user_order_rejected_fa_without_reason():
    msg = format_user_order_rejected(42, None)
    assert "#42" in msg
    # Should not crash on None reason
    assert "STUB" not in msg


def test_format_user_activated_fa_lists_country_connections():
    msg = format_user_activated(
        package_name="Basic",
        limit_gb=20.0,
        expiry_date=datetime(2026, 7, 13),
        region_flag="🇪🇺",
        region_name="Europe",
        connections={
            "CH": {"ssh": {"primary": "ssh://ch.example.com:22#x"}},
            "DE": {"ssh": {"primary": "ssh://de.example.com:22#y"}},
        },
    )
    assert "Basic" in msg
    assert "20" in msg
    # Each country's connection URL should appear
    assert "ssh://ch.example.com:22#x" in msg
    assert "ssh://de.example.com:22#y" in msg
    assert "SSH" in msg  # protocol label uppercased
    assert "STUB" not in msg


def test_format_user_activated_fa_handles_empty_connections():
    msg = format_user_activated(
        package_name="Basic",
        limit_gb=20.0,
        expiry_date=None,
        region_flag="🇪🇺",
        region_name="Europe",
        connections={},
    )
    # No crash; still has header
    assert "اشتراک شما فعال شد" in msg


def test_format_user_activated_fa_handles_none_connections():
    msg = format_user_activated(
        package_name="Basic",
        limit_gb=20.0,
        expiry_date=None,
        region_flag="🇪🇺",
        region_name="Europe",
        connections=None,
    )
    assert "اشتراک شما فعال شد" in msg


def test_format_referral_reward_fa_decimal_inputs():
    """Referrer reward message uses Decimal (matches caller in _maybe_award_referral)."""
    msg = format_referral_reward(
        reward=Decimal("1000.00"),
        new_balance=Decimal("5000.00"),
    )
    assert "1,000" in msg  # formatted with thousands separator
    assert "5,000" in msg
    assert "STUB" not in msg


# ---------------------------------------------------------------------------
# Traffic alerts
# ---------------------------------------------------------------------------


def test_format_user_traffic_80_fa_includes_percentage_and_usage():
    msg = format_user_traffic_80(used_gb=8.0, limit_gb=10.0, pct=80)
    assert "80" in msg  # percentage
    assert "8.00" in msg  # used
    assert "10.00" in msg  # limit


def test_format_user_traffic_100_fa_basic():
    msg = format_user_traffic_100()
    assert "حجم" in msg or "اشتراک" in msg


def test_format_user_suspended_wallet_depleted_fa_basic():
    msg = format_user_suspended_wallet_depleted()
    assert "متوقف" in msg
    assert "STUB" not in msg


# ---------------------------------------------------------------------------
# Subscription lifecycle
# ---------------------------------------------------------------------------


def test_format_user_subscription_expiring_fa_includes_days():
    msg = format_user_subscription_expiring(days_left=3)
    assert "3" in msg
    assert "روز" in msg  # "days"


def test_format_user_subscription_expired_fa_basic():
    msg = format_user_subscription_expired()
    assert "منقضی" in msg


def test_format_user_receipt_received_fa_includes_order_and_amount():
    msg = format_user_receipt_received(order_id=42, amount_tomans=100000.0)
    assert "#42" in msg
    assert "100,000" in msg  # formatted with thousands separator


def test_format_admin_new_receipt_fa_contains_key_fields():
    """Reseller's 'new receipt' alert lists order id, user, plan, region, amount."""
    msg = format_admin_new_receipt(
        order_id=42,
        username="hasan_abc",
        package_name="Basic",
        region="EU",
        amount=150000.0,
    )
    assert "#42" in msg
    assert "hasan_abc" in msg
    assert "Basic" in msg
    assert "EU" in msg
    assert "150,000" in msg
    assert "رسید جدید" in msg


# ---------------------------------------------------------------------------
# Welcome
# ---------------------------------------------------------------------------


def test_format_user_welcome_fa_contains_bot_name_and_first_name():
    msg = format_user_welcome(bot_display_name="HasanVPN", first_name="Ali")
    assert "HasanVPN" in msg
    assert "Ali" in msg
    assert "سلام" in msg  # Persian greeting
