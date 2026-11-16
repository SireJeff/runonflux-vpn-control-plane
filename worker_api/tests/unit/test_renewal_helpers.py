from datetime import datetime, timedelta

from app.services.subscriptions.renewal_service import compute_new_expiry

NOW = datetime(2026, 7, 21, 12, 0, 0)


def test_additive_when_active():
    current = NOW + timedelta(days=10)
    result = compute_new_expiry(current, 30, NOW)
    assert result == current + timedelta(days=30)  # extends from current expiry


def test_from_now_when_expired():
    current = NOW - timedelta(days=5)
    result = compute_new_expiry(current, 30, NOW)
    assert result == NOW + timedelta(days=30)


def test_from_now_when_no_expiry():
    result = compute_new_expiry(None, 30, NOW)
    assert result == NOW + timedelta(days=30)


from unittest.mock import MagicMock

from app.models.user_regions import UserRegion
from app.services.regions.assignment import set_user_regions


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *a, **k):
        return self

    def all(self):
        return self._rows


def _fake_db(existing_rows):
    db = MagicMock()
    db.query.return_value = _FakeQuery(existing_rows)
    return db


def test_set_regions_creates_rows_first_is_primary():
    db = _fake_db([])
    user = MagicMock(id=1)
    added = []
    db.add.side_effect = lambda row: added.append(row)

    set_user_regions(db, user, ["eu", "as"], NOW)

    assert len(added) == 2
    assert added[0].macro_region == "eu" and added[0].is_primary is True
    assert added[0].region_expires_at is None  # primary is free
    assert added[1].macro_region == "as" and added[1].is_primary is False
    assert added[1].region_expires_at == NOW + timedelta(days=30)


def test_set_regions_removes_dropped_region():
    existing = UserRegion(user_id=1, macro_region="na", is_primary=True)
    db = _fake_db([existing])
    user = MagicMock(id=1)
    db.add.side_effect = lambda row: None

    set_user_regions(db, user, ["eu"], NOW)

    db.delete.assert_called_once_with(existing)


def test_set_regions_preserves_suspended_status_on_existing_nonprimary():
    """F1: re-saving the region set must NOT reactivate a billing-suspended
    non-primary region (that would grant free access). Its status is preserved."""
    eu = UserRegion(user_id=1, macro_region="eu", is_primary=True, status="active")
    as_row = UserRegion(
        user_id=1, macro_region="as", is_primary=False, status="suspended"
    )
    as_row.region_expires_at = NOW - timedelta(days=1)  # already past-due
    db = _fake_db([eu, as_row])
    user = MagicMock(id=1)
    db.add.side_effect = lambda row: None

    # Reseller re-saves the SAME set via the editor (eu primary, as non-primary).
    set_user_regions(db, user, ["eu", "as"], NOW)

    assert as_row.status == "suspended"  # NOT silently reactivated
    assert as_row.is_primary is False
    assert eu.status == "active" and eu.is_primary is True
