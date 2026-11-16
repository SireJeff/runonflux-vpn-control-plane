"""Integration tests for /admin/routing-rules endpoints (Task 5).

Follows the importlib single-module load convention shared by the sibling
reseller admin API suites (test_free_config_api.py, test_admin_packages_api.py,
test_referral_api.py) to avoid the heavy app.main import (which pulls optional
telegram/cloudflare SDKs not present in the test env).

Unlike those suites' MagicMock DB, these tests bind the router to the REAL
`fluxvpn_test` Postgres db_session so FK enforcement (admin_routing_configs ->
admins) and per-reseller isolation are exercised for real. Auth is fully real:
each client carries a genuine role="admin" JWT for its own provisioned Admin
row, and RoleChecker(["admin"]) resolves that token against the same db_session.
Two real Admin rows make the reseller-isolation assertion genuine (per-request,
not a shared global), which a class-level auth patch could not guarantee.

Run from worker_api/:  pytest tests/integration/test_routing_rules_api.py -v
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# The endpoint transitively imports app.services.credentials, which pulls in the
# fdm cloudflare_client and its optional `cloudflare` SDK (not installed in the
# test env). Stub the package + the submodules it imports so the module loads.
for _name in ("cloudflare", "cloudflare.types", "cloudflare.types.dns"):
    sys.modules.setdefault(_name, MagicMock())

from app.core.auth.jwt import create_access_token
from app.core.database import get_db
from app.models.admins import Admin

# ---------------------------------------------------------------------------
# Load the routing_rules_api module directly (avoid heavy app.main import)
# ---------------------------------------------------------------------------
_MOD_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "app"
    / "api"
    / "v1"
    / "endpoints"
    / "routing_rules_api.py"
)
_spec = importlib.util.spec_from_file_location(
    "app.api.v1.endpoints.routing_rules_api",
    str(_MOD_PATH),
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["app.api.v1.endpoints.routing_rules_api"] = _mod
_spec.loader.exec_module(_mod)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_admin(db, username: str) -> Admin:
    admin = Admin(username=username, password_hash="x", status="active")
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


def _build_client(db_session, admin: Admin) -> TestClient:
    """Mount only the routing-rules router, bound to the real db_session, and
    carry a genuine role="admin" JWT for `admin`. Real RoleChecker resolves it."""
    app = FastAPI()
    app.include_router(_mod.router, prefix="/api/v1")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    token = create_access_token({"sub": str(admin.id), "role": "admin"})
    client = TestClient(app)
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


@pytest.fixture
def admin_a(db_session):
    return _make_admin(db_session, "reseller_a")


@pytest.fixture
def admin_b(db_session):
    return _make_admin(db_session, "reseller_b")


@pytest.fixture
def admin_client(db_session, admin_a):
    return _build_client(db_session, admin_a)


@pytest.fixture
def other_admin_client(db_session, admin_b):
    return _build_client(db_session, admin_b)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_get_returns_disabled_default(admin_client):
    r = admin_client.get("/api/v1/admin/routing-rules")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_enabled"] is False
    assert body["ban_domains"] == [] and body["allow_domains"] == [] and body["presets"] == {}


def test_put_then_get_roundtrip(admin_client):
    payload = {
        "is_enabled": True,
        "ban_domains": ["Ads.com "],
        "allow_domains": ["bank.ir"],
        "presets": {"iran_direct": True},
    }
    r = admin_client.put("/api/v1/admin/routing-rules", json=payload)
    assert r.status_code == 200, r.text
    assert r.json()["ban_domains"] == ["ads.com"]  # normalized
    r2 = admin_client.get("/api/v1/admin/routing-rules")
    assert r2.json()["is_enabled"] is True
    assert r2.json()["presets"] == {"iran_direct": True}


def test_put_rejects_bad_domain(admin_client):
    r = admin_client.put(
        "/api/v1/admin/routing-rules",
        json={
            "is_enabled": True,
            "ban_domains": ["http://x"],
            "allow_domains": [],
            "presets": {},
        },
    )
    assert r.status_code == 422, r.text


def test_put_rejects_unknown_preset(admin_client):
    r = admin_client.put(
        "/api/v1/admin/routing-rules",
        json={
            "is_enabled": True,
            "ban_domains": [],
            "allow_domains": [],
            "presets": {"nope": True},
        },
    )
    assert r.status_code == 422, r.text


def test_reseller_isolation(admin_client, other_admin_client):
    admin_client.put(
        "/api/v1/admin/routing-rules",
        json={
            "is_enabled": True,
            "ban_domains": ["a.com"],
            "allow_domains": [],
            "presets": {},
        },
    )
    r = other_admin_client.get("/api/v1/admin/routing-rules")
    assert r.json()["ban_domains"] == []  # B does not see A's rules
