from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints import admin_api
from app.core.auth.role_dependencies import require_admin
from app.core.database import get_db
from app.models.admins import Admin
from app.models.platform_settings import PlatformSetting
from app.models.wire_orders import WireOrder

pytestmark = pytest.mark.database


def _client(db, admin_id=1):
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
    app = FastAPI()
    app.include_router(admin_api.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_admin] = lambda: {"id": admin_id, "role": "admin"}
    return TestClient(app)


def test_crypto_topup_rejected_when_not_enabled(db_session):
    client = _client(db_session)
    r = client.post(
        "/api/v1/admin/wallet/wire-order",
        json={
            "payment_method": "crypto",
            "amount_usd": 50,
            "crypto_txid": "0xabc",
            "contact_telegram": "@a",
        },
    )
    assert r.status_code == 422
    assert "not enabled" in r.json()["detail"].lower()


def test_crypto_topup_below_min_rejected(db_session):
    db_session.add(PlatformSetting(key="crypto_topup_address", value="TWALLET"))
    db_session.add(PlatformSetting(key="min_topup_usd", value="25"))
    db_session.commit()
    client = _client(db_session)
    r = client.post(
        "/api/v1/admin/wallet/wire-order",
        json={
            "payment_method": "crypto",
            "amount_usd": 10,
            "crypto_txid": "0xabc",
            "contact_telegram": "@a",
        },
    )
    assert r.status_code == 422
    assert "minimum" in r.json()["detail"].lower()


def test_crypto_topup_snapshots_usd_and_tomans(db_session):
    db_session.add(PlatformSetting(key="crypto_topup_address", value="TWALLET"))
    db_session.add(PlatformSetting(key="min_topup_usd", value="10"))
    db_session.add(PlatformSetting(key="toman_per_usd_rate", value="60000"))
    db_session.commit()
    client = _client(db_session)
    r = client.post(
        "/api/v1/admin/wallet/wire-order",
        json={
            "payment_method": "crypto",
            "amount_usd": 50,
            "crypto_txid": "0xabc",
            "crypto_link": "https://x/0xabc",
            "contact_telegram": "@a",
        },
    )
    assert r.status_code == 201
    order = db_session.query(WireOrder).order_by(WireOrder.id.desc()).first()
    assert order.payment_method == "crypto"
    assert order.amount_usd == Decimal("50.00")
    assert order.amount_tomans == Decimal("3000000")  # 50 * 60000
    assert order.usd_rate_snapshot == Decimal("60000")
    assert order.status == "pending"


def test_wire_topup_still_works(db_session):
    client = _client(db_session)
    r = client.post(
        "/api/v1/admin/wallet/wire-order",
        json={
            "amount_tomans": 500000,
            "contact_telegram": "@a",
        },
    )
    assert r.status_code == 201
    order = db_session.query(WireOrder).order_by(WireOrder.id.desc()).first()
    assert order.payment_method == "wire"


def test_wire_topup_below_min_rejected(db_session):
    db_session.add(PlatformSetting(key="min_topup_tomans", value="500000"))
    db_session.commit()
    client = _client(db_session)
    r = client.post(
        "/api/v1/admin/wallet/wire-order",
        json={
            "amount_tomans": 499999,
            "contact_telegram": "@a",
        },
    )
    assert r.status_code == 422
    assert "minimum" in r.json()["detail"].lower()
