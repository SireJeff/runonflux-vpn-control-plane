"""Phase 4.7a: 2 defensive guards discovered while closing out the FDM
Hardening project's backlog.

1. sync_deployment's finalize tail (spec-gap injection, timestamps, final
   commit) was unguarded -- a failure there left the sync_log row
   permanently stuck at status="running", since the only write that had
   landed was the initial one at the top of the method.
2. _sync_deployment_isolated's `db = SessionLocal()` sat outside its own
   try block (flagged Minor during Phase 4.6's final opus review) -- a
   hypothetical construction failure would escape uncaught.

Uses a plain top-level import (mirrors test_fdm_phase4_6_bounded_concurrency.py),
NOT the sys.modules swap trick used by test_fdm_sync_lifecycle.py.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import app.services.fdm.fdm_sync_service as _fdm
from app.core.config import settings
from app.models.fdm import FdmDeployment

FdmSyncService = _fdm.FdmSyncService


def _run(coro):
    return asyncio.run(coro)


def _make_deployment(id=1, flux_app_name="ch01", region="CH"):
    d = MagicMock()
    d.id = id
    d.flux_app_name = flux_app_name
    d.region = region
    d.consecutive_failures = 0
    return d


def test_sync_deployment_survives_finalize_commit_failure():
    """If the final commit (after status is decided) raises once, the retry
    path must still land the row at status='failed', not leave it at
    'running'."""
    mock_db = MagicMock()
    deployment = _make_deployment()

    commit_calls = {"count": 0}

    def commit_side_effect():
        commit_calls["count"] += 1
        if commit_calls["count"] == 2:
            # 1st commit = the initial "running" row (line ~164).
            # 2nd commit = the finalize tail -- this is the one that fails.
            raise RuntimeError("connection reset")

    mock_db.commit.side_effect = commit_side_effect

    service = FdmSyncService(mock_db)
    with patch.object(
        service, "_discover_instances", new_callable=AsyncMock, return_value=([], [])
    ), patch.object(service, "_ensure_domains_exist", return_value=[]), patch.object(
        service, "_inject_spec_gap_into_log", new_callable=MagicMock
    ):
        sync_log = _run(service.sync_deployment(deployment))

    assert sync_log.status == "failed", (
        "a finalize-commit failure must still result in status='failed' via "
        "the retry path, not leave the row at 'running'"
    )
    assert mock_db.commit.call_count == 3, (
        "expected: initial running-row commit, failed finalize attempt, "
        "successful retry commit. (_ensure_domains_exist is patched to "
        "return [] directly -- it does its own DB queries via TLD lookups "
        "unrelated to this test, and letting it run for real against a bare "
        "MagicMock db would make the exact commit count unpredictable.)"
    )


def test_sync_deployment_logs_but_does_not_raise_when_both_commits_fail():
    """If BOTH the finalize commit and the retry commit fail, the method
    must still return without raising (the unfixable case is logged, not
    propagated)."""
    mock_db = MagicMock()
    deployment = _make_deployment()
    mock_db.commit.side_effect = [
        None,
        RuntimeError("still down"),
        RuntimeError("still down"),
    ]

    service = FdmSyncService(mock_db)
    with patch.object(
        service, "_discover_instances", new_callable=AsyncMock, return_value=([], [])
    ), patch.object(service, "_ensure_domains_exist", return_value=[]), patch.object(
        service, "_inject_spec_gap_into_log", new_callable=MagicMock
    ):
        sync_log = _run(service.sync_deployment(deployment))

    assert sync_log is not None, "must return the sync_log object, not raise"


def test_sync_deployment_isolated_survives_session_local_construction_failure():
    """If SessionLocal() itself raises, _sync_deployment_isolated must still
    return a tagged failure -- the finally's db.close() must not crash with
    UnboundLocalError when db was never assigned."""
    mock_db = MagicMock()
    service = FdmSyncService(mock_db)
    semaphore = asyncio.Semaphore(4)

    with patch.object(_fdm, "SessionLocal", side_effect=RuntimeError("pool exhausted")):
        key, sync_log = _run(
            service._sync_deployment_isolated(1, "ch01", "CH", semaphore)
        )

    assert key == "ch01:CH"
    assert sync_log.status == "failed"
    assert sync_log.errors[0]["type"] == "RuntimeError"


def test_sync_deployment_finalize_recovery_preserves_deployment_outcome():
    """A finalize-commit failure's rollback() must not silently revert
    deployment's already-decided last_sync_status/consecutive_failures back
    to stale last-committed values. Requires REAL SQLAlchemy commit/rollback
    semantics -- a MagicMock db's rollback() is a no-op and cannot reproduce
    real attribute-expiry, so this test uses a self-contained in-memory
    SQLite engine + a real ORM session, NOT the shared conftest `db_session`
    fixture: that fixture wraps every test in one externally-managed
    connection-level transaction (`connection.begin()` before the session is
    even created), so a real mid-test `rollback()` unwinds the test's own
    setup along with it -- confirmed empirically to raise
    sqlalchemy.orm.exc.ObjectDeletedError on the deployment row itself, not
    just its uncommitted attributes. A plain top-level `create_all()` also
    doesn't work here: FdmSyncLog.errors is a Postgres-only JSONB column
    that SQLite's DDL compiler can't render, so the 2 tables below are
    hand-created with a plain TEXT column standing in for it -- the ORM
    round-trips this fine for what this test exercises."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                """CREATE TABLE fdm_deployments (
            id INTEGER PRIMARY KEY, flux_app_name VARCHAR(255) NOT NULL,
            region VARCHAR(2) NOT NULL, domain_pool_size INTEGER, base_domain VARCHAR(255),
            protocol_name VARCHAR(50), health_check_port INTEGER, socks5_port INTEGER,
            is_active BOOLEAN, last_sync_at TIMESTAMP, last_sync_status VARCHAR(50),
            consecutive_failures INTEGER NOT NULL DEFAULT 0, created_at TIMESTAMP, updated_at TIMESTAMP
        )"""
            )
        )
        conn.execute(
            text(
                """CREATE TABLE fdm_sync_logs (
            id INTEGER PRIMARY KEY, deployment_id INTEGER NOT NULL,
            sync_started_at TIMESTAMP NOT NULL, sync_completed_at TIMESTAMP,
            instances_found INTEGER, instances_healthy INTEGER, domains_updated INTEGER,
            errors TEXT, status VARCHAR(50), created_at TIMESTAMP
        )"""
            )
        )

    db = sessionmaker(bind=engine)()

    deployment = FdmDeployment(
        flux_app_name="ch01",
        region="CH",
        consecutive_failures=2,
        last_sync_status="success",
    )
    db.add(deployment)
    db.commit()  # genuinely, durably committed baseline: consecutive_failures=2, last_sync_status="success"

    service = FdmSyncService(db=db)

    real_commit = db.commit
    calls = {"n": 0}

    def flaky_commit():
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("connection reset")
        return real_commit()

    db.commit = flaky_commit

    # Disable the (orthogonal) endpoint-liveness gate: this test's minimal
    # in-memory schema has no flux_app_registrations table, and the gate is
    # unrelated to the finalize-recovery semantics under test. This exercises
    # the real FDM_LIVENESS_ENABLED kill-switch early-return, restoring the
    # exact pre-feature sync_deployment flow.
    with patch.object(settings, "FDM_LIVENESS_ENABLED", False), patch.object(
        service,
        "_discover_instances",
        new_callable=AsyncMock,
        return_value=(["1.2.3.4"], []),
    ), patch.object(
        service, "_filter_ips_by_region", new_callable=AsyncMock, return_value=[]
    ), patch.object(
        service, "_ensure_domains_exist", return_value=[]
    ), patch.object(
        service, "_inject_spec_gap_into_log", new_callable=MagicMock
    ):
        sync_log = _run(service.sync_deployment(deployment))

    # This cycle discovers 1 IP (instances_found=1>0) but 0 in-region, so the
    # "failed" branch runs AND increments consecutive_failures: 2 -> 3. If
    # the finalize tail's rollback() silently reverted deployment's
    # uncommitted attributes (the bug), these would read back as the STALE
    # committed baseline (2, "success") instead of this cycle's real
    # decision (3, "failed").
    assert deployment.last_sync_status == "failed", (
        "rollback() must not silently revert deployment.last_sync_status "
        "back to the stale pre-cycle committed value"
    )
    assert deployment.consecutive_failures == 3, (
        "rollback() must not silently revert deployment.consecutive_failures "
        "back to the stale pre-cycle committed value"
    )
    assert sync_log.status == "failed"

    db.close()


def _sqlite_fdm_session():
    """In-memory SQLite with the 2 FDM tables sync_deployment touches, hand-DDL'd
    (FdmSyncLog.errors is Postgres-only JSONB -> plain TEXT here). Mirrors the
    harness in test_sync_deployment_finalize_recovery_preserves_deployment_outcome."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                """CREATE TABLE fdm_deployments (
            id INTEGER PRIMARY KEY, flux_app_name VARCHAR(255) NOT NULL,
            region VARCHAR(2) NOT NULL, domain_pool_size INTEGER, base_domain VARCHAR(255),
            protocol_name VARCHAR(50), health_check_port INTEGER, socks5_port INTEGER,
            is_active BOOLEAN, last_sync_at TIMESTAMP, last_sync_status VARCHAR(50),
            consecutive_failures INTEGER NOT NULL DEFAULT 0, created_at TIMESTAMP, updated_at TIMESTAMP
        )"""
            )
        )
        conn.execute(
            text(
                """CREATE TABLE fdm_sync_logs (
            id INTEGER PRIMARY KEY, deployment_id INTEGER NOT NULL,
            sync_started_at TIMESTAMP NOT NULL, sync_completed_at TIMESTAMP,
            instances_found INTEGER, instances_healthy INTEGER, domains_updated INTEGER,
            errors TEXT, status VARCHAR(50), created_at TIMESTAMP
        )"""
            )
        )
    return sessionmaker(bind=engine)()


def test_sync_deployment_records_instance_counts_when_gate_fails_open():
    """Minor #6: sync_log.instances_found/instances_healthy must be assigned
    AFTER the liveness gate. The gate's fail-open path calls self.db.rollback()
    on a probe error; if the counts were assigned BEFORE the gate, that rollback
    would expire them back to the NULL the initial running-row was inserted with
    and the cycle would log NULL counts (and even hit `None > 0` at the failed-
    branch guard). With the assignment moved after the gate, a fail-open cycle
    still records the real counts. Uses a real ORM session so rollback() has real
    attribute-expiry semantics (a MagicMock rollback is a no-op)."""
    db = _sqlite_fdm_session()
    deployment = FdmDeployment(
        flux_app_name="ch01",
        region="CH",
        consecutive_failures=0,
        last_sync_status="success",
    )
    db.add(deployment)
    db.commit()

    service = FdmSyncService(db=db)

    # LivenessGate(...).gate(...) raises -> _apply_liveness_gate catches, rolls
    # back the shared session, and serves all_ips (fail-open).
    failing_gate = MagicMock()
    failing_gate.return_value.gate = AsyncMock(side_effect=RuntimeError("probe boom"))

    with patch.object(settings, "FDM_LIVENESS_ENABLED", True), patch.object(
        _fdm, "LivenessGate", failing_gate
    ), patch.object(
        service,
        "_discover_instances",
        new_callable=AsyncMock,
        return_value=(["1.2.3.4", "5.6.7.8"], ["1.2.3.4"]),
    ), patch.object(
        service,
        "_filter_ips_by_region",
        new_callable=AsyncMock,
        return_value=["1.2.3.4", "5.6.7.8"],
    ), patch.object(
        service, "_manage_domain_lifecycle", new_callable=AsyncMock
    ), patch.object(
        service, "_ensure_domains_exist", return_value=[]
    ), patch.object(
        service, "_inject_spec_gap_into_log", new_callable=MagicMock
    ):
        sync_log = _run(service.sync_deployment(deployment))

    failing_gate.return_value.gate.assert_awaited_once()
    assert sync_log.instances_found == 2, (
        "a gate fail-open cycle must still record instances_found (2 discovered), "
        "not the NULL that the pre-gate assignment order would leave after rollback"
    )
    assert sync_log.instances_healthy == 1

    db.close()
