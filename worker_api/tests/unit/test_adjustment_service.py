from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

NOW = datetime(2026, 7, 21, 12, 0, 0)


def _svc():
    from app.services.subscriptions.adjustment_service import AdjustmentService

    db = MagicMock()
    added = []
    db.add.side_effect = lambda r: added.append(r)
    svc = AdjustmentService(db)
    return svc, db, added


def test_extend_days_is_additive_and_audited():
    svc, db, added = _svc()
    user = MagicMock(id=1, expires_at=NOW + timedelta(days=5))
    with patch("app.services.subscriptions.adjustment_service.datetime") as dt:
        dt.now.return_value.replace.return_value = NOW
        adj = svc.extend_days(user, admin_id=2, days=30, reason="promo")
    assert user.expires_at == NOW + timedelta(days=5) + timedelta(days=30)
    assert adj.action == "extend_days"
    assert adj.details["days"] == 30
    assert any(getattr(a, "action", None) == "extend_days" for a in added)


def test_topup_gb_adds_to_existing_limit():
    svc, db, added = _svc()
    user = MagicMock(id=1, traffic_limit_bytes=1 * 1024**3)
    adj = svc.topup_gb(user, admin_id=2, gb=5, reason=None)
    assert user.traffic_limit_bytes == 6 * 1024**3
    assert adj.action == "topup_gb"


def test_topup_gb_from_unlimited_treats_none_as_zero():
    svc, db, added = _svc()
    user = MagicMock(id=1, traffic_limit_bytes=None)
    svc.topup_gb(user, admin_id=2, gb=5, reason=None)
    assert user.traffic_limit_bytes == 5 * 1024**3


def test_edit_regions_calls_set_user_regions_and_audits():
    svc, db, added = _svc()
    user = MagicMock(id=1)
    with patch(
        "app.services.subscriptions.adjustment_service.set_user_regions"
    ) as sur, patch("app.services.subscriptions.adjustment_service.datetime") as dt:
        dt.now.return_value.replace.return_value = NOW
        adj = svc.edit_regions(
            user, admin_id=2, macro_regions=["eu", "as"], reason=None
        )
    sur.assert_called_once()
    assert adj.action == "edit_regions"
    assert adj.details["regions"] == ["eu", "as"]


def test_set_expiry_normalizes_tzaware_to_naive_utc():
    """F4: a tz-aware `when` (dashboard sends ISO "Z"/offset) is converted to
    UTC and stored WITHOUT tzinfo, matching the naive-UTC TIMESTAMP convention."""
    svc, db, added = _svc()
    user = MagicMock(id=1, expires_at=None)
    aware = datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone(timedelta(hours=4)))
    adj = svc.set_expiry(user, admin_id=2, when=aware, reason=None)
    expected = datetime(2026, 7, 31, 20, 0, 0)  # 00:00+04:00 -> 20:00 UTC prior day
    assert user.expires_at == expected
    assert user.expires_at.tzinfo is None
    assert adj.action == "set_expiry"
    assert adj.details["to"] == expected.isoformat()


def test_set_expiry_leaves_naive_input_unchanged():
    """F4: an already-naive `when` is stored as-is (guard no-ops)."""
    svc, db, added = _svc()
    user = MagicMock(id=1, expires_at=None)
    naive = datetime(2026, 8, 1, 0, 0, 0)
    svc.set_expiry(user, admin_id=2, when=naive, reason=None)
    assert user.expires_at == naive
    assert user.expires_at.tzinfo is None
