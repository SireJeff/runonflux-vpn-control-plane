from decimal import Decimal
from unittest.mock import MagicMock

from app.models.admin_users import AdminUser
from app.models.admins import Admin
from app.models.admin_user_wallet_txn import AdminUserWalletTxn
from app.services.orders.order_service import OrderService


def _seed(db):
    a = Admin(id=1, username="r1", password_hash="x", status="active",
              wallet_balance=Decimal("0.00"))
    db.add(a); db.flush()
    u = AdminUser(id=1, admin_id=1, username="u1", password_hash="x",
                  status="active", wallet_credit_tomans=Decimal("0.00"))
    db.add(u); db.commit()
    return u


def test_create_topup_order_pending(db_session):
    u = _seed(db_session)
    svc = OrderService(db_session)
    svc.router = MagicMock()
    order = svc.create_topup_order(
        user=u, amount_tomans=Decimal("200000"),
        receipt_file_id="rf1", receipt_file_unique_id="rfu1",
    )
    assert order.kind == "topup"
    assert order.status == "pending"
    assert order.package_id is None
    assert order.macro_region is None
    assert order.amount_tomans == Decimal("200000")


def test_approve_topup_credits_wallet(db_session):
    u = _seed(db_session)
    svc = OrderService(db_session)
    svc.router = MagicMock()
    order = svc.create_topup_order(user=u, amount_tomans=Decimal("200000"),
                                   receipt_file_id="rf1")
    svc.approve_order(order.id, reviewer_admin_id=1)
    db_session.refresh(u)
    assert u.wallet_credit_tomans == Decimal("200000.00")
    rows = db_session.query(AdminUserWalletTxn).filter_by(
        user_id=u.id, type="topup").all()
    assert len(rows) == 1 and rows[0].order_id == order.id
    svc.router.send_to_end_user.assert_called()
