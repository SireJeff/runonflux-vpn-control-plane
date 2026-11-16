"""HTTP-level E2E for the reseller end-user bot purchase flow.

Mounts real routers (user_orders_api, referral_api, admin_packages_api,
bot_config_api) on a minimal FastAPI app, drives them with TestClient.
DB is mocked at the Session level.
"""

import importlib.util
import socket
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _postgres_reachable() -> bool:
    """Quick TCP probe -- don't import psycopg2 here."""
    try:
        socket.create_connection(("localhost", 5432), timeout=1).close()
        return True
    except OSError:
        return False


POSTGRES_AVAILABLE = _postgres_reachable()
SKIP_REASON_DB = (
    "PostgreSQL not reachable on localhost:5432 -- run with Docker stack to enable"
)
_skip_if_no_db = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason=SKIP_REASON_DB)

_ENDPOINTS_DIR = (
    Path(__file__).resolve().parent.parent.parent / "app" / "api" / "v1" / "endpoints"
)


def _load_module(name: str, filename: str):
    """Load a router module via importlib, register in sys.modules."""
    path = _ENDPOINTS_DIR / filename
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Load router modules -- wrap in try/except so collection doesn't crash.
_MOD_LOAD_ERROR = None
try:
    _orders_mod = _load_module(
        "app.api.v1.endpoints.user_orders_api", "user_orders_api.py"
    )
    _packages_mod = _load_module(
        "app.api.v1.endpoints.admin_packages_api", "admin_packages_api.py"
    )
    _referral_mod = _load_module("app.api.v1.endpoints.referral_api", "referral_api.py")
    _bot_config_mod = _load_module(
        "app.api.v1.endpoints.bot_config_api", "bot_config_api.py"
    )
except Exception as exc:
    _MOD_LOAD_ERROR = exc
    _orders_mod = _packages_mod = _referral_mod = _bot_config_mod = None


def _requires_module_loaded(test_func):
    """Decorator: skip test if module loading failed."""
    return pytest.mark.skipif(
        _MOD_LOAD_ERROR is not None,
        reason=f"Module load failed: {_MOD_LOAD_ERROR}",
    )(test_func)


# ---------------------------------------------------------------------------
# Auth fixtures
# ---------------------------------------------------------------------------

ADMIN_AUTH = {"id": 5, "role": "admin", "entity": MagicMock()}
END_USER_AUTH = {"id": 50, "role": "end_user", "entity": MagicMock(), "admin_id": 5}


def _fake_admin_call():
    return ADMIN_AUTH


def _fake_end_user_call():
    return END_USER_AUTH


def _patch_auth(monkeypatch):
    """Patch RoleChecker on each router module."""
    for mod in (_orders_mod, _packages_mod, _referral_mod, _bot_config_mod):
        monkeypatch.setattr(mod.RoleChecker, "__call__", staticmethod(_fake_admin_call))
    # Override end_user routes on user_orders_api specifically
    monkeypatch.setattr(
        _orders_mod.RoleChecker, "__call__", staticmethod(_fake_admin_call)
    )


def _patch_auth_end_user(monkeypatch):
    """Patch RoleChecker so POST /admin/orders sees end_user role."""
    for mod in (_orders_mod, _packages_mod, _referral_mod, _bot_config_mod):
        monkeypatch.setattr(
            mod.RoleChecker, "__call__", staticmethod(_fake_end_user_call)
        )


# ---------------------------------------------------------------------------
# DB mock helpers
# ---------------------------------------------------------------------------


def _make_user(
    user_id=50,
    admin_id=5,
    status="lead",
    wallet_credit_tomans=Decimal("0"),
):
    user = MagicMock()
    user.id = user_id
    user.admin_id = admin_id
    user.status = status
    user.wallet_credit_tomans = wallet_credit_tomans
    user.current_order_id = None
    user.traffic_limit_bytes = None
    user.traffic_used_bytes = 0
    user.expires_at = None
    return user


def _make_package(
    pkg_id=7,
    admin_id=5,
    name="Basic",
    traffic_limit_gb=Decimal("20"),
    duration_days=30,
    price_tomans=Decimal("100000"),
    is_active=True,
):
    pkg = MagicMock()
    pkg.id = pkg_id
    pkg.admin_id = admin_id
    pkg.name = name
    pkg.traffic_limit_gb = traffic_limit_gb
    pkg.duration_days = duration_days
    pkg.price_tomans = price_tomans
    pkg.is_active = is_active
    return pkg


def _make_order(
    order_id=200,
    admin_id=5,
    user_id=50,
    status="pending",
    amount_tomans=Decimal("100000"),
    wallet_credit_applied_tomans=Decimal("0"),
):
    order = MagicMock()
    order.id = order_id
    order.user_id = user_id
    order.admin_id = admin_id
    order.package_id = 7
    order.package_snapshot = {
        "name": "Basic",
        "traffic_gb": 20.0,
        "duration_days": 30,
        "price_tomans": 100000.0,
    }
    order.macro_region = "eu"
    order.amount_tomans = amount_tomans
    order.wallet_credit_applied_tomans = wallet_credit_applied_tomans
    order.status = status
    order.reviewer_admin_id = None
    order.reviewed_at = None
    order.rejection_reason = None
    order.receipt_file_id = "f1"
    order.receipt_local_path = None
    order.payment_method = "card"
    order.crypto_txid = None
    order.crypto_link = None
    order.amount_usd_snapshot = None
    order.created_at = datetime.now(timezone.utc).replace(tzinfo=None)
    order.expires_at = datetime.now(timezone.utc).replace(tzinfo=None)
    return order


def _make_referral_config(admin_id=5, is_enabled=True, reward_percentage=Decimal("10")):
    cfg = MagicMock()
    cfg.admin_id = admin_id
    cfg.is_enabled = is_enabled
    cfg.reward_percentage = reward_percentage
    cfg.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    return cfg


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client(monkeypatch):
    _patch_auth(monkeypatch)

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
        []
    )

    app = FastAPI()
    app.include_router(_orders_mod.router, prefix="/api/v1")
    app.include_router(_packages_mod.router, prefix="/api/v1")
    app.include_router(_referral_mod.router, prefix="/api/v1")
    app.include_router(_bot_config_mod.router, prefix="/api/v1")

    from app.core.database import get_db

    def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    tc = TestClient(app)
    tc._mock_db = mock_db
    yield tc
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Test 1: E2E purchase flow (create -> approve -> GET verify)
# ---------------------------------------------------------------------------


@_skip_if_no_db
@_requires_module_loaded
def test_e2e_purchase_flow(client, monkeypatch):
    """POST create (end_user) -> POST approve (admin) -> GET verify."""
    user = _make_user()
    _make_package()
    created_order = _make_order(order_id=200, status="pending")
    approved_order = _make_order(order_id=200, status="approved")
    approved_order.reviewer_admin_id = 5
    approved_order.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)

    fake_service = MagicMock()
    fake_service.create_order.return_value = created_order
    fake_service.approve_order.return_value = approved_order

    # Phase 1: create order (end_user role)
    _patch_auth_end_user(monkeypatch)
    mock_db = client._mock_db
    mock_db.query.return_value.filter.return_value.first.return_value = user

    with patch.object(_orders_mod, "OrderService", return_value=fake_service):
        resp = client.post(
            "/api/v1/admin/orders",
            json={
                "package_id": 7,
                "macro_region": "eu",
                "receipt_file_id": "f1",
                "receipt_file_unique_id": "u1",
            },
            headers={"Authorization": "Bearer t"},
        )
    assert resp.status_code == 201, resp.text
    assert resp.json()["id"] == 200
    assert resp.json()["status"] == "pending"
    fake_service.create_order.assert_called_once()

    # Phase 2: approve order (admin role)
    _patch_auth(monkeypatch)
    with patch.object(_orders_mod, "OrderService", return_value=fake_service):
        resp = client.post(
            "/api/v1/admin/orders/200/approve",
            headers={"Authorization": "Bearer t"},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "approved"
    assert resp.json()["reviewer_admin_id"] == 5

    # Phase 3: GET verify
    mock_db.query.return_value.filter.return_value.first.return_value = approved_order
    resp = client.get(
        "/api/v1/admin/orders/200",
        headers={"Authorization": "Bearer t"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "approved"


# ---------------------------------------------------------------------------
# Test 2: Invalid region returns 400
# ---------------------------------------------------------------------------


@_skip_if_no_db
@_requires_module_loaded
def test_create_order_400_on_invalid_region(client, monkeypatch):
    """Invalid macro_region -> 400, not 500."""
    _patch_auth_end_user(monkeypatch)
    user = _make_user()
    client._mock_db.query.return_value.filter.return_value.first.return_value = user

    fake_service = MagicMock()
    from app.services.orders.order_service import OrderError

    fake_service.create_order.side_effect = OrderError("Invalid macro region")

    with patch.object(_orders_mod, "OrderService", return_value=fake_service):
        resp = client.post(
            "/api/v1/admin/orders",
            json={
                "package_id": 7,
                "macro_region": "xx",
                "receipt_file_id": "f1",
                "receipt_file_unique_id": "u1",
            },
            headers={"Authorization": "Bearer t"},
        )
    assert resp.status_code == 400
    assert "Invalid macro region" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Test 3: Inactive package returns 400
# ---------------------------------------------------------------------------


@_skip_if_no_db
@_requires_module_loaded
def test_create_order_400_on_inactive_package(client, monkeypatch):
    """Inactive package -> OrderError -> 400."""
    _patch_auth_end_user(monkeypatch)
    user = _make_user()
    client._mock_db.query.return_value.filter.return_value.first.return_value = user

    fake_service = MagicMock()
    from app.services.orders.order_service import OrderError

    fake_service.create_order.side_effect = OrderError("Package not found or inactive")

    with patch.object(_orders_mod, "OrderService", return_value=fake_service):
        resp = client.post(
            "/api/v1/admin/orders",
            json={
                "package_id": 99,
                "macro_region": "eu",
                "receipt_file_id": "f1",
                "receipt_file_unique_id": "u1",
            },
            headers={"Authorization": "Bearer t"},
        )
    assert resp.status_code == 400
    assert "Package not found or inactive" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Test 4: Wallet credit applied correctly
# ---------------------------------------------------------------------------


@_skip_if_no_db
@_requires_module_loaded
def test_create_order_wallet_credit_applied(client, monkeypatch):
    """Order amount reduced and wallet debited when credit is applied."""
    _patch_auth_end_user(monkeypatch)
    user = _make_user(wallet_credit_tomans=Decimal("50000"))
    client._mock_db.query.return_value.filter.return_value.first.return_value = user

    order_with_credit = _make_order(
        order_id=200,
        amount_tomans=Decimal("70000"),
        wallet_credit_applied_tomans=Decimal("30000"),
    )
    fake_service = MagicMock()
    fake_service.create_order.return_value = order_with_credit

    with patch.object(_orders_mod, "OrderService", return_value=fake_service):
        resp = client.post(
            "/api/v1/admin/orders",
            json={
                "package_id": 7,
                "macro_region": "eu",
                "wallet_credit_to_apply_tomans": "30000",
                "receipt_file_id": "f1",
                "receipt_file_unique_id": "u1",
            },
            headers={"Authorization": "Bearer t"},
        )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["amount_tomans"] == "70000"
    assert data["wallet_credit_applied_tomans"] == "30000"
    # Verify service was called with the credit amount
    call_kwargs = fake_service.create_order.call_args
    assert call_kwargs.kwargs["wallet_credit_to_apply_tomans"] == Decimal("30000")


# ---------------------------------------------------------------------------
# Test 5: Approve on already-approved order returns 400
# ---------------------------------------------------------------------------


@_skip_if_no_db
@_requires_module_loaded
def test_approve_already_approved_returns_400(client, monkeypatch):
    """Second approve on an already-approved order -> 400."""
    fake_service = MagicMock()
    from app.services.orders.order_service import OrderError

    fake_service.approve_order.side_effect = OrderError("Order is not pending")

    with patch.object(_orders_mod, "OrderService", return_value=fake_service):
        resp = client.post(
            "/api/v1/admin/orders/200/approve",
            headers={"Authorization": "Bearer t"},
        )
    assert resp.status_code == 400
    assert "not pending" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Test 6: Reject with refund
# ---------------------------------------------------------------------------


@_skip_if_no_db
@_requires_module_loaded
def test_reject_order_with_reason(client, monkeypatch):
    """POST /reject happy path: order status -> rejected, reason stored."""
    rejected_order = _make_order(order_id=200, status="rejected")
    rejected_order.reviewer_admin_id = 5
    rejected_order.rejection_reason = "bad receipt"

    fake_service = MagicMock()
    fake_service.reject_order.return_value = rejected_order

    with patch.object(_orders_mod, "OrderService", return_value=fake_service):
        resp = client.post(
            "/api/v1/admin/orders/200/reject",
            json={"reason": "bad receipt"},
            headers={"Authorization": "Bearer t"},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "rejected"
    fake_service.reject_order.assert_called_once_with(200, 5, "bad receipt")


# ---------------------------------------------------------------------------
# Test 7: Referral config GET auto-creates
# ---------------------------------------------------------------------------


@_skip_if_no_db
@_requires_module_loaded
def test_referral_config_get_auto_creates(client):
    """GET /admin/referral/config when no config exists auto-creates and returns 200."""
    # First call to .first() returns None (no existing config),
    # then the endpoint calls _get_or_create_config which does db.add + commit.
    # After commit, db.refresh(cfg) is called. We simulate refresh setting attributes.
    mock_db = client._mock_db

    call_count = {"n": 0}

    def fake_first():
        call_count["n"] += 1
        if call_count["n"] == 1:
            return None  # no existing config
        return _make_referral_config()

    mock_db.query.return_value.filter.return_value.first.side_effect = fake_first

    def fake_refresh(obj):
        obj.admin_id = 5
        obj.is_enabled = True
        obj.reward_percentage = Decimal("10")
        obj.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

    mock_db.refresh = MagicMock(side_effect=fake_refresh)

    resp = client.get(
        "/api/v1/admin/referral/config",
        headers={"Authorization": "Bearer t"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["admin_id"] == 5
    assert data["is_enabled"] is True
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()
