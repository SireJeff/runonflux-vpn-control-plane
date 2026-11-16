from decimal import Decimal

import pytest

from app.models.admins import Admin
from app.services.billing.wire_order_service import WireOrderService

pytestmark = pytest.mark.database


def _admin(db, admin_id=1):
    a = Admin(
        id=admin_id,
        username=f"r{admin_id}",
        password_hash="x",
        status="active",
        wallet_balance=Decimal("0.00"),
    )
    db.add(a)
    db.commit()
    return a


def test_create_crypto_order_snapshots_usd_and_txid(db_session):
    _admin(db_session)
    order = WireOrderService(db_session).create_order(
        admin_id=1,
        amount_tomans=Decimal("3000000"),
        contact_telegram="@a",
        payment_method="crypto",
        amount_usd=Decimal("50.00"),
        crypto_txid="0xabc",
        crypto_link="https://x/0xabc",
        usd_rate_snapshot=Decimal("60000"),
    )
    assert order.payment_method == "crypto"
    assert order.amount_usd == Decimal("50.00")
    assert order.crypto_txid == "0xabc"
    assert order.usd_rate_snapshot == Decimal("60000")
    assert order.status == "pending"


def test_create_wire_order_unchanged(db_session):
    _admin(db_session, admin_id=2)
    order = WireOrderService(db_session).create_order(
        admin_id=2,
        amount_tomans=Decimal("500000"),
        contact_telegram="@b",
    )
    assert order.payment_method == "wire"
    assert order.amount_usd is None
    assert order.crypto_txid is None
