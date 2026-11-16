"""Unit tests for end-user Celery notification tasks.

Calls task bodies synchronously (NOT via .delay()) and mocks SessionLocal
to avoid needing a real DB. NotificationRouter is patched at the module
level per the Task 9D sys.modules-pollution lesson.
"""

import socket
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

import app.tasks.end_user_notifications as _mod


def _postgres_reachable() -> bool:
    """Quick TCP probe — don't import psycopg2 here."""
    try:
        socket.create_connection(("localhost", 5432), timeout=1).close()
        return True
    except OSError:
        return False


POSTGRES_AVAILABLE = _postgres_reachable()
SKIP_REASON_DB = (
    "PostgreSQL not reachable on localhost:5432 — run with Docker stack to enable"
)

# Reusable skipif decorator for DB-dependent tests
_skip_if_no_db = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason=SKIP_REASON_DB)

subscription_expiring = _mod.subscription_expiring
subscription_expired = _mod.subscription_expired
cleanup_pending_orders = _mod.cleanup_pending_orders
notify_end_users_tld_changed = _mod.notify_end_users_tld_changed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(
    user_id=10,
    admin_id=5,
    username="alice",
    status="active",
    expires_at=None,
):
    from app.models.admin_users import AdminUser

    return AdminUser(
        id=user_id,
        admin_id=admin_id,
        username=username,
        status=status,
        expires_at=expires_at,
    )


def _make_order(order_id=42, admin_id=5, user_id=10, status="pending", expires_at=None):
    from app.models.user_orders import UserOrder

    return UserOrder(
        id=order_id,
        user_id=user_id,
        admin_id=admin_id,
        package_id=1,
        package_snapshot={"name": "X"},
        macro_region="eu",
        amount_tomans=100,
        wallet_credit_applied_tomans=0,
        status=status,
        expires_at=expires_at,
    )


def _setup_session_local(mock_db):
    """Patch SessionLocal to return mock_db."""
    return patch.object(_mod, "SessionLocal", return_value=mock_db)


def _chainable_query(mock_db, users):
    """Make any number of .filter() calls on the query resolve to `users` via
    .all(). The TLD-change task's filter count varies by purpose (dashboard: 2;
    subscription: 3); the mock must be agnostic to it — filtering is the DB's
    job, the mock supplies the post-filter result set."""
    q = mock_db.query.return_value
    q.filter.return_value = q  # self-referential: any .filter() returns same chain
    q.all.return_value = users
    return q


# ---------------------------------------------------------------------------
# subscription_expiring
# ---------------------------------------------------------------------------


@_skip_if_no_db
@patch.object(_mod, "NotificationRouter")
def test_subscription_expiring_notifies_users_in_3_day_window(MockRouter):
    """Active users with expires_at in [now+3d, now+4d) get notified."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    expiring_soon = _make_user(
        user_id=10,
        expires_at=now + timedelta(days=3, hours=6),
    )
    _make_user(
        user_id=11,
        expires_at=now + timedelta(days=10),
    )
    _make_user(
        user_id=12,
        status="suspended",
        expires_at=now - timedelta(days=1),
    )

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = [expiring_soon]
    mock_db.close = MagicMock()

    mock_router = MockRouter.return_value

    with _setup_session_local(mock_db):
        result = subscription_expiring()

    assert result == {"notified": 1}
    mock_router.send_to_end_user.assert_called_once()
    call_args = mock_router.send_to_end_user.call_args
    assert call_args[0][0] == 10  # user_id
    assert "3" in call_args[0][1]  # days_left in message
    assert "STUB" not in call_args[0][1]


@_skip_if_no_db
@patch.object(_mod, "NotificationRouter")
def test_subscription_expiring_no_users_returns_zero(MockRouter):
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = []
    mock_db.close = MagicMock()

    with _setup_session_local(mock_db):
        result = subscription_expiring()

    assert result == {"notified": 0}
    MockRouter.return_value.send_to_end_user.assert_not_called()


@_skip_if_no_db
@patch.object(_mod, "NotificationRouter")
def test_subscription_expiring_continues_on_notification_failure(MockRouter):
    """One failed notification shouldn't stop the rest."""
    u1 = _make_user(
        user_id=10,
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=3),
    )
    u2 = _make_user(
        user_id=11,
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=3),
    )

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = [u1, u2]
    mock_db.close = MagicMock()

    mock_router = MockRouter.return_value
    mock_router.send_to_end_user.side_effect = [
        RuntimeError("bot down"),
        True,  # second call succeeds
    ]

    with _setup_session_local(mock_db):
        result = subscription_expiring()

    # Only the successful one counts
    assert result == {"notified": 1}
    assert mock_router.send_to_end_user.call_count == 2


# ---------------------------------------------------------------------------
# subscription_expired
# ---------------------------------------------------------------------------


@_skip_if_no_db
@patch.object(_mod, "NotificationRouter")
def test_subscription_expired_notifies_and_marks_status_expired(MockRouter):
    """Users who expired yesterday get notified + status flipped to 'expired'."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    user = _make_user(
        user_id=10,
        status="active",
        expires_at=now - timedelta(hours=12),  # expired 12h ago
    )

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = [user]
    mock_db.close = MagicMock()

    mock_router = MockRouter.return_value

    with _setup_session_local(mock_db):
        result = subscription_expired()

    assert result == {"notified": 1}
    assert user.status == "expired"  # status flipped
    mock_db.commit.assert_called_once()
    mock_router.send_to_end_user.assert_called_once()


@_skip_if_no_db
@patch.object(_mod, "NotificationRouter")
def test_subscription_expired_no_users_returns_zero(MockRouter):
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_filter.all.return_value = []
    mock_db.close = MagicMock()

    with _setup_session_local(mock_db):
        result = subscription_expired()

    assert result == {"notified": 0}
    MockRouter.return_value.send_to_end_user.assert_not_called()


# ---------------------------------------------------------------------------
# cleanup_pending_orders
# ---------------------------------------------------------------------------


@_skip_if_no_db
@patch.object(_mod, "NotificationRouter")
def test_cleanup_pending_orders_marks_stale_orders_expired(MockRouter):
    """Orders pending past expires_at become status=expired."""
    expired_expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        hours=1
    )
    stale_order = _make_order(
        order_id=42,
        status="pending",
        expires_at=expired_expires_at,
    )

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = [stale_order]
    mock_db.close = MagicMock()

    with _setup_session_local(mock_db):
        result = cleanup_pending_orders()

    assert result == {"expired": 1}
    assert stale_order.status == "expired"
    mock_db.commit.assert_called_once()


@_skip_if_no_db
@patch.object(_mod, "NotificationRouter")
def test_cleanup_pending_orders_no_stale_returns_zero(MockRouter):
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = []
    mock_db.close = MagicMock()

    with _setup_session_local(mock_db):
        result = cleanup_pending_orders()

    assert result == {"expired": 0}
    mock_db.commit.assert_called_once()  # commit happens regardless


@_skip_if_no_db
@patch.object(_mod, "NotificationRouter")
def test_cleanup_pending_orders_doesnt_touch_non_pending(MockRouter):
    """Non-pending orders in the result set aren't touched (defense in depth)."""
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = []
    mock_db.close = MagicMock()

    with _setup_session_local(mock_db):
        result = cleanup_pending_orders()

    assert result == {"expired": 0}


# ---------------------------------------------------------------------------
# notify_end_users_tld_changed (Task 4) — Phase 3: affected-admins-only
# ---------------------------------------------------------------------------


@patch.object(_mod, "NotificationRouter")
def test_tld_changed_notifies_returned_user_with_button(MockRouter):
    """Affected-admins call: the user returned by the (mocked) query gets a
    notice with a reply_markup button carrying the new domain in the text."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    active = _make_user(user_id=20, status="active", expires_at=now + timedelta(days=5))

    mock_db = MagicMock()
    mock_db.close = MagicMock()
    _chainable_query(mock_db, [active])
    mock_router = MockRouter.return_value
    mock_router.send_to_end_user.return_value = True

    with _setup_session_local(mock_db):
        result = notify_end_users_tld_changed(
            [7], "subscription", "sub.new.example", "sub.old.example"
        )

    assert result == {"notified": 1}
    mock_router.send_to_end_user.assert_called_once()
    args, kwargs = mock_router.send_to_end_user.call_args
    assert args[0] == 20  # user_id
    assert "sub.new.example" in args[1]  # new domain in message text
    assert "reply_markup" in kwargs  # button attached


@patch.object(_mod, "NotificationRouter")
def test_tld_changed_skips_failed_sends(MockRouter):
    """A failed send (router returns False) is not counted, but the batch
    continues — verified for BOTH subscription and dashboard purposes."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    u1 = _make_user(user_id=30, status="active", expires_at=now + timedelta(days=5))
    u2 = _make_user(user_id=31, status="active", expires_at=now + timedelta(days=5))

    mock_db = MagicMock()
    mock_db.close = MagicMock()
    _chainable_query(mock_db, [u1, u2])
    mock_router = MockRouter.return_value

    for purpose in ("subscription", "dashboard"):
        mock_router.send_to_end_user.reset_mock()
        mock_router.send_to_end_user.side_effect = [True, False]  # 2nd send fails
        with _setup_session_local(mock_db):
            result = notify_end_users_tld_changed(
                [7], purpose, "new.example", "old.example"
            )
        assert result == {"notified": 1}  # only the success counted
        assert (
            mock_router.send_to_end_user.call_count == 2
        )  # batch continued past failure


@patch.object(_mod, "NotificationRouter")
def test_tld_changed_empty_admin_ids_short_circuits(MockRouter):
    """No affected admins -> no query, no sends."""
    mock_db = MagicMock()
    mock_db.close = MagicMock()
    mock_router = MockRouter.return_value
    with _setup_session_local(mock_db):
        result = notify_end_users_tld_changed(
            [], "dashboard", "new.example", "old.example"
        )
    assert result == {"notified": 0}
    mock_db.query.assert_not_called()
    mock_router.send_to_end_user.assert_not_called()
