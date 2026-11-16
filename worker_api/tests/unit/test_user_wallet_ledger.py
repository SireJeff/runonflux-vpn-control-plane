from decimal import Decimal

import pytest

from app.models.admin_users import AdminUser
from app.models.admins import Admin
from app.models.admin_user_wallet_txn import AdminUserWalletTxn
from app.services.billing.user_wallet_ledger import record_wallet_txn


def _seed(db):
    a = Admin(username="r1", password_hash="x", status="active",
              wallet_balance=Decimal("0.00"))
    db.add(a)
    db.flush()
    u = AdminUser(admin_id=a.id, username="u1", password_hash="x",
                  status="active", wallet_credit_tomans=Decimal("0.00"))
    db.add(u)
    db.flush()
    return u


def test_credit_updates_balance_and_writes_row(db_session):
    u = _seed(db_session)
    txn = record_wallet_txn(db_session, u, Decimal("100000.00"), "topup")
    db_session.commit()
    assert u.wallet_credit_tomans == Decimal("100000.00")
    assert txn.balance_after == Decimal("100000.00")
    assert txn.amount_tomans == Decimal("100000.00")
    rows = db_session.query(AdminUserWalletTxn).filter_by(user_id=u.id).all()
    assert len(rows) == 1


def test_debit_reduces_balance(db_session):
    u = _seed(db_session)
    record_wallet_txn(db_session, u, Decimal("100000.00"), "topup")
    record_wallet_txn(db_session, u, Decimal("-30000.00"), "spend")
    db_session.commit()
    assert u.wallet_credit_tomans == Decimal("70000.00")


def test_overdraw_raises(db_session):
    u = _seed(db_session)
    with pytest.raises(ValueError):
        record_wallet_txn(db_session, u, Decimal("-5000.00"), "spend")
