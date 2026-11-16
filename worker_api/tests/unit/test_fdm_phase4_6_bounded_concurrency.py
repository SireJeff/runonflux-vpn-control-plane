"""Phase 4.6: bounded concurrency for the per-deployment sync loop.

Uses a plain top-level import (mirrors test_fdm_phase4_discovery_cache.py),
NOT the importlib.util.spec_from_file_location / sys.modules swap trick used
by test_fdm_sync_lifecycle.py and test_fdm_phase4_overlap_lock_integration.py
-- that swap is a workaround specific to those files' own needs, not a
requirement for testing FdmSyncService internals in general.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import app.services.fdm.fdm_sync_service as _fdm

FdmSyncService = _fdm.FdmSyncService


def _run(coro):
    return asyncio.run(coro)


def _make_deployment(id=1, flux_app_name="ch01", region="CH", health_check_port=443):
    d = MagicMock()
    d.id = id
    d.flux_app_name = flux_app_name
    d.region = region
    d.health_check_port = health_check_port
    return d


# ---------------------------------------------------------------------------
# _prewarm_discovery_cache
# ---------------------------------------------------------------------------


def test_prewarm_discovery_cache_dedups_by_app_and_port():
    """3 deployments, 2 sharing (app,port), 1 on a different app -> exactly
    2 discovery calls, not 3."""
    deployments = [
        _make_deployment(id=1, flux_app_name="ch01", health_check_port=443),
        _make_deployment(id=2, flux_app_name="ch01", health_check_port=443),
        _make_deployment(id=3, flux_app_name="na01", health_check_port=443),
    ]
    service = FdmSyncService(MagicMock())
    calls = []

    with patch.object(
        service, "_get_cached_instances", new_callable=AsyncMock
    ) as mock_get:

        def _record(app_name, port):
            calls.append((app_name, port))
            return MagicMock()

        mock_get.side_effect = _record
        _run(service._prewarm_discovery_cache(deployments))

    assert sorted(calls) == [
        ("ch01", 443),
        ("na01", 443),
    ], f"expected exactly one call per distinct (app,port); got {calls}"


def test_prewarm_discovery_cache_falls_back_to_443_when_port_unset():
    """health_check_port=None -> falls back to port 443, matching the
    existing `d.health_check_port or 443` convention already used elsewhere
    in this file (fdm_sync_service.py:1763)."""
    deployments = [_make_deployment(id=1, flux_app_name="ch01", health_check_port=None)]
    service = FdmSyncService(MagicMock())
    calls = []

    with patch.object(
        service, "_get_cached_instances", new_callable=AsyncMock
    ) as mock_get:

        def _record(app_name, port):
            calls.append((app_name, port))
            return MagicMock()

        mock_get.side_effect = _record
        _run(service._prewarm_discovery_cache(deployments))

    assert calls == [("ch01", 443)]


# ---------------------------------------------------------------------------
# _sync_deployment_isolated
# ---------------------------------------------------------------------------


def test_sync_deployment_isolated_uses_own_session_not_shared_db():
    """Each isolated task opens its own SessionLocal(), never touching the
    original service's self.db."""
    mock_db = MagicMock()  # the ORIGINAL service's session -- must stay untouched
    scratch_db = MagicMock()
    dep = _make_deployment(id=7, flux_app_name="ch01", region="CH")
    scratch_db.query.return_value.filter.return_value.first.return_value = dep

    service = FdmSyncService(mock_db)
    semaphore = asyncio.Semaphore(4)

    with patch.object(_fdm, "SessionLocal", return_value=scratch_db), patch.object(
        FdmSyncService,
        "sync_deployment",
        new_callable=AsyncMock,
        return_value=MagicMock(status="success"),
    ) as mock_sync:
        key, sync_log = _run(
            service._sync_deployment_isolated(7, "ch01", "CH", semaphore)
        )

    assert key == "ch01:CH"
    mock_sync.assert_awaited_once_with(dep)
    mock_db.rollback.assert_not_called()
    mock_db.commit.assert_not_called()
    scratch_db.close.assert_called_once()


def test_sync_deployment_isolated_opens_session_with_expire_on_commit_false():
    """sync_all_deployments's caller reads .status off every returned
    FdmSyncLog AFTER this scratch session is closed (see the summary log
    line in sync_all_deployments). The default expire_on_commit=True would
    mark every attribute for lazy-reload on the scratch session's own
    commits, which then raises DetachedInstanceError once the session is
    closed -- confirmed live 2026-07-19 (post-Phase-4.7a-deploy incident):
    this aborted every sync_all_deployments cycle via celery's autoretry,
    growing backoff, until fixed by passing expire_on_commit=False here."""
    mock_db = MagicMock()
    scratch_db = MagicMock()
    dep = _make_deployment(id=7, flux_app_name="ch01", region="CH")
    scratch_db.query.return_value.filter.return_value.first.return_value = dep

    service = FdmSyncService(mock_db)
    semaphore = asyncio.Semaphore(4)

    with patch.object(
        _fdm, "SessionLocal", return_value=scratch_db
    ) as mock_session_local, patch.object(
        FdmSyncService,
        "sync_deployment",
        new_callable=AsyncMock,
        return_value=MagicMock(status="success"),
    ):
        _run(service._sync_deployment_isolated(7, "ch01", "CH", semaphore))

    mock_session_local.assert_called_once_with(expire_on_commit=False)


def test_sync_deployment_isolated_rolls_back_before_logging_failure():
    """On sync_deployment failure: scratch db.rollback() before db.add(), and
    the ORIGINAL service's session (self.db) is never touched -- the failure
    is fully contained to this task's own session."""
    mock_db = MagicMock()
    scratch_db = MagicMock()
    dep = _make_deployment(id=9, flux_app_name="na01", region="US")
    scratch_db.query.return_value.filter.return_value.first.return_value = dep

    call_order = []
    scratch_db.rollback.side_effect = lambda: call_order.append("rollback")
    scratch_db.add.side_effect = lambda *a, **k: call_order.append("add")

    service = FdmSyncService(mock_db)
    semaphore = asyncio.Semaphore(4)

    with patch.object(_fdm, "SessionLocal", return_value=scratch_db), patch.object(
        FdmSyncService,
        "sync_deployment",
        new_callable=AsyncMock,
        side_effect=RuntimeError("boom"),
    ):
        key, sync_log = _run(
            service._sync_deployment_isolated(9, "na01", "US", semaphore)
        )

    assert key == "na01:US"
    assert sync_log.status == "failed"
    assert call_order == [
        "rollback",
        "add",
    ], "rollback must happen before writing the failed FdmSyncLog"
    mock_db.rollback.assert_not_called()
    mock_db.commit.assert_not_called()


def test_sync_deployment_isolated_handles_missing_deployment():
    """dep_id no longer resolves in a fresh session (e.g. deleted mid-cycle)
    -> tagged failure log, not a crash; key is still built from the
    caller-supplied dep_app/dep_region since the row can't be loaded to
    derive them."""
    mock_db = MagicMock()
    scratch_db = MagicMock()
    scratch_db.query.return_value.filter.return_value.first.return_value = None

    service = FdmSyncService(mock_db)
    semaphore = asyncio.Semaphore(4)

    with patch.object(_fdm, "SessionLocal", return_value=scratch_db):
        key, sync_log = _run(
            service._sync_deployment_isolated(999, "ch01", "CH", semaphore)
        )

    assert key == "ch01:CH"
    assert sync_log.status == "failed"
    assert sync_log.errors[0]["type"] == "LookupError"
    scratch_db.commit.assert_called_once()


def test_sync_deployment_isolated_handles_query_exception_not_just_missing_row():
    """If the deployment re-query itself raises (e.g. a transient DB error,
    not just a clean 'no row found'), _sync_deployment_isolated must still
    return a tagged failure -- not propagate and abort the whole cycle's
    asyncio.gather()."""
    mock_db = MagicMock()
    scratch_db = MagicMock()
    scratch_db.query.side_effect = RuntimeError("connection reset")

    service = FdmSyncService(mock_db)
    semaphore = asyncio.Semaphore(4)

    with patch.object(_fdm, "SessionLocal", return_value=scratch_db):
        key, sync_log = _run(
            service._sync_deployment_isolated(5, "ch01", "CH", semaphore)
        )

    assert key == "ch01:CH"
    assert sync_log.status == "failed"
    assert sync_log.errors[0]["type"] == "RuntimeError"
    mock_db.rollback.assert_not_called()


def test_sync_deployment_isolated_survives_rollback_commit_close_all_raising():
    """Even if the scratch session's OWN rollback()/commit()/close() calls
    raise (e.g. connection already dead), _sync_deployment_isolated must
    still return a tagged failure -- never propagate and abort the whole
    cycle's asyncio.gather(). Regression test for review finding C-1."""
    mock_db = MagicMock()
    scratch_db = MagicMock()
    dep = _make_deployment(id=9, flux_app_name="na01", region="US")
    scratch_db.query.return_value.filter.return_value.first.return_value = dep
    scratch_db.rollback.side_effect = RuntimeError("rollback failed")
    scratch_db.commit.side_effect = RuntimeError("commit failed")
    scratch_db.close.side_effect = RuntimeError("close failed")

    service = FdmSyncService(mock_db)
    semaphore = asyncio.Semaphore(4)

    with patch.object(_fdm, "SessionLocal", return_value=scratch_db), patch.object(
        FdmSyncService,
        "sync_deployment",
        new_callable=AsyncMock,
        side_effect=RuntimeError("boom"),
    ):
        key, sync_log = _run(
            service._sync_deployment_isolated(9, "na01", "US", semaphore)
        )

    assert key == "na01:US"
    assert sync_log.status == "failed"
    assert sync_log.errors[0]["error"] == "boom"


def test_sync_deployment_isolated_copies_caches_not_shares_by_reference():
    """_discovery_cache/_spec_expected must be per-task copies -- sharing the
    dict object across concurrent tasks means one task's cache-miss write
    mutates state visible to every sibling task. Regression test for review
    finding I-1."""
    mock_db = MagicMock()
    scratch_db = MagicMock()
    dep = _make_deployment(id=7, flux_app_name="ch01", region="CH")
    scratch_db.query.return_value.filter.return_value.first.return_value = dep

    service = FdmSyncService(mock_db)
    service._discovery_cache = {"seed": "value"}
    service._spec_expected = {"seed": 1}
    semaphore = asyncio.Semaphore(4)

    captured = {}

    async def fake_sync(self, deployment):
        captured["discovery_cache"] = self._discovery_cache
        captured["spec_expected"] = self._spec_expected
        self._discovery_cache["mutated"] = "oops"
        return MagicMock(status="success")

    with patch.object(_fdm, "SessionLocal", return_value=scratch_db), patch.object(
        FdmSyncService, "sync_deployment", new=fake_sync
    ):
        _run(service._sync_deployment_isolated(7, "ch01", "CH", semaphore))

    assert captured["discovery_cache"] is not service._discovery_cache
    assert captured["spec_expected"] is not service._spec_expected
    assert (
        "mutated" not in service._discovery_cache
    ), "a copy on scratch must not leak mutations back onto the original service"


# ---------------------------------------------------------------------------
# sync_all_deployments fan-out wiring
# ---------------------------------------------------------------------------


def test_sync_all_deployments_fans_out_and_merges_results():
    """sync_all_deployments's returned dict has the same shape it would have
    produced sequentially: one entry per deployment, keyed 'app:region'."""
    deployments = [
        _make_deployment(id=1, flux_app_name="ch01", region="CH"),
        _make_deployment(id=2, flux_app_name="na01", region="US"),
        _make_deployment(id=3, flux_app_name="row01", region="AR"),
    ]
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = deployments

    async def fake_isolated(self, dep_id, dep_app, dep_region, semaphore):
        return f"{dep_app}:{dep_region}", MagicMock(status="success")

    with patch.object(
        FdmSyncService, "_run_phase", new_callable=AsyncMock
    ), patch.object(
        FdmSyncService, "_prewarm_discovery_cache", new_callable=AsyncMock
    ), patch.object(
        FdmSyncService, "_sync_deployment_isolated", new=fake_isolated
    ):
        service = FdmSyncService(mock_db)
        results = _run(service.sync_all_deployments())

    assert set(results.keys()) == {"ch01:CH", "na01:US", "row01:AR"}
    assert all(r.status == "success" for r in results.values())


def test_sync_all_deployments_respects_concurrency_bound():
    """No more than SYNC_CONCURRENCY deployment-sync tasks run at once, even
    with more deployments than the bound."""
    deployments = [
        _make_deployment(id=i, flux_app_name="ch01", region=f"R{i}") for i in range(6)
    ]
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = deployments

    in_flight = 0
    max_in_flight = 0

    async def fake_isolated(self, dep_id, dep_app, dep_region, semaphore):
        nonlocal in_flight, max_in_flight
        async with semaphore:
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            await asyncio.sleep(0.02)
            in_flight -= 1
            return f"{dep_app}:{dep_region}", MagicMock(status="success")

    with patch.object(
        FdmSyncService, "_run_phase", new_callable=AsyncMock
    ), patch.object(
        FdmSyncService, "_prewarm_discovery_cache", new_callable=AsyncMock
    ), patch.object(
        FdmSyncService, "_sync_deployment_isolated", new=fake_isolated
    ), patch.object(
        FdmSyncService, "SYNC_CONCURRENCY", 2
    ):
        service = FdmSyncService(mock_db)
        results = _run(service.sync_all_deployments())

    assert len(results) == 6
    assert (
        max_in_flight == 2
    ), f"expected exactly 2 concurrent tasks (the bound), got {max_in_flight}"
