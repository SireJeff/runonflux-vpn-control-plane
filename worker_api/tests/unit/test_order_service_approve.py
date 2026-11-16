"""Unit tests for OrderService.approve_order + referral + delivery (Task 9D).

CredentialService.generate_user_credentials and ConnectionStringService are
mocked because they're tested independently and have their own DB queries
that would make the mock setup explosive.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.services.orders import order_service as _mod
from app.services.orders.order_service import OrderError, OrderService


@pytest.fixture(autouse=True)
def _stub_deliver_connections_dependencies():
    """T12: _deliver_connections now calls module-level helpers (set_password,
    get_subscription_base_url, get_dashboard_base_url, country_flag,
    get_country_name). Patch each of them so tests don't need real crypto,
    real URL lookups, or real country data — and so the existing mock_db
    side_effect lists (sized for the old _deliver_connections that made zero
    DB calls) stay valid.

    ConnectionStringService is patched separately by each test's own
    @patch.object decorator; tests that exercise _deliver_connections should
    also stub ``MockConnService.return_value.generate_country_breakdown``
    to a real dict (empty is fine).
    """
    with patch.object(_mod, "set_password"), patch.object(
        _mod, "get_subscription_base_url", return_value="https://sub.test"
    ), patch.object(
        _mod, "get_dashboard_base_url", return_value="https://dash.test"
    ), patch.object(
        _mod, "country_flag", return_value="🌐"
    ), patch.object(
        _mod, "get_country_name", side_effect=lambda c: c
    ):
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(
    user_id=10,
    admin_id=5,
    status="pending",
    wallet_credit_tomans=Decimal("0"),
    referred_by_user_id=None,
    traffic_limit_bytes=None,
    traffic_used_bytes=0,
    expires_at=None,
    region=None,
    current_order=None,
    username=None,
    referral_code=None,
):
    from app.models.admin_users import AdminUser

    user = AdminUser(
        id=user_id,
        admin_id=admin_id,
        status=status,
        wallet_credit_tomans=wallet_credit_tomans,
        referred_by_user_id=referred_by_user_id,
        traffic_limit_bytes=traffic_limit_bytes,
        traffic_used_bytes=traffic_used_bytes,
        expires_at=expires_at,
        username=username or f"user{user_id}",
        referral_code=referral_code,
    )
    user.region = region  # relationship attribute
    user.current_order = current_order
    return user


def _make_pending_order(
    order_id=42,
    admin_id=5,
    user_id=10,
    amount_tomans=Decimal("100000.00"),
    wallet_credit_applied_tomans=Decimal("0"),
    snapshot=None,
):
    from app.models.user_orders import UserOrder

    return UserOrder(
        id=order_id,
        user_id=user_id,
        admin_id=admin_id,
        package_id=1,
        package_snapshot=snapshot
        or {
            "name": "Basic",
            "traffic_gb": 20.0,
            "duration_days": 30,
            "price_tomans": 100000.0,
        },
        macro_region="eu",
        amount_tomans=amount_tomans,
        wallet_credit_applied_tomans=wallet_credit_applied_tomans,
        status="pending",
    )


def _make_service_with_approve_mocks(
    first_results,
    region_result=None,
    creds_count=0,
    referral_config=None,
    referrer=None,
):
    """Build OrderService with all external services mocked.

    first_results: list returned in sequence by .first() calls.
      [order, user, region?, referral_config?, referrer?]
    The test specifies only what's needed; we provide sane defaults.
    """
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.side_effect = first_results
    mock_db.query.return_value.filter_by.return_value.count.return_value = creds_count
    mock_db.refresh = MagicMock(side_effect=lambda x: None)

    service = OrderService(mock_db)
    service.router = MagicMock()
    return service, mock_db


# ---------------------------------------------------------------------------
# approve_order state machine
# ---------------------------------------------------------------------------


@patch.object(_mod, "ConnectionStringService")
@patch.object(_mod, "CredentialService")
def test_approve_order_success_activates_user_and_marks_approved(
    MockCredService,
    MockConnService,
):
    """Happy path: order approved, user activated, status flipped."""
    user = _make_user(user_id=10, status="pending")
    order = _make_pending_order()
    service, mock_db = _make_service_with_approve_mocks(
        first_results=[order, user, None],  # order, user, no existing region
        creds_count=0,  # first purchase, generate creds
    )

    result = service.approve_order(order_id=42, reviewer_admin_id=5)

    # User activated
    assert user.status == "active"
    assert user.traffic_limit_bytes == int(20.0 * 1024**3)
    assert user.traffic_used_bytes == 0
    assert user.expires_at is not None

    # Order approved
    assert result.status == "approved"
    assert result.reviewer_admin_id == 5
    assert result.reviewed_at is not None

    # Credentials generated (first purchase)
    MockCredService.return_value.generate_user_credentials.assert_called_once_with(user)

    # T12: _deliver_connections now uses generate_country_breakdown (not
    # generate_all_region_connections) to build the v2 hero country grid.
    MockConnService.return_value.generate_country_breakdown.assert_called_once()
    # First positional arg is the user; second is the macro region.
    call_args = MockConnService.return_value.generate_country_breakdown.call_args
    assert call_args[0][0] is user

    # End-user notified
    service.router.send_to_end_user.assert_called_once()
    notify_args = service.router.send_to_end_user.call_args
    assert notify_args[0][0] == 10  # user_id positional


@patch.object(_mod, "ConnectionStringService")
@patch.object(_mod, "CredentialService")
def test_approve_order_skips_credential_generation_when_already_has_creds(
    MockCredService,
    MockConnService,
):
    """If user already has UserCredentialV2 rows, don't regenerate."""
    user = _make_user()
    order = _make_pending_order()
    service, mock_db = _make_service_with_approve_mocks(
        first_results=[order, user, None],
        creds_count=6,  # already has all creds
    )

    service.approve_order(order_id=42, reviewer_admin_id=5)

    MockCredService.return_value.generate_user_credentials.assert_not_called()


def test_approve_order_already_approved_raises():
    _make_user()
    order = _make_pending_order()
    order.status = "approved"
    service, _ = _make_service_with_approve_mocks(first_results=[order])

    with pytest.raises(OrderError, match="not pending"):
        service.approve_order(order_id=42, reviewer_admin_id=5)


def test_approve_order_not_found_raises():
    service, _ = _make_service_with_approve_mocks(first_results=[None])

    with pytest.raises(OrderError, match="Order not found"):
        service.approve_order(order_id=999, reviewer_admin_id=5)


@patch.object(_mod, "ConnectionStringService")
@patch.object(_mod, "CredentialService")
def test_approve_order_user_not_found_raises(MockCredService, MockConnService):
    order = _make_pending_order()
    service, _ = _make_service_with_approve_mocks(
        first_results=[order, None],  # user not found
    )

    with pytest.raises(OrderError, match="User not found"):
        service.approve_order(order_id=42, reviewer_admin_id=5)


# ---------------------------------------------------------------------------
# approve_order referral awarding
# ---------------------------------------------------------------------------


@patch.object(_mod, "ConnectionStringService")
@patch.object(_mod, "CredentialService")
def test_approve_order_awards_referral_when_enabled(
    MockCredService,
    MockConnService,
):
    """If user was referred and config enabled, referrer gets reward."""
    referrer = _make_user(
        user_id=99,
        wallet_credit_tomans=Decimal("0"),
    )
    user = _make_user(user_id=10, referred_by_user_id=99)
    order = _make_pending_order(amount_tomans=Decimal("100000.00"))

    config_mock = MagicMock()
    config_mock.reward_percentage = Decimal("10")  # 10% commission

    # T-geo-axis: set_user_regions now reconciles existing UserRegion rows via
    # a bulk `.all()` query (region-set reconciliation), not a single `.first()`
    # lookup -- so the only remaining `.first()` calls after order/user are the
    # referral config lookup then the referrer lookup.
    service, mock_db = _make_service_with_approve_mocks(
        first_results=[order, user, config_mock, referrer],
        creds_count=0,
    )
    # record_wallet_txn re-fetches the credited user under a row lock (C1);
    # return the referrer instance for that ledger lock query.
    mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = (
        referrer
    )

    service.approve_order(order_id=42, reviewer_admin_id=5)

    # Referrer got 10% of 100000 = 10000
    assert referrer.wallet_credit_tomans == Decimal("10000.00")

    # AdminReferralEarning was added
    mock_db.add.assert_called()  # at least region + earning added

    # Referrer notified (1 call for referral reward + 1 for activation delivery = 2)
    assert service.router.send_to_end_user.call_count == 2
    # First call was referral to referrer (user_id=99)
    first_call = service.router.send_to_end_user.call_args_list[0]
    assert first_call[0][0] == 99


@patch.object(_mod, "ConnectionStringService")
@patch.object(_mod, "CredentialService")
def test_approve_order_referral_rewards_on_full_price_when_wallet_paid(
    MockCredService,
    MockConnService,
):
    """Reward is computed on the full package price (cash + wallet-applied),
    so a fully wallet-paid order (amount_tomans=0) still credits the referrer."""
    referrer = _make_user(user_id=99, wallet_credit_tomans=Decimal("0"))
    user = _make_user(user_id=10, referred_by_user_id=99)
    # Full package price 100000 paid entirely from wallet: cash=0, applied=100000.
    order = _make_pending_order(
        amount_tomans=Decimal("0.00"),
        wallet_credit_applied_tomans=Decimal("100000.00"),
    )

    config_mock = MagicMock()
    config_mock.reward_percentage = Decimal("10")  # 10% commission

    service, mock_db = _make_service_with_approve_mocks(
        first_results=[order, user, config_mock, referrer],
        creds_count=0,
    )
    mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = (
        referrer
    )

    service.approve_order(order_id=42, reviewer_admin_id=5)

    # 10% of the full 100000 price = 10000, even though cash charged was 0.
    assert referrer.wallet_credit_tomans == Decimal("10000.00")
    first_call = service.router.send_to_end_user.call_args_list[0]
    assert first_call[0][0] == 99


@patch.object(_mod, "ConnectionStringService")
@patch.object(_mod, "CredentialService")
def test_approve_order_skips_referral_when_user_not_referred(
    MockCredService,
    MockConnService,
):
    """No referred_by_user_id -> no referral lookup, no award."""
    user = _make_user(referred_by_user_id=None)
    order = _make_pending_order()

    service, mock_db = _make_service_with_approve_mocks(
        first_results=[order, user],
    )

    service.approve_order(order_id=42, reviewer_admin_id=5)

    # Only 2 .first() calls (order, user) -- region reconciliation now uses a
    # bulk `.all()` query (set_user_regions), and no referral queries happen
    # since the user was never referred.
    assert mock_db.query.return_value.filter.return_value.first.call_count == 2


@patch.object(_mod, "ConnectionStringService")
@patch.object(_mod, "CredentialService")
def test_approve_order_skips_referral_when_config_disabled(
    MockCredService,
    MockConnService,
):
    """User was referred but admin disabled referral -> no award."""
    user = _make_user(referred_by_user_id=99)
    order = _make_pending_order()

    service, _ = _make_service_with_approve_mocks(
        first_results=[order, user, None, None],  # config not found (disabled)
    )

    service.approve_order(order_id=42, reviewer_admin_id=5)

    # Only 1 send (the activation), no referral reward
    service.router.send_to_end_user.assert_called_once()


# ---------------------------------------------------------------------------
# approve_order referral code assignment
# ---------------------------------------------------------------------------


@patch.object(_mod, "ConnectionStringService")
@patch.object(_mod, "CredentialService")
def test_approve_order_assigns_referral_code_if_missing(
    MockCredService,
    MockConnService,
):
    """First-time approval assigns user.referral_code in USERNAME-XXXX format."""
    user = _make_user(user_id=10, username="alice")
    user.referral_code = None
    order = _make_pending_order()
    service, _ = _make_service_with_approve_mocks(
        first_results=[order, user, None],
        creds_count=0,
    )

    service.approve_order(order_id=42, reviewer_admin_id=5)

    assert user.referral_code is not None
    assert user.referral_code.startswith("ALICE-")
    # token_hex(2) = 4 hex chars
    suffix = user.referral_code.split("-", 1)[1]
    assert len(suffix) == 4


@patch.object(_mod, "ConnectionStringService")
@patch.object(_mod, "CredentialService")
def test_approve_order_preserves_existing_referral_code(
    MockCredService,
    MockConnService,
):
    """If user already has a referral_code, don't overwrite it."""
    user = _make_user(user_id=10, username="bob")
    user.referral_code = "EXISTING-CODE"
    order = _make_pending_order()
    service, _ = _make_service_with_approve_mocks(
        first_results=[order, user, None],
        creds_count=0,
    )

    service.approve_order(order_id=42, reviewer_admin_id=5)

    assert user.referral_code == "EXISTING-CODE"  # unchanged
