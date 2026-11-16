from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch


def test_charges_each_expired_nonprimary_region():
    from app.services.billing.region_billing_service import RegionBillingService

    now = datetime(2026, 7, 21, 12, 0, 0)
    r1 = MagicMock(
        user_id=1,
        macro_region="as",
        is_primary=False,
        status="active",
        region_expires_at=now - timedelta(days=1),
    )
    r2 = MagicMock(
        user_id=1,
        macro_region="na",
        is_primary=False,
        status="active",
        region_expires_at=now - timedelta(days=1),
    )
    db = MagicMock()
    # region query -> .all() = [r1, r2]; user query -> .first() = active user
    db.query.return_value.filter.return_value.all.return_value = [r1, r2]
    user = MagicMock(id=1, admin_id=9, status="active", username="u")
    db.query.return_value.filter.return_value.first.return_value = user

    svc = RegionBillingService(db)
    svc._get_region_price = MagicMock(return_value=Decimal("2.00"))
    svc.wallet_service = MagicMock()
    svc.wallet_service.debit_wallet.return_value = MagicMock()  # truthy = success

    # Freeze the service's clock so the +30d write is deterministic. Only the
    # `datetime` symbol is patched; `timedelta`/`timezone` remain the real ones.
    with patch("app.services.billing.region_billing_service.datetime") as mock_dt:
        mock_dt.now.return_value = (
            now  # datetime.now(timezone.utc).replace(tzinfo=None) -> now
        )
        result = svc.charge_monthly_regions()

    assert svc.wallet_service.debit_wallet.call_count == 2  # one per non-primary region
    assert result["charged"] == 2
    assert r1.region_expires_at == now + timedelta(days=30)


def test_suspends_region_on_insufficient_balance():
    from app.services.billing.region_billing_service import RegionBillingService

    now = datetime(2026, 7, 21, 12, 0, 0)
    r1 = MagicMock(
        user_id=1,
        macro_region="as",
        is_primary=False,
        status="active",
        region_expires_at=now - timedelta(days=1),
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [r1]
    user = MagicMock(id=1, admin_id=9, status="active", username="u")
    db.query.return_value.filter.return_value.first.return_value = user

    svc = RegionBillingService(db)
    svc._get_region_price = MagicMock(return_value=Decimal("2.00"))
    svc.wallet_service = MagicMock()
    svc.wallet_service.debit_wallet.return_value = None  # insufficient balance

    result = svc.charge_monthly_regions()

    assert result["suspended"] == 1
    assert r1.status == "suspended"
