"""Unit tests for OrderService.create_order and reject_order (Task 9B).

approve_order, _maybe_award_referral, _deliver_connections tested in Task 9D.
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.services.orders.order_service import OrderError, OrderService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(
    user_id=10,
    admin_id=5,
    wallet_credit_tomans=Decimal("0"),
    current_order_id=None,
):
    from app.models.admin_users import AdminUser

    return AdminUser(
        id=user_id,
        admin_id=admin_id,
        wallet_credit_tomans=wallet_credit_tomans,
        current_order_id=current_order_id,
    )


def _make_package(
    pkg_id=1,
    admin_id=5,
    name="Basic",
    traffic_limit_gb=Decimal("20.00"),
    duration_days=30,
    price_tomans=Decimal("100000.00"),
    is_active=True,
    display_order=0,
):
    from app.models.admin_packages import AdminPackage

    return AdminPackage(
        id=pkg_id,
        admin_id=admin_id,
        name=name,
        traffic_limit_gb=traffic_limit_gb,
        duration_days=duration_days,
        price_tomans=price_tomans,
        is_active=is_active,
        display_order=display_order,
    )


def _make_pending_order(
    order_id=42,
    admin_id=5,
    user_id=10,
    applied=Decimal("0"),
    status="pending",
):
    from app.models.user_orders import UserOrder

    return UserOrder(
        id=order_id,
        user_id=user_id,
        admin_id=admin_id,
        package_id=1,
        package_snapshot={"name": "Basic"},
        macro_region="eu",
        amount_tomans=Decimal("100000.00"),
        wallet_credit_applied_tomans=applied,
        status=status,
    )


def _make_mock_db(first_result=None):
    """Mock SQLAlchemy session. first_result sets what .first() returns by default."""
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = first_result

    counter = {"id": 100}

    def fake_refresh(obj):
        if obj.id is None:
            obj.id = counter["id"]
            counter["id"] += 1

    mock_db.refresh = MagicMock(side_effect=fake_refresh)
    return mock_db


def _make_service(mock_db):
    """Build OrderService with mocked router (don't hit Telegram)."""
    service = OrderService(mock_db)
    service.router = MagicMock()
    return service


# ---------------------------------------------------------------------------
# create_order tests
# ---------------------------------------------------------------------------


def test_create_order_success_no_wallet_credit():
    user = _make_user(wallet_credit_tomans=Decimal("0"))
    pkg = _make_package()
    mock_db = _make_mock_db(first_result=pkg)

    service = _make_service(mock_db)

    order = service.create_order(
        user=user,
        package_id=1,
        macro_region="eu",
        wallet_credit_to_apply_tomans=Decimal("0"),
    )

    assert order.id == 100
    assert order.user_id == 10
    assert order.admin_id == 5
    assert order.status == "pending"
    assert order.amount_tomans == Decimal("100000.00")
    assert order.wallet_credit_applied_tomans == Decimal("0")
    assert order.package_snapshot == {
        "name": "Basic",
        "traffic_gb": 20.0,
        "duration_days": 30,
        "price_tomans": 100000.0,
    }
    assert order.macro_region == "eu"
    assert order.expires_at is not None

    mock_db.add.assert_called_once()
    assert mock_db.commit.call_count == 2  # initial + current_order_id update


def test_create_order_caps_credit_at_user_balance():
    """If requested credit > user balance, only balance is applied."""
    user = _make_user(wallet_credit_tomans=Decimal("30000"))
    pkg = _make_package(price_tomans=Decimal("100000.00"))
    mock_db = _make_mock_db(first_result=pkg)
    # record_wallet_txn re-fetches the user under a row lock (C1); return the
    # same user instance for that ledger lock query after the package lookup.
    mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = (
        user
    )

    service = _make_service(mock_db)

    order = service.create_order(
        user=user,
        package_id=1,
        macro_region="eu",
        wallet_credit_to_apply_tomans=Decimal("50000"),
    )

    assert order.wallet_credit_applied_tomans == Decimal("30000")
    assert order.amount_tomans == Decimal("70000.00")
    assert user.wallet_credit_tomans == Decimal("0")


def test_create_order_invalid_package_raises():
    user = _make_user()
    mock_db = _make_mock_db(first_result=None)

    service = _make_service(mock_db)

    with pytest.raises(OrderError, match="Package not found"):
        service.create_order(user=user, package_id=999, macro_region="eu")


def test_create_order_invalid_macro_region_raises():
    user = _make_user()
    pkg = _make_package()
    mock_db = _make_mock_db(first_result=pkg)

    service = _make_service(mock_db)

    with pytest.raises(OrderError, match="Invalid macro_region"):
        service.create_order(
            user=user,
            package_id=1,
            macro_region="xx_invalid",
        )


def test_create_order_sets_current_order_id():
    user = _make_user(current_order_id=None)
    pkg = _make_package()
    mock_db = _make_mock_db(first_result=pkg)

    service = _make_service(mock_db)
    service.create_order(user=user, package_id=1, macro_region="eu")

    assert user.current_order_id == 100


def test_create_order_debits_user_wallet():
    user = _make_user(wallet_credit_tomans=Decimal("50000"))
    pkg = _make_package()
    mock_db = _make_mock_db(first_result=pkg)
    # record_wallet_txn re-fetches the user under a row lock (C1).
    mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = (
        user
    )

    service = _make_service(mock_db)
    service.create_order(
        user=user,
        package_id=1,
        macro_region="eu",
        wallet_credit_to_apply_tomans=Decimal("20000"),
    )

    assert user.wallet_credit_tomans == Decimal("30000")


def test_create_order_snapshot_captures_package_at_order_time():
    """Snapshot fields must come from pkg at create-time, not via FK later."""
    user = _make_user()
    pkg = _make_package(
        name="Premium",
        traffic_limit_gb=Decimal("100.00"),
        duration_days=90,
        price_tomans=Decimal("500000.00"),
    )
    mock_db = _make_mock_db(first_result=pkg)

    service = _make_service(mock_db)
    order = service.create_order(user=user, package_id=1, macro_region="eu")

    assert order.package_snapshot == {
        "name": "Premium",
        "traffic_gb": 100.0,
        "duration_days": 90,
        "price_tomans": 500000.0,
    }


# ---------------------------------------------------------------------------
# reject_order tests
# ---------------------------------------------------------------------------


def test_reject_order_success_refunds_credit_and_notifies():
    user = _make_user(user_id=10, wallet_credit_tomans=Decimal("0"))
    order = _make_pending_order(applied=Decimal("30000"))

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.side_effect = [
        order,
        user,
    ]
    # record_wallet_txn re-fetches the user under a row lock (C1).
    mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = (
        user
    )
    mock_db.refresh = MagicMock(side_effect=lambda x: None)

    service = _make_service(mock_db)

    result = service.reject_order(
        order_id=42,
        reviewer_admin_id=5,
        reason="bad receipt",
    )

    assert result.status == "rejected"
    assert result.reviewer_admin_id == 5
    assert result.reviewed_at is not None
    assert result.rejection_reason == "bad receipt"
    assert user.wallet_credit_tomans == Decimal("30000")  # refunded

    service.router.send_to_end_user.assert_called_once()
    call_args = service.router.send_to_end_user.call_args
    assert call_args[0][0] == 10  # positional arg 0: user_id


def test_reject_order_already_approved_raises():
    order = _make_pending_order(status="approved")
    mock_db = _make_mock_db(first_result=order)

    service = _make_service(mock_db)

    with pytest.raises(OrderError, match="not pending"):
        service.reject_order(order_id=42, reviewer_admin_id=5)


def test_reject_order_not_found_raises():
    mock_db = _make_mock_db(first_result=None)

    service = _make_service(mock_db)

    with pytest.raises(OrderError, match="Order not found"):
        service.reject_order(order_id=999, reviewer_admin_id=5)


def test_reject_order_no_refund_when_zero_applied():
    """If wallet_credit_applied_tomans=0, no refund happens."""
    user = _make_user(wallet_credit_tomans=Decimal("5000"))
    order = _make_pending_order(applied=Decimal("0"))

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.side_effect = [
        order,
        user,
    ]
    mock_db.refresh = MagicMock(side_effect=lambda x: None)

    service = _make_service(mock_db)
    service.reject_order(order_id=42, reviewer_admin_id=5)

    assert user.wallet_credit_tomans == Decimal("5000")  # unchanged


def test_reject_order_cross_admin_returns_not_found():
    """Admin A querying admin B's order gets None -> OrderError."""
    mock_db = _make_mock_db(first_result=None)

    service = _make_service(mock_db)

    with pytest.raises(OrderError, match="Order not found"):
        service.reject_order(order_id=42, reviewer_admin_id=99)
