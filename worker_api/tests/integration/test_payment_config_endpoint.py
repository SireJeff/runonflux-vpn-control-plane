import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints import admin_api
from app.core.auth.role_dependencies import require_admin
from app.core.database import get_db
from app.models.platform_settings import PlatformSetting

pytestmark = pytest.mark.database


def _client(db_session, admin_id=1):
    app = FastAPI()
    app.include_router(admin_api.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[require_admin] = lambda: {"id": admin_id, "role": "admin"}
    return TestClient(app)


def test_payment_config_disabled_when_no_address(db_session):
    client = _client(db_session)
    r = client.get("/api/v1/admin/payment-config")
    assert r.status_code == 200
    body = r.json()
    assert body["crypto_enabled"] is False
    assert body["min_topup_usd"] == 10.0
    assert body["toman_per_usd_rate"] == 60000.0


def test_payment_config_enabled_with_address(db_session):
    db_session.add(PlatformSetting(key="crypto_topup_address", value="TWALLET123"))
    db_session.add(PlatformSetting(key="crypto_topup_network", value="USDT (TRC20)"))
    db_session.add(PlatformSetting(key="min_topup_usd", value="25"))
    db_session.add(PlatformSetting(key="toman_per_usd_rate", value="70000"))
    db_session.commit()

    client = _client(db_session)
    body = client.get("/api/v1/admin/payment-config").json()
    assert body["crypto_enabled"] is True
    assert body["crypto_topup_address"] == "TWALLET123"
    assert body["crypto_topup_network"] == "USDT (TRC20)"
    assert body["min_topup_usd"] == 25.0
    assert body["toman_per_usd_rate"] == 70000.0
