from decimal import Decimal

from app.models.admin_users import AdminUser
from app.models.admins import Admin
from app.models.admin_packages import AdminPackage
from app.models.admin_user_wallet_txn import AdminUserWalletTxn
from app.services.orders.order_service import OrderService


def _seed(db, balance=Decimal("500000.00")):
    a = Admin(id=1, username="r1", password_hash="x", status="active",
              wallet_balance=Decimal("0.00"))
    db.add(a)
    db.flush()
    pkg = AdminPackage(id=1, admin_id=1, name="Basic",
                       traffic_limit_gb=Decimal("50"), duration_days=30,
                       price_tomans=Decimal("300000"), is_active=True)
    u = AdminUser(id=1, admin_id=1, username="u1", password_hash="x",
                  status="pending", wallet_credit_tomans=balance)
    db.add_all([pkg, u])
    db.commit()
    return u


def test_applying_wallet_credit_writes_spend_row(db_session):
    u = _seed(db_session)
    order = OrderService(db_session).create_order(
        user=u, package_id=1, macro_regions=["eu"],
        wallet_credit_to_apply_tomans=Decimal("300000"),
    )
    rows = db_session.query(AdminUserWalletTxn).filter_by(
        user_id=u.id, type="spend").all()
    assert len(rows) == 1
    assert rows[0].amount_tomans == Decimal("-300000.00")
    assert rows[0].order_id == order.id
    assert u.wallet_credit_tomans == Decimal("200000.00")
