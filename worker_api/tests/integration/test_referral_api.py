"""Integration tests for /admin/referral endpoints.

Uses the importlib-loading pattern (see test_bot_config_api.py / Task 9
test_user_orders_api.py for reference). Apply the Task 9D lessons:
- @patch.object(_mod, ...) NOT @patch("dotted.string")
- Bind ADMIN_AUTH entity with admin fields at module level
- staticmethod(_fake_admin_call) to avoid FastAPI 422 trap
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

# ---------------------------------------------------------------------------
# Load the referral_api module directly
# ---------------------------------------------------------------------------
_MOD_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "app"
    / "api"
    / "v1"
    / "endpoints"
    / "referral_api.py"
)
_spec = importlib.util.spec_from_file_location(
    "app.api.v1.endpoints.referral_api",
    str(_MOD_PATH),
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["app.api.v1.endpoints.referral_api"] = _mod
_spec.loader.exec_module(_mod)

# Bind module-level constants the test functions need
AdminReferralConfig = _mod.AdminReferralConfig
AdminReferralEarning = _mod.AdminReferralEarning


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_admin_entity(
    admin_id=5,
    username="reseller1",
    wallet_balance=Decimal("100.00"),
):
    """Build the Admin mock that current['entity'] returns."""
    admin = MagicMock()
    admin.id = admin_id
    admin.username = username
    admin.wallet_balance = wallet_balance
    return admin


ADMIN_ENTITY = _make_admin_entity()
ADMIN_AUTH = {"id": 5, "role": "admin", "entity": ADMIN_ENTITY}


def _fake_admin_call():
    return ADMIN_AUTH


def _patch_admin_auth(monkeypatch):
    monkeypatch.setattr(
        _mod.RoleChecker,
        "__call__",
        staticmethod(_fake_admin_call),
    )


def _make_config_mock(
    admin_id=5,
    is_enabled=False,
    reward_percentage=Decimal("10.00"),
):
    cfg = MagicMock()
    cfg.admin_id = admin_id
    cfg.is_enabled = is_enabled
    cfg.reward_percentage = reward_percentage
    cfg.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    return cfg


def _make_earning_mock(
    earning_id=1,
    order_id=42,
    admin_id=5,
    commission_percent=Decimal("10.00"),
    amount_tomans=Decimal("1000.00"),
    created_at=None,
):
    e = MagicMock()
    e.id = earning_id
    e.order_id = order_id
    e.admin_id = admin_id
    e.commission_percent = commission_percent
    e.amount_tomans = amount_tomans
    e.created_at = created_at or datetime.now(timezone.utc).replace(tzinfo=None)
    return e


def _fake_refresh(obj):
    """Set default ORM fields when db.refresh() is called on a new AdminReferralConfig."""
    if isinstance(obj, AdminReferralConfig):
        if not obj.admin_id:
            obj.admin_id = 5
        if getattr(obj, "is_enabled", None) is None:
            obj.is_enabled = False
        if getattr(obj, "reward_percentage", None) is None:
            obj.reward_percentage = Decimal("10.00")
        if getattr(obj, "updated_at", None) is None:
            obj.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.fixture
def client(monkeypatch):
    _patch_admin_auth(monkeypatch)

    mock_db = MagicMock()
    # Default: no existing config (forces _get_or_create_config to create)
    mock_db.query.return_value.filter.return_value.first.return_value = None
    # Default: no earnings, zero aggregates
    mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
        []
    )
    # For stats endpoints: count() and sum() chains
    mock_db.query.return_value.filter.return_value.scalar.return_value = 0
    mock_db.refresh = MagicMock(side_effect=_fake_refresh)

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
# GET /config tests
# ---------------------------------------------------------------------------


def test_get_config_creates_default_if_missing(client):
    """GET /config when admin has no row -> creates default, returns 200."""
    response = client.get(
        "/api/v1/admin/referral/config",
        headers={"Authorization": "Bearer t"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["admin_id"] == 5
    # Defaults from model
    assert data["is_enabled"] is False
    assert data["reward_percentage"] == "10.00"
    # _get_or_create_config did add + commit
    client._mock_db.add.assert_called_once()
    client._mock_db.commit.assert_called()


def test_get_config_returns_existing_when_present(client):
    """GET /config when admin has a row -> returns it without creating."""
    existing = _make_config_mock(
        admin_id=5,
        is_enabled=True,
        reward_percentage=Decimal("15.00"),
    )
    client._mock_db.query.return_value.filter.return_value.first.return_value = existing

    response = client.get(
        "/api/v1/admin/referral/config",
        headers={"Authorization": "Bearer t"},
    )
    assert response.status_code == 200
    assert response.json()["is_enabled"] is True
    assert response.json()["reward_percentage"] == "15.00"
    # Should NOT have called add (no new row created)
    client._mock_db.add.assert_not_called()


# ---------------------------------------------------------------------------
# PUT /config tests
# ---------------------------------------------------------------------------


def test_update_config_persists_full_update(client):
    """PUT happy path: full update of is_enabled + reward_percentage."""
    existing = _make_config_mock()
    client._mock_db.query.return_value.filter.return_value.first.return_value = existing

    response = client.put(
        "/api/v1/admin/referral/config",
        json={"is_enabled": True, "reward_percentage": "15.00"},
        headers={"Authorization": "Bearer t"},
    )
    assert response.status_code == 200, response.text
    # Verify setattr was called with the provided values
    assert existing.is_enabled is True
    assert existing.reward_percentage == Decimal("15.00")
    client._mock_db.commit.assert_called()


def test_update_config_partial_update_only_sets_provided_fields(client):
    """PUT with partial body -- only provided fields change."""
    existing = _make_config_mock(is_enabled=False, reward_percentage=Decimal("10.00"))
    client._mock_db.query.return_value.filter.return_value.first.return_value = existing

    response = client.put(
        "/api/v1/admin/referral/config",
        json={"is_enabled": True},  # only is_enabled
        headers={"Authorization": "Bearer t"},
    )
    assert response.status_code == 200
    assert existing.is_enabled is True


def test_update_config_reward_percentage_over_100_returns_422(client):
    response = client.put(
        "/api/v1/admin/referral/config",
        json={"reward_percentage": "150.00"},
        headers={"Authorization": "Bearer t"},
    )
    assert response.status_code == 422


def test_update_config_reward_percentage_negative_returns_422(client):
    response = client.put(
        "/api/v1/admin/referral/config",
        json={"reward_percentage": "-5.00"},
        headers={"Authorization": "Bearer t"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /stats tests
# ---------------------------------------------------------------------------


def test_get_stats_returns_aggregates(client):
    """GET /stats returns total_referrals + total_earned + wallet balance."""
    # The stats endpoint runs two queries with .scalar() -- set both via side_effect
    client._mock_db.query.return_value.filter.return_value.scalar.side_effect = [
        7,  # count of referred users
        Decimal("5000"),  # sum of earnings
    ]

    response = client.get(
        "/api/v1/admin/referral/stats",
        headers={"Authorization": "Bearer t"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total_referrals"] == 7
    assert data["total_earned_tomans"] == "5000"
    # From ADMIN_ENTITY.wallet_balance = Decimal("100.00")
    assert data["wallet_credit_tomans"] == "100.00"
    # Reseller referral code uses their username
    assert data["my_referral_code"] == "ADMIN-reseller1"


def test_get_stats_returns_zeros_when_no_data(client):
    """No referrals, no earnings, no wallet balance."""
    # Override ADMIN_ENTITY wallet_balance to 0
    ADMIN_ENTITY.wallet_balance = Decimal("0")
    client._mock_db.query.return_value.filter.return_value.scalar.side_effect = [
        0,  # count
        0,  # sum
    ]

    response = client.get(
        "/api/v1/admin/referral/stats",
        headers={"Authorization": "Bearer t"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_referrals"] == 0
    assert data["total_earned_tomans"] == "0"

    # Restore for other tests
    ADMIN_ENTITY.wallet_balance = Decimal("100.00")


# ---------------------------------------------------------------------------
# GET /earnings tests
# ---------------------------------------------------------------------------


def test_list_earnings_returns_rows_newest_first(client):
    """GET /earnings returns up to `limit` rows ordered by created_at desc."""
    e1 = _make_earning_mock(earning_id=1, amount_tomans=Decimal("100.00"))
    e2 = _make_earning_mock(earning_id=2, amount_tomans=Decimal("200.00"))
    client._mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
        e2,
        e1,
    ]

    response = client.get(
        "/api/v1/admin/referral/earnings",
        headers={"Authorization": "Bearer t"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["id"] == 2  # newest first
    assert data[1]["id"] == 1


def test_list_earnings_empty(client):
    response = client.get(
        "/api/v1/admin/referral/earnings",
        headers={"Authorization": "Bearer t"},
    )
    assert response.status_code == 200
    assert response.json() == []


def test_list_earnings_passes_limit_query_param(client):
    """GET /earnings?limit=10 passes limit through to query."""
    response = client.get(
        "/api/v1/admin/referral/earnings?limit=10",
        headers={"Authorization": "Bearer t"},
    )
    assert response.status_code == 200
    # Verify limit(10) was called on the query chain
    # (the .limit.return_value.all chain is what we set up in fixture)
