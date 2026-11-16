from decimal import Decimal

from app.models.admin_free_config import AdminFreeConfig
from app.models.admin_user_wallet_txn import AdminUserWalletTxn
from app.models.admin_users import AdminUser
from app.models.admins import Admin
from app.models.user_orders import UserOrder


def _admin(db):
    a = Admin(username="r1", password_hash="x", status="active",
              wallet_balance=Decimal("0.00"))
    db.add(a)
    db.flush()
    return a


def test_wallet_txn_persists_with_ledger_fields(db_session):
    a = _admin(db_session)
    u = AdminUser(admin_id=a.id, username="u1", password_hash="x", status="active")
    db_session.add(u)
    db_session.flush()

    txn = AdminUserWalletTxn(
        user_id=u.id, admin_id=a.id, amount_tomans=Decimal("100000.00"),
        type="topup", order_id=None, balance_after=Decimal("100000.00"),
    )
    db_session.add(txn)
    db_session.commit()
    db_session.refresh(txn)
    assert txn.id is not None
    assert txn.type == "topup"
    assert txn.balance_after == Decimal("100000.00")


def test_free_config_defaults(db_session):
    a = _admin(db_session)
    fc = AdminFreeConfig(admin_id=a.id)
    db_session.add(fc)
    db_session.commit()
    db_session.refresh(fc)
    assert fc.is_enabled is False
    assert fc.kind == "shared"


def test_user_order_kind_defaults_to_subscription(db_session):
    a = _admin(db_session)
    u = AdminUser(admin_id=a.id, username="u2", password_hash="x", status="active")
    db_session.add(u)
    db_session.flush()
    o = UserOrder(
        user_id=u.id, admin_id=a.id, amount_tomans=Decimal("0.00"),
        status="pending",
    )
    db_session.add(o)
    db_session.commit()
    db_session.refresh(o)
    assert o.kind == "subscription"
    assert o.macro_region is None  # now nullable for topups
    assert o.package_snapshot is None
