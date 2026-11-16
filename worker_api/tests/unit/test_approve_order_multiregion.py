from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch


def test_approve_order_provisions_full_region_set_additively():
    from app.services.orders.order_service import OrderService

    now = datetime(2026, 7, 21, 12, 0, 0)
    user = MagicMock(id=7, expires_at=now + timedelta(days=10), admin_id=3)
    order = MagicMock(
        id=1,
        status="pending",
        user_id=7,
        reviewer_admin_id=None,
        macro_region="eu",
        macro_regions=["eu", "as"],
        package_snapshot={"duration_days": 30, "traffic_gb": 100, "name": "P"},
    )
    db = MagicMock()
    svc = OrderService(db)

    with patch(
        "app.services.orders.order_service.set_user_regions"
    ) as set_regions, patch(
        "app.services.orders.order_service.compute_new_expiry",
        return_value=now + timedelta(days=40),
    ) as cne, patch(
        "app.services.orders.order_service.CredentialService"
    ), patch.object(
        OrderService, "_maybe_award_referral"
    ), patch.object(
        OrderService, "_deliver_connections"
    ):
        # Wire the query chain to return order then user, matching the real code's order of queries:
        # approve_order does self.db.query(UserOrder).filter(...).first() -> order,
        # then self.db.query(AdminUser).filter(...).first() -> user.
        # The UserRegion query has been removed in favor of set_user_regions (patched below),
        # and the credential-count check uses .filter_by(...).count(), a separate mock chain,
        # so exactly these two .filter().first() calls occur.
        db.query.return_value.filter.return_value.first.side_effect = [order, user]
        svc.approve_order(order_id=1, reviewer_admin_id=3)

    set_regions.assert_called_once()
    args, kwargs = set_regions.call_args
    passed_regions = (
        kwargs.get("macro_regions") if "macro_regions" in kwargs else args[2]
    )
    assert passed_regions == ["eu", "as"]
    cne.assert_called_once()
    assert user.expires_at == now + timedelta(days=40)


def test_approve_order_drops_currently_unhealthy_regions():
    """F3: a region that went unhealthy while the order was pending is dropped;
    only the healthy subset is provisioned (with a floor tested separately)."""
    from app.services.orders.order_service import OrderService

    now = datetime(2026, 7, 21, 12, 0, 0)
    user = MagicMock(id=7, expires_at=now + timedelta(days=10), admin_id=3)
    order = MagicMock(
        id=1,
        status="pending",
        user_id=7,
        reviewer_admin_id=None,
        macro_region="eu",
        macro_regions=["eu", "as"],
        package_snapshot={"duration_days": 30, "traffic_gb": 100, "name": "P"},
    )
    db = MagicMock()
    svc = OrderService(db)

    with patch(
        "app.services.orders.order_service.set_user_regions"
    ) as set_regions, patch(
        "app.services.regions.availability.healthy_macro_codes", return_value={"eu"}
    ), patch(
        "app.services.orders.order_service.compute_new_expiry",
        return_value=now + timedelta(days=40),
    ), patch(
        "app.services.orders.order_service.CredentialService"
    ), patch.object(
        OrderService, "_maybe_award_referral"
    ), patch.object(
        OrderService, "_deliver_connections"
    ):
        db.query.return_value.filter.return_value.first.side_effect = [order, user]
        svc.approve_order(order_id=1, reviewer_admin_id=3)

    set_regions.assert_called_once()
    args, kwargs = set_regions.call_args
    passed_regions = (
        kwargs.get("macro_regions") if "macro_regions" in kwargs else args[2]
    )
    assert passed_regions == ["eu"]  # "as" was unhealthy -> dropped


def test_approve_order_floor_provisions_original_when_all_unhealthy():
    """F3 floor: if EVERY requested region is unhealthy, provision the original
    set anyway rather than stranding a paid order with zero regions."""
    from app.services.orders.order_service import OrderService

    now = datetime(2026, 7, 21, 12, 0, 0)
    user = MagicMock(id=7, expires_at=now + timedelta(days=10), admin_id=3)
    order = MagicMock(
        id=1,
        status="pending",
        user_id=7,
        reviewer_admin_id=None,
        macro_region="eu",
        macro_regions=["eu", "as"],
        package_snapshot={"duration_days": 30, "traffic_gb": 100, "name": "P"},
    )
    db = MagicMock()
    svc = OrderService(db)

    with patch(
        "app.services.orders.order_service.set_user_regions"
    ) as set_regions, patch(
        "app.services.regions.availability.healthy_macro_codes", return_value=set()
    ), patch(
        "app.services.orders.order_service.compute_new_expiry",
        return_value=now + timedelta(days=40),
    ), patch(
        "app.services.orders.order_service.CredentialService"
    ), patch.object(
        OrderService, "_maybe_award_referral"
    ), patch.object(
        OrderService, "_deliver_connections"
    ):
        db.query.return_value.filter.return_value.first.side_effect = [order, user]
        svc.approve_order(order_id=1, reviewer_admin_id=3)

    set_regions.assert_called_once()
    args, kwargs = set_regions.call_args
    passed_regions = (
        kwargs.get("macro_regions") if "macro_regions" in kwargs else args[2]
    )
    assert passed_regions == ["eu", "as"]  # floor: original set preserved
