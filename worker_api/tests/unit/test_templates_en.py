"""Unit tests for English notification templates — mirror of templates_fa.py."""
from datetime import datetime
from decimal import Decimal

from app.services.notifications.templates_en import (
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


def test_format_user_order_approved_en_contains_key_fields():
    msg = format_user_order_approved(
        order_id=42,
        package_name="Basic",
        limit_gb=20.0,
        expiry_date=datetime(2026, 7, 13),
        region_flag="EU",
        region_name="Europe",
    )
    assert "#42" in msg
    assert "Basic" in msg
    assert "20.0 GB" in msg
    assert "2026-07-13" in msg
    assert "EU" in msg
    assert "Europe" in msg


def test_format_user_order_approved_en_handles_none_expiry_and_limit():
    msg = format_user_order_approved(
        order_id=99,
        package_name="Premium",
        limit_gb=None,
        expiry_date=None,
        region_flag="GL",
        region_name="Global",
    )
    assert "Unlimited" in msg
    assert "-" in msg or "---" in msg


def test_format_user_order_rejected_en_with_reason():
    msg = format_user_order_rejected(42, "Invalid receipt")
    assert "#42" in msg
    assert "Invalid receipt" in msg


def test_format_user_order_rejected_en_without_reason():
    msg = format_user_order_rejected(42, None)
    assert "#42" in msg


def test_format_user_activated_en_lists_country_connections():
    msg = format_user_activated(
        package_name="Basic",
        limit_gb=20.0,
        expiry_date=datetime(2026, 7, 13),
        region_flag="EU",
        region_name="Europe",
        connections={
            "CH": {"ssh": {"primary": "ssh://ch.example.com:22#x"}},
            "DE": {"ssh": {"primary": "ssh://de.example.com:22#y"}},
        },
    )
    assert "Basic" in msg
    assert "20.0 GB" in msg
    assert "ssh://ch.example.com:22#x" in msg
    assert "ssh://de.example.com:22#y" in msg
    assert "SSH" in msg


def test_format_user_activated_en_handles_empty_connections():
    msg = format_user_activated(
        package_name="Basic",
        limit_gb=20.0,
        expiry_date=None,
        region_flag="EU",
        region_name="Europe",
        connections={},
    )
    assert "Your subscription is active" in msg or "active" in msg.lower()


def test_format_user_activated_en_handles_none_connections():
    msg = format_user_activated(
        package_name="Basic",
        limit_gb=20.0,
        expiry_date=None,
        region_flag="EU",
        region_name="Europe",
        connections=None,
    )
    assert "active" in msg.lower()


def test_format_referral_reward_en_decimal_inputs():
    msg = format_referral_reward(
        reward=Decimal("1000.00"),
        new_balance=Decimal("5000.00"),
    )
    assert "1,000" in msg
    assert "5,000" in msg


# ---------------------------------------------------------------------------
# Traffic alerts
# ---------------------------------------------------------------------------


def test_format_user_traffic_80_en_includes_percentage_and_usage():
    msg = format_user_traffic_80(used_gb=8.0, limit_gb=10.0, pct=80)
    assert "80" in msg
    assert "8.00" in msg
    assert "10.00" in msg


def test_format_user_traffic_100_en_basic():
    msg = format_user_traffic_100()
    assert (
        "expired" in msg.lower() or "ended" in msg.lower() or "depleted" in msg.lower()
    )


def test_format_user_suspended_wallet_depleted_en_basic():
    msg = format_user_suspended_wallet_depleted()
    assert "suspend" in msg.lower() or "stop" in msg.lower() or "halt" in msg.lower()


# ---------------------------------------------------------------------------
# Subscription lifecycle
# ---------------------------------------------------------------------------


def test_format_user_subscription_expiring_en_includes_days():
    msg = format_user_subscription_expiring(days_left=3)
    assert "3" in msg
    assert "day" in msg.lower()


def test_format_user_subscription_expired_en_basic():
    msg = format_user_subscription_expired()
    assert "expired" in msg.lower() or "ended" in msg.lower()


def test_format_user_receipt_received_en_includes_order_and_amount():
    msg = format_user_receipt_received(order_id=42, amount_tomans=100000.0)
    assert "#42" in msg
    assert "100,000" in msg


def test_format_admin_new_receipt_en_contains_key_fields():
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
    assert "New Receipt" in msg or "New receipt" in msg


# ---------------------------------------------------------------------------
# Welcome
# ---------------------------------------------------------------------------


def test_format_user_welcome_en_contains_bot_name_and_first_name():
    msg = format_user_welcome(bot_display_name="FluxVPN", first_name="Alice")
    assert "FluxVPN" in msg
    assert "Alice" in msg
    assert "Hi" in msg or "Hello" in msg
