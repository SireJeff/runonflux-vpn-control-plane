"""Phase 4.3 integration: sync_all_deployments respects the overlap lock.

Uses the isolated-load helper (fdm_sync_service has a cold circular import at
module load, same as test_fdm_sync_lifecycle.py). Patches overlap_lock ON the
loaded fdm_sync_service module so the isolated load is respected.
"""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import app.services.fdm.fdm_sync_service  # noqa: F401  (cold-import dodge)
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


@asynccontextmanager
async def _held_lock(key, ttl=None):
    """Mimics overlap_lock when the lock is already held by another runner.

    Signature mirrors overlap_lock(key, ttl=None) so the patched mock accepts
    the `overlap_lock("fdm:sync:lock")` call from sync_all_deployments.
    """
    yield False


def test_sync_all_deployments_skips_when_lock_held():
    """T8: when overlap_lock yields False, sync returns {} and runs NO phase."""
    with patch.object(_mod, "overlap_lock", _held_lock), patch.object(
        FdmSyncService, "_run_phase", new=AsyncMock()
    ) as phase_mock:
        service = FdmSyncService(MagicMock())
        result = _run(service.sync_all_deployments())

    assert result == {}
    phase_mock.assert_not_called()  # skipped before any phase runs


def test_sync_all_deployments_proceeds_when_lock_acquired():
    """Sanity complement: when overlap_lock yields True, phases DO run."""

    @asynccontextmanager
    async def _free_lock(key, ttl=None):
        yield True

    with patch.object(_mod, "overlap_lock", _free_lock), patch.object(
        FdmSyncService, "_run_phase", new=AsyncMock()
    ) as phase_mock, patch.object(
        FdmSyncService, "_ensure_pi_for_fdm_domains", new=AsyncMock()
    ):
        # Stop the deployment query from producing work: return no deployments.
        service = FdmSyncService(MagicMock())
        service.db.query.return_value.filter.return_value.all.return_value = []
        result = _run(service.sync_all_deployments())

    assert result == {}  # no deployments -> empty results, but phases RAN
    assert phase_mock.call_count == 10  # all pre-sync phases invoked (Phase 1-10)
