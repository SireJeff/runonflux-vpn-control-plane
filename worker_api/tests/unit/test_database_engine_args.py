"""Regression guard for the 2026-08-18 FDM lock-cascade freeze.

The FDM liveness gate runs a *synchronous* ``INSERT INTO fdm_ip_liveness``
inside an async method. If that INSERT blocks on a row lock held by a
transaction orphaned by a previously SIGKILLed ``fdm.sync_all_deployments``
cycle, the blocking call freezes the whole asyncio event loop until the task
hits its 3600s hard limit -> SIGKILL -> another orphaned lock -> a
self-sustaining cascade that froze every region's FDM sync.

The Postgres engine MUST therefore set a short ``lock_timeout`` (so the INSERT
fails fast and the gate's fail-open path lets the cycle finish) and an
``idle_in_transaction_session_timeout`` (so leaked transactions stop holding
locks). These tests fail if either guard is dropped.
"""

from app.core.database import build_engine_args


def test_postgres_sets_lock_and_idle_timeouts():
    args = build_engine_args("postgresql://u:p@host:5432/db")
    opts = args["connect_args"]["options"]
    assert "lock_timeout=10s" in opts
    assert "idle_in_transaction_session_timeout=300s" in opts


def test_postgres_keeps_pool_config():
    args = build_engine_args("postgresql://u:p@host:5432/db")
    assert "pool_size" in args
    assert args["pool_pre_ping"] is True


def test_sqlite_unaffected():
    """SQLite (tests) must not receive libpq options and must keep its
    thread flag — the timeouts are a Postgres-only concern."""
    args = build_engine_args("sqlite:///./test.db")
    assert args["connect_args"] == {"check_same_thread": False}
    assert "pool_size" not in args
