from datetime import datetime, timedelta, timezone

from app.services.bots.usage_format import format_remaining

GB = 1024 ** 3


def test_normal_usage():
    now = datetime(2026, 8, 18, tzinfo=timezone.utc).replace(tzinfo=None)
    exp = now + timedelta(days=28)
    s = format_remaining(100 * GB, 12 * GB, exp, "fa", now=now)
    assert "88" in s        # remaining GB (100-12)
    assert "28" in s        # days remaining


def test_unlimited_traffic():
    s = format_remaining(None, 5 * GB, None, "fa")
    assert "نامحدود" in s
    assert "بدون انقضا" in s


def test_expired_shows_zero_days():
    now = datetime(2026, 8, 18, tzinfo=timezone.utc).replace(tzinfo=None)
    exp = now - timedelta(days=3)
    s = format_remaining(10 * GB, 10 * GB, exp, "en", now=now)
    assert "0" in s
