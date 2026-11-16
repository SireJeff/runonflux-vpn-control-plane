"""Unit tests for end-user notification wiring in TrafficBillingService.

Verifies that process_traffic_report and _suspend_admin_users call
NotificationRouter.send_to_end_user with the correct FA templates.
Admin-side alerts (existing behavior) are mocked away via get_redis=None
so we can focus on the new end-user path.
"""

import sys
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

# Import the module through the normal import mechanism (the billing package
# has circular-import issues with importlib loading). We then grab the ref
# from sys.modules so @patch.object(_mod, ...) targets the correct object.
from app.services.billing import traffic_billing_service

_mod = sys.modules["app.services.billing.traffic_billing_service"]

TrafficBillingService = _mod.TrafficBillingService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(
    user_id=10,
    admin_id=5,
    username="alice",
    status="active",
    traffic_used_bytes=0,
    traffic_limit_bytes=10 * 1073741824,  # 10 GB
):
    """Build a real AdminUser row."""
    from app.models.admin_users import AdminUser

    user = AdminUser(
        id=user_id,
        admin_id=admin_id,
        username=username,
        status=status,
        traffic_used_bytes=traffic_used_bytes,
        traffic_limit_bytes=traffic_limit_bytes,
    )
    return user


def _make_service(mock_db):
    """Build TrafficBillingService with mocked WalletService + NotificationRouter."""
    with patch.object(_mod, "WalletService") as MockWallet:
        mock_wallet = MockWallet.return_value
        mock_wallet.debit_wallet.return_value = MagicMock()
        mock_wallet.has_positive_balance.return_value = True
        service = TrafficBillingService(mock_db)
    return service, mock_wallet


def _setup_user_lookup(mock_db, user):
    """Configure mock_db.query to return `user` for AdminUser lookup."""
    mock_db.query.return_value.filter.return_value.first.return_value = user


def _setup_process_traffic_mocks(service, mock_db):
    """Patch internal methods that hit DB queries we don't care about."""
    service._get_price_per_gb = MagicMock(return_value=Decimal("0.02"))
    service._get_admin_telegram_id = MagicMock(return_value=None)
    mock_db.add = MagicMock()
    mock_db.commit = MagicMock()


# ---------------------------------------------------------------------------
# process_traffic_report: end-user traffic alerts
# ---------------------------------------------------------------------------


@patch.object(_mod, "NotificationRouter")
@patch.object(_mod, "get_redis", return_value=None)
def test_process_traffic_report_at_80_pct_notifies_end_user(
    mock_get_redis,
    MockRouter,
):
    """When user crosses 80% of traffic limit, end-user gets Persian alert."""
    # User has used 8.5 of 10 GB = 85%
    user = _make_user(
        traffic_used_bytes=int(8.5 * 1073741824),
        traffic_limit_bytes=10 * 1073741824,
    )
    mock_db = MagicMock()
    _setup_user_lookup(mock_db, user)
    mock_db.refresh = MagicMock(side_effect=lambda x: None)

    service, mock_wallet = _make_service(mock_db)
    _setup_process_traffic_mocks(service, mock_db)
    mock_router_instance = MockRouter.return_value

    # Process 1 byte (user is already at 85% from our setup)
    service.process_traffic_report(
        username="alice",
        protocol="ssh",
        region_code="CH",
        bytes_in=1,
        bytes_out=0,
        instance_ip="1.2.3.4",
    )

    # End-user got an 80% alert via router
    send_calls = mock_router_instance.send_to_end_user.call_args_list
    assert len(send_calls) >= 1
    # First positional arg is user_id
    assert send_calls[0][0][0] == 10
    # Message contains Persian copy (not English STUB)
    msg = send_calls[0][0][1]
    assert "STUB" not in msg
    assert "80" in msg or "هشدار" in msg


@patch.object(_mod, "NotificationRouter")
@patch.object(_mod, "get_redis", return_value=None)
def test_process_traffic_report_at_100_pct_notifies_end_user(
    mock_get_redis,
    MockRouter,
):
    """When user crosses 100% of traffic limit, end-user gets the 100% alert."""
    # User has used 9.99 GB; sending 0.02 GB more pushes them over 100%
    user = _make_user(
        traffic_used_bytes=int(9.99 * 1073741824),
        traffic_limit_bytes=10 * 1073741824,
    )
    mock_db = MagicMock()
    _setup_user_lookup(mock_db, user)
    mock_db.refresh = MagicMock(side_effect=lambda x: None)

    service, mock_wallet = _make_service(mock_db)
    _setup_process_traffic_mocks(service, mock_db)
    mock_router_instance = MockRouter.return_value

    service.process_traffic_report(
        username="alice",
        protocol="ssh",
        region_code="CH",
        bytes_in=int(0.02 * 1073741824),
        bytes_out=0,
        instance_ip="1.2.3.4",
    )

    send_calls = mock_router_instance.send_to_end_user.call_args_list
    assert len(send_calls) >= 1
    msg = send_calls[0][0][1]
    assert "STUB" not in msg
    # 100% template mentions "به پایان رسید" (ended)
    assert "به پایان رسید" in msg or "اشتراک" in msg


@patch.object(_mod, "NotificationRouter")
@patch.object(_mod, "get_redis", return_value=None)
def test_process_traffic_report_under_80_pct_does_not_notify_end_user(
    mock_get_redis,
    MockRouter,
):
    """User at 50% traffic should NOT trigger an alert."""
    user = _make_user(
        traffic_used_bytes=int(5 * 1073741824),  # 50%
        traffic_limit_bytes=10 * 1073741824,
    )
    mock_db = MagicMock()
    _setup_user_lookup(mock_db, user)
    mock_db.refresh = MagicMock(side_effect=lambda x: None)

    service, _ = _make_service(mock_db)
    _setup_process_traffic_mocks(service, mock_db)
    mock_router_instance = MockRouter.return_value

    service.process_traffic_report(
        username="alice",
        protocol="ssh",
        region_code="CH",
        bytes_in=1,
        bytes_out=0,
        instance_ip="1.2.3.4",
    )

    mock_router_instance.send_to_end_user.assert_not_called()


@patch.object(_mod, "NotificationRouter")
@patch.object(_mod, "get_redis", return_value=None)
def test_process_traffic_report_skips_alert_when_no_traffic_limit(
    mock_get_redis,
    MockRouter,
):
    """User with no traffic_limit_bytes (unlimited) -> no alerts."""
    user = _make_user(
        traffic_used_bytes=100,
        traffic_limit_bytes=None,  # unlimited
    )
    mock_db = MagicMock()
    _setup_user_lookup(mock_db, user)
    mock_db.refresh = MagicMock(side_effect=lambda x: None)

    service, _ = _make_service(mock_db)
    _setup_process_traffic_mocks(service, mock_db)
    mock_router_instance = MockRouter.return_value

    service.process_traffic_report(
        username="alice",
        protocol="ssh",
        region_code="CH",
        bytes_in=1000,
        bytes_out=0,
        instance_ip="1.2.3.4",
    )

    mock_router_instance.send_to_end_user.assert_not_called()


@patch.object(_mod, "NotificationRouter")
@patch.object(_mod, "get_redis", return_value=None)
def test_process_traffic_report_continues_if_enduser_notify_fails(
    mock_get_redis,
    MockRouter,
):
    """If NotificationRouter raises, billing still completes (error is logged)."""
    user = _make_user(
        traffic_used_bytes=int(9 * 1073741824),  # 90%
        traffic_limit_bytes=10 * 1073741824,
    )
    mock_db = MagicMock()
    _setup_user_lookup(mock_db, user)
    mock_db.refresh = MagicMock(side_effect=lambda x: None)

    service, _ = _make_service(mock_db)
    _setup_process_traffic_mocks(service, mock_db)
    mock_router_instance = MockRouter.return_value
    mock_router_instance.send_to_end_user.side_effect = RuntimeError("bot offline")

    # Should NOT raise -- billing completes
    result = service.process_traffic_report(
        username="alice",
        protocol="ssh",
        region_code="CH",
        bytes_in=1,
        bytes_out=0,
        instance_ip="1.2.3.4",
    )
    assert result["status"] == "billed"


# ---------------------------------------------------------------------------
# _suspend_admin_users: per-user notification
# ---------------------------------------------------------------------------


@patch.object(_mod, "NotificationRouter")
def test_suspend_admin_users_notifies_each_user(MockRouter):
    """Each suspended user gets a Persian 'service stopped' message."""
    u1 = _make_user(user_id=10, username="alice", status="active")
    u2 = _make_user(user_id=11, username="bob", status="active")
    u3 = _make_user(user_id=12, username="carol", status="active")

    mock_db = MagicMock()
    # The suspend method queries AdminUser and gets back the list [u1, u2, u3]
    mock_db.query.return_value.filter.return_value.all.return_value = [u1, u2, u3]

    service, _ = _make_service(mock_db)
    mock_router_instance = MockRouter.return_value

    service._suspend_admin_users(admin_id=5)

    # All 3 users got suspended
    assert u1.status == "suspended"
    assert u2.status == "suspended"
    assert u3.status == "suspended"

    # 3 notification calls
    assert mock_router_instance.send_to_end_user.call_count == 3
    # Each call's first arg is the user_id
    user_ids_called = [
        call[0][0] for call in mock_router_instance.send_to_end_user.call_args_list
    ]
    assert sorted(user_ids_called) == [10, 11, 12]

    # Messages are Persian (not STUB)
    for call in mock_router_instance.send_to_end_user.call_args_list:
        msg = call[0][1]
        assert "STUB" not in msg
        assert "متوقف" in msg  # "stopped" in Persian


@patch.object(_mod, "NotificationRouter")
def test_suspend_admin_users_continues_if_one_notification_fails(MockRouter):
    """A bot failure for one user doesn't block the others."""
    u1 = _make_user(user_id=10, status="active")
    u2 = _make_user(user_id=11, status="active")

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = [u1, u2]

    service, _ = _make_service(mock_db)
    mock_router_instance = MockRouter.return_value
    # First call fails, second succeeds
    mock_router_instance.send_to_end_user.side_effect = [
        RuntimeError("bot down for u1"),
        True,
    ]

    # Should NOT raise
    service._suspend_admin_users(admin_id=5)

    # Both users still suspended (status change happens before notification)
    assert u1.status == "suspended"
    assert u2.status == "suspended"
    assert mock_router_instance.send_to_end_user.call_count == 2


@patch.object(_mod, "NotificationRouter")
def test_suspend_admin_users_commits_after_status_changes(MockRouter):
    """Verify db.commit is called after status changes."""
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = []

    service, _ = _make_service(mock_db)
    service._suspend_admin_users(admin_id=5)

    mock_db.commit.assert_called()
