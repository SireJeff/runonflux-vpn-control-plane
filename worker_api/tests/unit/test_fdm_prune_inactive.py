"""Unit tests for _prune_inactive_deployment_domains (global orphan reaper).

Closes the stale-state gap where domains under a DEACTIVATED deployment (and
their live DNS A-records) were never cleaned, because the per-deployment
lifecycle phases only run for ACTIVE deployments. Same MagicMock/isolated-
load style as test_fdm_sync_lifecycle.py (no real DB needed).
"""
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Complete the package __init__ first so the isolated load below doesn't hit
# a partial-init circular import (fdm_sync_service -> package __init__ ->
# fdm_sync_service). In a full-suite run an earlier import does this for us.
import app.services.fdm  # noqa: E402,F401
from tests.unit._fdm_isolated_import import isolated_module_load

_MOD_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "app"
    / "services"
    / "fdm"
    / "fdm_sync_service.py"
)
with isolated_module_load("app.services.fdm.fdm_sync_service", _MOD_PATH) as _mod:
    FdmSyncService = _mod.FdmSyncService


def _run(coro):
    return asyncio.run(coro)


def _domain(id, updated_minutes_ago=60, dns_record_id="rec"):
    d = MagicMock()
    d.id = id
    d.domain_name = "x-%d.operator4.example.invalid" % id
    d.dns_record_id = dns_record_id
    d.tld_id = None
    if updated_minutes_ago is None:
        d.updated_at = None
    else:
        d.updated_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            minutes=updated_minutes_ago
        )
    return d


def _query_all(mock_db, rows):
    # query(FdmDomain).join(FdmDeployment, ...).filter(is_active==False).all()
    mock_db.query.return_value.join.return_value.filter.return_value.all.return_value = (
        rows
    )


def test_prune_deletes_stale_inactive_domain_and_its_dns():
    stale = _domain(1, updated_minutes_ago=60)
    mock_db = MagicMock()
    _query_all(mock_db, [stale])
    svc = FdmSyncService(mock_db)
    with patch.object(
        FdmSyncService, "_delete_dns_record_for_domain", new_callable=AsyncMock
    ) as mdel:
        pruned = _run(svc._prune_inactive_deployment_domains())
    assert pruned == 1
    mdel.assert_awaited_once_with(stale)
    mock_db.delete.assert_called_once_with(stale)
    mock_db.commit.assert_called_once()


def test_prune_skips_recently_updated_domain():
    fresh = _domain(2, updated_minutes_ago=5)
    mock_db = MagicMock()
    _query_all(mock_db, [fresh])
    svc = FdmSyncService(mock_db)
    with patch.object(
        FdmSyncService, "_delete_dns_record_for_domain", new_callable=AsyncMock
    ) as mdel:
        pruned = _run(svc._prune_inactive_deployment_domains())
    assert pruned == 0
    mdel.assert_not_awaited()
    mock_db.delete.assert_not_called()
    mock_db.commit.assert_not_called()


def test_prune_treats_null_updated_at_as_stale():
    nulld = _domain(3, updated_minutes_ago=None)
    mock_db = MagicMock()
    _query_all(mock_db, [nulld])
    svc = FdmSyncService(mock_db)
    with patch.object(
        FdmSyncService, "_delete_dns_record_for_domain", new_callable=AsyncMock
    ):
        pruned = _run(svc._prune_inactive_deployment_domains())
    assert pruned == 1
    mock_db.delete.assert_called_once_with(nulld)


def test_prune_noop_when_no_inactive_domains():
    mock_db = MagicMock()
    _query_all(mock_db, [])
    svc = FdmSyncService(mock_db)
    pruned = _run(svc._prune_inactive_deployment_domains())
    assert pruned == 0
    mock_db.delete.assert_not_called()
    mock_db.commit.assert_not_called()


def test_prune_phase_wired_into_sync_all_deployments():
    import inspect

    src = inspect.getsource(FdmSyncService.sync_all_deployments)
    assert (
        "_prune_inactive_deployment_domains" in src
    ), "prune phase must be wired into sync_all_deployments"
