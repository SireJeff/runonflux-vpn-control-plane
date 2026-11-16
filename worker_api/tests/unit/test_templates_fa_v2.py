"""Tests for v2 templates (hero + my_connections) in Persian."""
from app.services.notifications.templates_fa import (
    format_my_connections,
    format_user_activated_v2,
)


def test_format_user_activated_v2_contains_subscription_url():
    msg = format_user_activated_v2(
        package_name="Lite (1m)",
        limit_gb=20.0,
        expiry_date="2026-07-19",
        region_flag="🇪🇺",
        region_name="اروپا",
        username="user_abc",
        password="secret123",
        dashboard_url="https://panel.test/user/login",
        subscription_url="https://api.test/sub/token",
        countries=[("NL", "🇳🇱", "هلند"), ("DE", "🇩🇪", "آلمان")],
    )
    assert "https://api.test/sub/token" in msg
    assert "secret123" in msg
    assert "user_abc" in msg
    assert "Lite (1m)" in msg
    assert "🇳🇱" in msg
    assert "🇩🇪" in msg


def test_format_user_activated_v2_fits_in_telegram_limit():
    """Persian hero with 7 countries must fit in 4096 chars."""
    countries = [("CC%d" % i, "🌐", "Country%d" % i) for i in range(7)]
    msg = format_user_activated_v2(
        package_name="Long Package Name Here",
        limit_gb=100.0,
        expiry_date="2026-12-31",
        region_flag="🇪🇺",
        region_name="اروپا",
        username="a" * 30,
        password="b" * 20,
        dashboard_url="https://panel.example.com/user/login",
        subscription_url="https://api.example.com/api/v1/user/sub/" + "x" * 32,
        countries=countries,
    )
    assert len(msg) <= 4096, f"Hero is {len(msg)} chars, exceeds Telegram limit"


def test_format_my_connections_contains_all_sections():
    msg = format_my_connections(
        username="user_abc",
        password="secret123",
        dashboard_url="https://panel.test/user/login",
        subscription_url="https://api.test/sub/token",
        countries=[("NL", "🇳🇱", "هلند")],
    )
    assert "user_abc" in msg
    assert "secret123" in msg
    assert "https://api.test/sub/token" in msg
    assert "🇳🇱" in msg
