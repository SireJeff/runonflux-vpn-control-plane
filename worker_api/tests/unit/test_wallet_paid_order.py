from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.models.admin_users import AdminUser
from app.models.admins import Admin
from app.models.admin_packages import AdminPackage
from app.models.admin_user_wallet_txn import AdminUserWalletTxn
from app.services.orders.order_service import OrderError, OrderService
from app.services.billing.topup_config import effective_min_topup_tomans


def _seed(db, balance):
    a = Admin(id=1, username="r1", password_hash="x", status="active",
              wallet_balance=Decimal("0.00"))
    db.add(a); db.flush()
    pkg = AdminPackage(id=1, admin_id=1, name="Basic",
                       traffic_limit_gb=Decimal("50"), duration_days=30,
                       price_tomans=Decimal("300000"), is_active=True)
    u = AdminUser(id=1, admin_id=1, username="u1", password_hash="x",
                  status="pending", wallet_credit_tomans=balance)
    db.add_all([pkg, u]); db.commit()
    return u


def test_default_min_topup(db_session):
    _seed(db_session, Decimal("0"))
    assert effective_min_topup_tomans(db_session, 1) == Decimal("500000")


def test_wallet_paid_order_activates_and_debits(db_session, monkeypatch):
    import app.services.orders.order_service as mod
    monkeypatch.setattr(mod, "set_user_regions", lambda *a, **k: None)
    monkeypatch.setattr("app.services.regions.availability.healthy_macro_codes",
                        lambda db: ["eu"])
    u = _seed(db_session, Decimal("500000"))
    svc = OrderService(db_session)
    svc.router = MagicMock()
    svc._deliver_connections = MagicMock()  # skip credential/telegram side effects
    order = svc.create_wallet_paid_order(u, package_id=1, macro_regions=["eu"])
    assert order.status == "approved"
    assert order.payment_method == "wallet"
    assert u.status == "active"
    assert u.wallet_credit_tomans == Decimal("200000.00")
    rows = db_session.query(AdminUserWalletTxn).filter_by(type="spend").all()
    assert rows and rows[0].amount_tomans == Decimal("-300000.00")


def test_wallet_paid_order_insufficient_balance(db_session):
    u = _seed(db_session, Decimal("100000"))
    svc = OrderService(db_session)
    svc.router = MagicMock()
    with pytest.raises(OrderError):
        svc.create_wallet_paid_order(u, package_id=1, macro_regions=["eu"])


def test_wallet_paid_order_second_purchase_rejected(db_session, monkeypatch):
    """Balance covers exactly ONE purchase. The first succeeds; the second must
    raise OrderError (insufficient after the first debit) and leave exactly one
    approved order + one 'spend' ledger row + correct final balance.

    This is the sequential-guard proof for the double-tap idempotency fix:
    the second call re-reads the reduced (locked) balance and is rejected
    BEFORE creating any order.
    """
    import app.services.orders.order_service as mod
    from app.models.user_orders import UserOrder

    monkeypatch.setattr(mod, "set_user_regions", lambda *a, **k: None)
    monkeypatch.setattr("app.services.regions.availability.healthy_macro_codes",
                        lambda db: ["eu"])
    # Package price is 300000; fund exactly one purchase.
    u = _seed(db_session, Decimal("300000"))
    svc = OrderService(db_session)
    svc.router = MagicMock()
    svc._deliver_connections = MagicMock()

    order1 = svc.create_wallet_paid_order(u, package_id=1, macro_regions=["eu"])
    assert order1.status == "approved"

    with pytest.raises(OrderError):
        svc.create_wallet_paid_order(u, package_id=1, macro_regions=["eu"])

    # Exactly one approved order.
    approved = db_session.query(UserOrder).filter_by(status="approved").all()
    assert len(approved) == 1
    # Exactly one spend ledger row.
    spends = db_session.query(AdminUserWalletTxn).filter_by(type="spend").all()
    assert len(spends) == 1
    assert spends[0].amount_tomans == Decimal("-300000.00")
    # Balance fully consumed, not double-debited into the negative.
    db_session.refresh(u)
    assert u.wallet_credit_tomans == Decimal("0.00")
