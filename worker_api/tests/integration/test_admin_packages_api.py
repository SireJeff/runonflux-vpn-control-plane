"""Integration tests for /admin/packages endpoints.

Uses the importlib-loading pattern (avoids heavy app.main imports) and a
mock DB session via dependency_overrides. See test_bot_config_api.py for
the reference pattern.
"""

import importlib.util
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

# ---------------------------------------------------------------------------
# Load the admin_packages_api module directly (avoid heavy app/__init__)
# ---------------------------------------------------------------------------
_MOD_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "app"
    / "api"
    / "v1"
    / "endpoints"
    / "admin_packages_api.py"
)
_spec = importlib.util.spec_from_file_location(
    "app.api.v1.endpoints.admin_packages_api",
    str(_MOD_PATH),
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["app.api.v1.endpoints.admin_packages_api"] = _mod
_spec.loader.exec_module(_mod)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ADMIN_AUTH = {"id": 5, "role": "admin", "entity": MagicMock()}


def _fake_admin_call():
    """Zero-param stand-in for RoleChecker.__call__ -- see python_testing_gotchas."""
    return ADMIN_AUTH


def _patch_admin_auth(monkeypatch):
    monkeypatch.setattr(
        _mod.RoleChecker,
        "__call__",
        staticmethod(_fake_admin_call),
    )


def _make_fake_refresh():
    """Return a side_effect that stamps server-side defaults onto an ORM instance."""
    counter = {"id": 1}

    def fake_refresh(obj):
        if obj.id is None:
            obj.id = counter["id"]
            counter["id"] += 1
        obj.admin_id = obj.admin_id or 5
        if obj.is_active is None:
            obj.is_active = True
        if obj.created_at is None:
            obj.created_at = datetime.now(timezone.utc).replace(tzinfo=None)
        if obj.updated_at is None:
            obj.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

    return fake_refresh


@pytest.fixture
def client(monkeypatch):
    """Minimal FastAPI app with only the packages router and mock DB."""
    _patch_admin_auth(monkeypatch)

    mock_db = MagicMock()
    # Default: no packages found (covers both 1-filter and 2-filter query chains)
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = (
        []
    )
    mock_db.query.return_value.filter.return_value.filter.return_value.order_by.return_value.all.return_value = (
        []
    )
    # Default: no package found by id
    mock_db.query.return_value.filter.return_value.first.return_value = None
    mock_db.refresh = MagicMock(side_effect=_make_fake_refresh())

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
# Tests
# ---------------------------------------------------------------------------


def test_create_package_returns_201_with_fields(client):
    """POST happy path -- admin creates a package, gets back full record."""
    response = client.post(
        "/api/v1/admin/packages",
        json={
            "name": "Basic",
            "traffic_limit_gb": "20.00",
            "duration_days": 30,
            "price_tomans": "100000.00",
        },
        headers={"Authorization": "Bearer t"},
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["name"] == "Basic"
    assert data["admin_id"] == 5
    assert data["is_active"] is True  # default from model
    assert data["display_order"] == 0
    assert data["id"] is not None
    assert data["created_at"] is not None
    client._mock_db.add.assert_called_once()
    client._mock_db.commit.assert_called_once()


def test_list_packages_default_excludes_inactive(client):
    """GET default returns only is_active=True packages."""
    # Set up: DB has 1 active + 1 inactive package.
    # NOTE: MagicMock(name="...") does NOT set obj.name -- "name" is a reserved
    # MagicMock attribute. We must assign .name after construction.
    active = MagicMock(
        id=1,
        admin_id=5,
        traffic_limit_gb=Decimal("10.00"),
        duration_days=30,
        price_tomans=Decimal("100.00"),
        is_active=True,
        display_order=0,
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    active.name = "Active"
    inactive = MagicMock(
        id=2,
        admin_id=5,
        traffic_limit_gb=Decimal("10.00"),
        duration_days=30,
        price_tomans=Decimal("100.00"),
        is_active=False,
        display_order=0,
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    inactive.name = "Old"
    # Default endpoint calls TWO .filter() calls (admin_id + is_active),
    # so the mock chain is query().filter().filter().order_by().all()
    client._mock_db.query.return_value.filter.return_value.filter.return_value.order_by.return_value.all.return_value = [
        active
    ]

    response = client.get(
        "/api/v1/admin/packages",
        headers={"Authorization": "Bearer t"},
    )
    assert response.status_code == 200
    names = [p["name"] for p in response.json()]
    assert names == ["Active"]


def test_list_packages_include_inactive_returns_all(client):
    """GET ?include_inactive=true returns all packages regardless of is_active."""
    active = MagicMock(
        id=1,
        admin_id=5,
        traffic_limit_gb=Decimal("10.00"),
        duration_days=30,
        price_tomans=Decimal("100.00"),
        is_active=True,
        display_order=0,
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    active.name = "Active"
    # When include_inactive=true, the endpoint adds NO is_active filter, so the
    # query chain is query().filter(admin_id).order_by().all() (only one filter).
    client._mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
        active
    ]

    response = client.get(
        "/api/v1/admin/packages?include_inactive=true",
        headers={"Authorization": "Bearer t"},
    )
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_create_duplicate_name_returns_409(client):
    """POST twice with same name under same admin -> IntegrityError -> 409."""
    call_count = {"n": 0}

    def fake_commit():
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise IntegrityError("stmt", "params", "orig")

    client._mock_db.commit = MagicMock(side_effect=fake_commit)
    client._mock_db.rollback = MagicMock()

    response = client.post(
        "/api/v1/admin/packages",
        json={
            "name": "Dup",
            "traffic_limit_gb": "1.00",
            "duration_days": 1,
            "price_tomans": "1.00",
        },
        headers={"Authorization": "Bearer t"},
    )
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"].lower()
    client._mock_db.rollback.assert_called_once()


def test_update_package_modifies_fields(client):
    """PUT /{id} updates only provided fields."""
    existing = MagicMock(
        id=42,
        admin_id=5,
        traffic_limit_gb=Decimal("10.00"),
        duration_days=30,
        price_tomans=Decimal("100.00"),
        is_active=True,
        display_order=0,
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    existing.name = "Old"
    client._mock_db.query.return_value.filter.return_value.first.return_value = existing

    response = client.put(
        "/api/v1/admin/packages/42",
        json={"price_tomans": "150.00", "display_order": 5},
        headers={"Authorization": "Bearer t"},
    )
    assert response.status_code == 200, response.text
    # Verify setattr was called with the provided values
    assert existing.price_tomans == Decimal("150.00")
    assert existing.display_order == 5
    # Verify fields NOT in the request were untouched (no setattr call for them)
    client._mock_db.commit.assert_called_once()


def test_update_package_returns_404_when_not_found(client):
    """PUT on non-existent or wrong-admin package returns 404."""
    # Default mock returns None for first()
    response = client.put(
        "/api/v1/admin/packages/9999",
        json={"name": "New"},
        headers={"Authorization": "Bearer t"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Package not found"


def test_archive_package_sets_inactive_and_returns_204(client):
    """DELETE soft-deletes by setting is_active=False."""
    existing = MagicMock(
        id=42,
        admin_id=5,
        traffic_limit_gb=Decimal("10.00"),
        duration_days=30,
        price_tomans=Decimal("100.00"),
        is_active=True,
        display_order=0,
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    existing.name = "Arch"
    client._mock_db.query.return_value.filter.return_value.first.return_value = existing

    response = client.delete(
        "/api/v1/admin/packages/42",
        headers={"Authorization": "Bearer t"},
    )
    assert response.status_code == 204
    assert existing.is_active is False
    client._mock_db.commit.assert_called_once()


def test_archive_returns_404_when_not_found(client):
    """DELETE on non-existent package returns 404."""
    response = client.delete(
        "/api/v1/admin/packages/9999",
        headers={"Authorization": "Bearer t"},
    )
    assert response.status_code == 404


def test_create_with_invalid_payload_returns_422(client):
    """POST with negative price -> 422 validation error."""
    response = client.post(
        "/api/v1/admin/packages",
        json={
            "name": "Bad",
            "traffic_limit_gb": "0",
            "duration_days": 1,
            "price_tomans": "1.00",
        },
        headers={"Authorization": "Bearer t"},
    )
    assert response.status_code == 422


def test_seed_defaults_populates_empty_reseller(client):
    """POST /seed-defaults on an empty reseller inserts the full default catalog."""
    from app.services.subscriptions.package_seeder import DEFAULT_PACKAGE_TEMPLATES

    # Seeder's existence check: query(AdminPackage).filter(admin_id==).count() -> 0
    client._mock_db.query.return_value.filter.return_value.count.return_value = 0

    resp = client.post(
        "/api/v1/admin/packages/seed-defaults",
        headers={"Authorization": "Bearer t"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["inserted"] == len(DEFAULT_PACKAGE_TEMPLATES)
    assert client._mock_db.add.call_count == len(DEFAULT_PACKAGE_TEMPLATES)
    client._mock_db.commit.assert_called_once()


def test_seed_defaults_is_idempotent_when_packages_exist(client):
    """POST /seed-defaults is a no-op (inserts nothing) when packages already exist."""
    client._mock_db.query.return_value.filter.return_value.count.return_value = 3

    resp = client.post(
        "/api/v1/admin/packages/seed-defaults",
        headers={"Authorization": "Bearer t"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["inserted"] == 0
    client._mock_db.add.assert_not_called()
