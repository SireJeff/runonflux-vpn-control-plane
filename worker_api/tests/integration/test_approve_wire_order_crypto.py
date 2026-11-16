from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints import super_admin
from app.core.auth.role_dependencies import require_super_admin
from app.core.database import get_db
from app.models.admins import Admin
from app.models.wire_orders import WireOrder

pytestmark = pytest.mark.database


def _client(db, sa_id=99):
    db.add(
        Admin(
            id=sa_id,
            username="sa",
            password_hash="x",
            status="active",
            wallet_balance=Decimal("0.00"),
        )
    )
    db.commit()
    app = FastAPI()
    app.include_router(super_admin.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_super_admin] = lambda: {
        "id": sa_id,
        "role": "super_admin",
    }
    return TestClient(app)


def _reseller(db, admin_id=1):
    db.add(
        Admin(
            id=admin_id,
            username="r1",
            password_hash="x",
            status="active",
            wallet_balance=Decimal("0.00"),
        )
    )
    db.commit()


def test_approve_crypto_credits_snapshotted_usd(db_session):
    _reseller(db_session)
    client = _client(db_session)
    order = WireOrder(
        admin_id=1,
        amount_tomans=Decimal("3000000"),
        amount_usd=Decimal("50.00"),
        contact_telegram="@a",
        status="pending",
        payment_method="crypto",
        crypto_txid="0xabc",
        usd_rate_snapshot=Decimal("60000"),
    )
    db_session.add(order)
    db_session.commit()

    # No exchange_rate needed for crypto
    r = client.post(f"/api/v1/super/orders/{order.id}/approve", json={})
    assert r.status_code == 200
    reseller = db_session.query(Admin).filter(Admin.id == 1).first()
    assert reseller.wallet_balance == Decimal("50.00")
    db_session.refresh(order)
    assert order.status == "approved"
    assert order.amount_usd == Decimal("50.00")


def test_approve_wire_still_requires_rate(db_session):
    _reseller(db_session, admin_id=2)
    client = _client(db_session, sa_id=98)
    order = WireOrder(
        admin_id=2,
        amount_tomans=Decimal("600000"),
        contact_telegram="@b",
        status="pending",
        payment_method="wire",
    )
    db_session.add(order)
    db_session.commit()
    r = client.post(f"/api/v1/super/orders/{order.id}/approve", json={})
    assert r.status_code == 422  # exchange_rate required for wire
