"""Integration tests for /admin/orders GET + POST endpoints.

Uses the importlib-loading pattern (see test_bot_config_api.py for reference).
GET endpoints from Task 9A, POST endpoints from Task 9D.
"""

import importlib.util
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Load the user_orders_api module directly
# ---------------------------------------------------------------------------
_MOD_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "app"
    / "api"
    / "v1"
    / "endpoints"
    / "user_orders_api.py"
)
_spec = importlib.util.spec_from_file_location(
    "app.api.v1.endpoints.user_orders_api",
    str(_MOD_PATH),
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["app.api.v1.endpoints.user_orders_api"] = _mod
_spec.loader.exec_module(_mod)

# Bind OrderError at collection time so it matches the endpoint's class.
# Importing inside test functions breaks when other test files replace
# sys.modules["app.services.orders.order_service"] via their own importlib loads.
OrderError = _mod.OrderError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ADMIN_AUTH = {"id": 5, "role": "admin", "entity": MagicMock()}


def _fake_admin_call():
    return ADMIN_AUTH


def _patch_admin_auth(monkeypatch):
    monkeypatch.setattr(
        _mod.RoleChecker,
        "__call__",
        staticmethod(_fake_admin_call),
    )


def _make_order_mock(
    order_id=42,
    admin_id=5,
    status="pending",
    receipt_local_path=None,
    user_id=10,
):
    """Build a MagicMock that quacks like a UserOrder ORM row."""
    order = MagicMock()
    order.id = order_id
    order.user_id = user_id
    order.admin_id = admin_id
    order.package_id = 1
    order.package_snapshot = {
        "name": "Basic",
        "traffic_gb": 20.0,
        "duration_days": 30,
        "price_tomans": 100000.0,
    }
    order.macro_region = "eu"
    order.amount_tomans = Decimal("100000.00")
    order.wallet_credit_applied_tomans = Decimal("0")
    order.status = status
    order.reviewer_admin_id = None
    order.reviewed_at = None
    order.rejection_reason = None
    order.receipt_file_id = "file_id_123"
    order.receipt_local_path = receipt_local_path
    order.payment_method = "card"
    order.crypto_txid = None
    order.crypto_link = None
    order.amount_usd_snapshot = None
    order.created_at = datetime.now(timezone.utc).replace(tzinfo=None)
    order.expires_at = datetime.now(timezone.utc).replace(tzinfo=None)
    return order


@pytest.fixture
def client(monkeypatch):
    _patch_admin_auth(monkeypatch)

    mock_db = MagicMock()
    # Default: empty list
    mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
        []
    )
    # Default: single-row lookup returns None
    mock_db.query.return_value.filter.return_value.first.return_value = None

    _app = FastAPI()
    _app.include_router(_mod.router, prefix="/api/v1")

    from app.core.database import get_db

    def override_get_db():
        yield mock_db

    _app.dependency_overrides[get_db] = override_get_db
    _test_client = TestClient(_app)
    _test_client._mock_db = mock_db
    yield _test_client
    _app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Tests for GET /admin/orders (list)
# ---------------------------------------------------------------------------


def test_list_orders_default_returns_admin_orders_only(client):
    """GET returns only the current admin's orders, newest first."""
    order1 = _make_order_mock(order_id=1, admin_id=5)
    order2 = _make_order_mock(order_id=2, admin_id=5)
    client._mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
        order2,
        order1,
    ]

    response = client.get(
        "/api/v1/admin/orders",
        headers={"Authorization": "Bearer t"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["id"] == 2  # newest first


def test_list_orders_with_status_filter(client):
    """GET ?status=pending passes filter through to query."""
    client._mock_db.query.return_value.filter.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
        []
    )

    response = client.get(
        "/api/v1/admin/orders?status=pending",
        headers={"Authorization": "Bearer t"},
    )
    assert response.status_code == 200
    assert response.json() == []


def test_list_orders_empty(client):
    response = client.get(
        "/api/v1/admin/orders",
        headers={"Authorization": "Bearer t"},
    )
    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# Tests for GET /admin/orders/{id}
# ---------------------------------------------------------------------------


def test_get_order_returns_order_when_found(client):
    order = _make_order_mock(order_id=42, admin_id=5)
    client._mock_db.query.return_value.filter.return_value.first.return_value = order

    response = client.get(
        "/api/v1/admin/orders/42",
        headers={"Authorization": "Bearer t"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["id"] == 42


def test_get_order_returns_404_when_not_found(client):
    # Default mock returns None
    response = client.get(
        "/api/v1/admin/orders/9999",
        headers={"Authorization": "Bearer t"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Order not found"


# ---------------------------------------------------------------------------
# Tests for GET /admin/orders/{id}/receipt
# ---------------------------------------------------------------------------


def test_get_receipt_returns_image_when_file_exists(client, tmp_path):
    """Receipt served as image/jpeg when local path is set and file exists."""
    # Create a fake receipt file
    fake_jpg = tmp_path / "42.jpg"
    fake_jpg.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg-data")

    order = _make_order_mock(order_id=42, admin_id=5, receipt_local_path=str(fake_jpg))
    client._mock_db.query.return_value.filter.return_value.first.return_value = order

    response = client.get(
        "/api/v1/admin/orders/42/receipt",
        headers={"Authorization": "Bearer t"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content.startswith(b"\xff\xd8")  # JPEG SOI marker


def test_get_receipt_returns_404_when_no_path(client):
    """Receipt 404 if order has no receipt_local_path (user hasn't uploaded)."""
    order = _make_order_mock(order_id=42, admin_id=5, receipt_local_path=None)
    client._mock_db.query.return_value.filter.return_value.first.return_value = order

    response = client.get(
        "/api/v1/admin/orders/42/receipt",
        headers={"Authorization": "Bearer t"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Receipt not available"


def test_get_receipt_returns_404_when_order_not_found(client):
    response = client.get(
        "/api/v1/admin/orders/9999/receipt",
        headers={"Authorization": "Bearer t"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Order not found"


def test_get_receipt_returns_410_when_file_missing_from_disk(client):
    """Receipt 410 Gone if path is set but file was deleted."""
    order = _make_order_mock(
        order_id=42,
        admin_id=5,
        receipt_local_path="/data/receipts/deleted.jpg",
    )
    client._mock_db.query.return_value.filter.return_value.first.return_value = order

    response = client.get(
        "/api/v1/admin/orders/42/receipt",
        headers={"Authorization": "Bearer t"},
    )
    assert response.status_code == 410
    assert response.json()["detail"] == "Receipt file missing"


# ---------------------------------------------------------------------------
# POST /admin/orders/{id}/approve + reject (Task 9D)
# ---------------------------------------------------------------------------


def test_approve_endpoint_returns_200_on_success(client, monkeypatch):
    """POST /approve happy path: OrderService.approve_order succeeds."""
    fake_order = _make_order_mock(order_id=42, admin_id=5, status="approved")

    fake_service = MagicMock()
    fake_service.approve_order.return_value = fake_order

    with patch.object(_mod, "OrderService", return_value=fake_service):
        response = client.post(
            "/api/v1/admin/orders/42/approve",
            headers={"Authorization": "Bearer t"},
        )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "approved"
    fake_service.approve_order.assert_called_once_with(42, 5)


def test_approve_endpoint_returns_400_on_order_error(client, monkeypatch):
    """POST /approve when OrderService raises OrderError -> 400."""
    fake_service = MagicMock()
    fake_service.approve_order.side_effect = OrderError(
        "Order is approved, not pending"
    )

    with patch.object(_mod, "OrderService", return_value=fake_service):
        response = client.post(
            "/api/v1/admin/orders/42/approve",
            headers={"Authorization": "Bearer t"},
        )

    assert response.status_code == 400
    assert "not pending" in response.json()["detail"]


def test_reject_endpoint_returns_200_on_success(client, monkeypatch):
    """POST /reject happy path."""
    fake_order = _make_order_mock(order_id=42, admin_id=5, status="rejected")

    fake_service = MagicMock()
    fake_service.reject_order.return_value = fake_order

    with patch.object(_mod, "OrderService", return_value=fake_service):
        response = client.post(
            "/api/v1/admin/orders/42/reject",
            json={"reason": "bad receipt"},
            headers={"Authorization": "Bearer t"},
        )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "rejected"
    fake_service.reject_order.assert_called_once_with(42, 5, "bad receipt")


def test_reject_endpoint_returns_400_on_order_error(client, monkeypatch):
    """POST /reject when OrderService raises OrderError -> 400."""
    fake_service = MagicMock()
    fake_service.reject_order.side_effect = OrderError("Order not found")

    with patch.object(_mod, "OrderService", return_value=fake_service):
        response = client.post(
            "/api/v1/admin/orders/999/reject",
            headers={"Authorization": "Bearer t"},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Order not found"


# ---------------------------------------------------------------------------
# POST /admin/orders/{id}/retry-receipt (Task 3)
# ---------------------------------------------------------------------------


def test_retry_receipt_happy_path(client, monkeypatch):
    """POST /retry-receipt succeeds: downloads, persists, returns order."""
    order = _make_order_mock(order_id=42, admin_id=5, receipt_local_path=None)
    order.receipt_file_id = "file_abc"

    mock_bot = MagicMock()
    mock_bot.bot_token_enc = b"encrypted_token_blob"

    client._mock_db.query.return_value.filter.return_value.first.side_effect = [
        order,
        mock_bot,
    ]

    fake_dl = AsyncMock(return_value="/data/receipts/42.jpg")
    mock_dec_token = MagicMock(return_value="DECRYPTED_TOKEN")

    with patch.object(_mod, "download_and_store", fake_dl):
        with patch(
            "app.api.v1.endpoints.user_orders_api.decrypt_token", mock_dec_token
        ):
            response = client.post(
                "/api/v1/admin/orders/42/retry-receipt",
                headers={"Authorization": "Bearer t"},
            )

    assert response.status_code == 200, response.text
    assert response.json()["id"] == 42
    fake_dl.assert_awaited_once_with("DECRYPTED_TOKEN", "file_abc", 42)


def test_retry_receipt_404_on_unknown_order(client):
    """POST /retry-receipt returns 404 when order not found."""
    client._mock_db.query.return_value.filter.return_value.first.return_value = None

    response = client.post(
        "/api/v1/admin/orders/9999/retry-receipt",
        headers={"Authorization": "Bearer t"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Order not found"


def test_retry_receipt_400_on_no_receipt_file_id(client):
    """POST /retry-receipt returns 400 when order has no receipt_file_id."""
    order = _make_order_mock(order_id=42, admin_id=5)
    order.receipt_file_id = None

    client._mock_db.query.return_value.filter.return_value.first.return_value = order

    response = client.post(
        "/api/v1/admin/orders/42/retry-receipt",
        headers={"Authorization": "Bearer t"},
    )
    assert response.status_code == 400
    assert "no receipt file_id" in response.json()["detail"].lower()


def test_retry_receipt_502_on_telegram_failure(client, monkeypatch):
    """POST /retry-receipt returns 502 when Telegram download raises."""
    order = _make_order_mock(order_id=42, admin_id=5)
    order.receipt_file_id = "file_abc"

    mock_bot = MagicMock()
    mock_bot.bot_token_enc = b"encrypted_token_blob"

    client._mock_db.query.return_value.filter.return_value.first.side_effect = [
        order,
        mock_bot,
    ]

    fake_dl = AsyncMock(side_effect=RuntimeError("Network timeout"))

    with patch.object(_mod, "download_and_store", fake_dl):
        with patch(
            "app.api.v1.endpoints.user_orders_api.decrypt_token",
            MagicMock(return_value="T"),
        ):
            response = client.post(
                "/api/v1/admin/orders/42/retry-receipt",
                headers={"Authorization": "Bearer t"},
            )

    assert response.status_code == 502
    assert "Telegram download failed" in response.json()["detail"]
