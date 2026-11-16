"""Integration tests for /admin/free-config endpoints (Task 13).

Uses the importlib-loading + mock-DB + patched-RoleChecker pattern shared by
the other reseller admin API tests (see test_admin_packages_api.py and
test_user_orders_api.py). The brief's assumed `db_session`/`admin_auth_headers`
fixtures do not exist in this suite; this pattern is the established one.

FreeConfigService is patched per-test so no real DB is required. The
invalid-region test exercises pure Pydantic validation (422) and needs no
service call at all.
"""

import importlib.util
import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Load the free_config_api module directly (avoid heavy app/__init__)
# ---------------------------------------------------------------------------
_MOD_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "app"
    / "api"
    / "v1"
    / "endpoints"
    / "free_config_api.py"
)
_spec = importlib.util.spec_from_file_location(
    "app.api.v1.endpoints.free_config_api",
    str(_MOD_PATH),
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["app.api.v1.endpoints.free_config_api"] = _mod
_spec.loader.exec_module(_mod)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ADMIN_AUTH = {"id": 5, "role": "admin", "entity": MagicMock()}


def _fake_admin_call():
    """Zero-param stand-in for RoleChecker.__call__."""
    return ADMIN_AUTH


def _patch_admin_auth(monkeypatch):
    monkeypatch.setattr(
        _mod.RoleChecker,
        "__call__",
        staticmethod(_fake_admin_call),
    )


def _make_config(
    is_enabled=False,
    kind="shared",
    label=None,
    region=None,
    traffic_limit_gb=None,
    duration_days=None,
    shared_credential_ref=None,
):
    """Build a MagicMock that quacks like an AdminFreeConfig ORM row."""
    cfg = MagicMock()
    cfg.is_enabled = is_enabled
    cfg.kind = kind
    cfg.label = label
    cfg.region = region
    cfg.traffic_limit_gb = traffic_limit_gb
    cfg.duration_days = duration_days
    cfg.shared_credential_ref = shared_credential_ref
    return cfg


@pytest.fixture
def client(monkeypatch):
    """Minimal FastAPI app with only the free-config router and a mock DB."""
    _patch_admin_auth(monkeypatch)

    mock_db = MagicMock()

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


def test_get_free_config_creates_default(client, monkeypatch):
    """GET returns the default (disabled) config for the current admin."""
    fake_service = MagicMock()
    fake_service.get_or_create.return_value = _make_config(is_enabled=False)

    monkeypatch.setattr(_mod, "FreeConfigService", lambda db: fake_service)

    r = client.get(
        "/api/v1/admin/free-config",
        headers={"Authorization": "Bearer t"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_enabled"] is False
    assert body["has_credential"] is False
    fake_service.get_or_create.assert_called_once_with(5)


def test_put_free_config_updates(client, monkeypatch):
    """PUT applies is_enabled + label + region and returns the updated config."""
    fake_service = MagicMock()
    fake_service.update.return_value = _make_config(
        is_enabled=True, label="Free", region="eu"
    )

    monkeypatch.setattr(_mod, "FreeConfigService", lambda db: fake_service)

    r = client.put(
        "/api/v1/admin/free-config",
        json={"is_enabled": True, "label": "Free", "region": "eu"},
        headers={"Authorization": "Bearer t"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_enabled"] is True
    assert body["label"] == "Free"
    assert body["region"] == "eu"
    fake_service.update.assert_called_once_with(
        5,
        is_enabled=True,
        kind=None,
        label="Free",
        region="eu",
        traffic_limit_gb=None,
        duration_days=None,
        daily_limit_mb=None,
        max_free_users=None,
    )


def test_put_free_config_rejects_invalid_region(client, monkeypatch):
    """PUT with a non-canonical region is rejected at the schema layer (422)."""
    fake_service = MagicMock()
    monkeypatch.setattr(_mod, "FreeConfigService", lambda db: fake_service)

    r = client.put(
        "/api/v1/admin/free-config",
        json={"region": "zz"},
        headers={"Authorization": "Bearer t"},
    )
    assert r.status_code == 422, r.text
    # Service must not be touched when validation fails.
    fake_service.update.assert_not_called()


def test_rotate_free_config(client, monkeypatch):
    """POST /rotate provisions the shared credential and reports has_credential."""
    fake_service = MagicMock()
    fake_service.rotate.return_value = _make_config(
        is_enabled=True,
        traffic_limit_gb=Decimal("10.00"),
        shared_credential_ref="abc123",
    )

    monkeypatch.setattr(_mod, "FreeConfigService", lambda db: fake_service)

    r = client.post(
        "/api/v1/admin/free-config/rotate",
        headers={"Authorization": "Bearer t"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["has_credential"] is True
    fake_service.rotate.assert_called_once_with(5)
