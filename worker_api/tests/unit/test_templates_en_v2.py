"""Tests for v2 templates (hero + my_connections) in English."""
from app.services.notifications.templates_en import (
    format_my_connections,
    format_user_activated_v2,
)


def test_format_user_activated_v2_english_text():
    msg = format_user_activated_v2(
        package_name="Lite (1m)",
        limit_gb=20.0,
        expiry_date="2026-07-19",
        region_flag="🇪🇺",
        region_name="Europe",
        username="user_abc",
        password="secret123",
        dashboard_url="https://panel.test/user/login",
        subscription_url="https://api.test/sub/token",
        countries=[("NL", "🇳🇱", "Netherlands")],
    )
    assert "Subscription Activated" in msg
    assert "User Portal" in msg
    assert "Subscription Link" in msg
    assert "secret123" in msg


def test_format_user_activated_v2_fits_in_telegram_limit():
    """English hero with 7 countries must fit in 4096 chars."""
    countries = [("CC%d" % i, "🌐", "Country%d" % i) for i in range(7)]
    msg = format_user_activated_v2(
        package_name="Long Package Name Here",
        limit_gb=100.0,
        expiry_date="2026-12-31",
        region_flag="🇪🇺",
        region_name="Europe",
        username="a" * 30,
        password="b" * 20,
        dashboard_url="https://panel.example.com/user/login",
        subscription_url="https://api.example.com/api/v1/user/sub/" + "x" * 32,
        countries=countries,
    )
    assert len(msg) <= 4096


def test_format_my_connections_english_text():
    msg = format_my_connections(
        username="u",
        password="p",
        dashboard_url="https://panel.test/user/login",
        subscription_url="https://api.test/sub/token",
        countries=[("NL", "🇳🇱", "Netherlands")],
    )
    assert "My Connections" in msg
    assert "Subscription Link" in msg
    assert "User Portal" in msg
