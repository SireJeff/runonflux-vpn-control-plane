"""Unit tests for FDM liveness pure helpers + any-port probe (Problem B)."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.exc import IntegrityError

from app.services.fdm.liveness import (
    LivenessGate,
    failing_fraction,
    failsafe_tripped,
    is_confirmed_dead,
    is_ip_live,
    next_failure_count,
)


def test_next_failure_count_resets_on_live():
    assert next_failure_count(5, True) == 0


def test_next_failure_count_increments_on_dead():
    assert next_failure_count(2, False) == 3


def test_is_confirmed_dead_threshold():
    assert is_confirmed_dead(3, 3) is True
    assert is_confirmed_dead(2, 3) is False


def test_is_ip_live_true_when_any_port_answers():
    async def run():
        with patch(
            "app.services.fdm.liveness._check_port",
            new=AsyncMock(side_effect=[False, True, False]),
        ):
            return await is_ip_live("1.2.3.4", [10, 20, 30], timeout=1.0)

    assert asyncio.run(run()) is True


def test_is_ip_live_false_when_all_ports_fail():
    async def run():
        with patch(
            "app.services.fdm.liveness._check_port", new=AsyncMock(return_value=False)
        ):
            return await is_ip_live("1.2.3.4", [10, 20], timeout=1.0)

    assert asyncio.run(run()) is False


def test_is_ip_live_fail_open_when_no_ports_known():
    async def run():
        return await is_ip_live("1.2.3.4", [], timeout=1.0)

    # Unknown port map -> cannot judge -> treat as live (never demote blindly).
    assert asyncio.run(run()) is True


def test_failing_fraction_zero_when_nothing_to_judge():
    assert failing_fraction(0, 0) == 0.0
    assert failing_fraction(3, 0) == 0.0  # guards div-by-zero


def test_failing_fraction_ratio():
    assert failing_fraction(3, 4) == 0.75


def test_failsafe_trips_above_fraction():
    assert failsafe_tripped(3, 4, 0.5) is True


def test_failsafe_passes_at_or_below_fraction():
    # exactly at the fraction does not trip (strict >)
    assert failsafe_tripped(2, 4, 0.5) is False
    assert failsafe_tripped(1, 4, 0.5) is False


def test_failsafe_disabled_when_fraction_is_one():
    # MAX_DEAD_FRACTION=1.0 disables the guard; the VM DB test relies on this
    assert failsafe_tripped(4, 4, 1.0) is False


def test_failsafe_no_probes_never_trips():
    assert failsafe_tripped(0, 0, 0.5) is False


def test_failsafe_fires_every_cycle_of_full_synchronized_outage():
    # regression guard: all IPs failing -> tripped (was a 1-cycle-then-blackout
    # bug when keyed on newly-confirmed-dead crossings)
    assert failsafe_tripped(8, 8, 0.5) is True


def test_failsafe_fires_on_majority_desync_deaths():
    # regression guard: 6/10 failing -> tripped, preventing one-by-one demotion
    # to empty (the desynchronized-death failure mode)
    assert failsafe_tripped(6, 10, 0.5) is True


def test_failsafe_allows_minority_genuine_deaths():
    # 2/10 failing -> not tripped -> those IPs demote normally after hysteresis
    assert failsafe_tripped(2, 10, 0.5) is False


def test_probe_many_runs_concurrently_and_respects_bound():
    # Regression guard for the prod SIGKILL: probing must fan out, not run
    # serially. Track peak in-flight probes: serial => peak==1, concurrent =>
    # peak>1, bounded => peak<=concurrency.
    in_flight = 0
    peak = 0

    async def tracking_probe(ip, ports, timeout):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return False

    async def run():
        gate = LivenessGate(db=None)
        ips = [f"1.1.1.{i}" for i in range(10)]
        with patch("app.services.fdm.liveness.is_ip_live", new=tracking_probe):
            return await gate._probe_many(ips, [22], timeout=1.0, concurrency=3)

    result = asyncio.run(run())
    assert result == {f"1.1.1.{i}": False for i in range(10)}
    assert peak > 1, "probes ran serially — the prod-timeout regression"
    assert peak <= 3, "semaphore bound exceeded"


def test_probe_many_empty_is_noop():
    async def run():
        gate = LivenessGate(db=None)
        with patch(
            "app.services.fdm.liveness.is_ip_live", new=AsyncMock(return_value=False)
        ):
            return await gate._probe_many([], [22], timeout=1.0, concurrency=5)

    assert asyncio.run(run()) == {}


def _mock_db_row_lookup(first_side_effect):
    """A MagicMock Session whose query(...).filter(...).first() yields values
    from first_side_effect in order, with a non-suppressing begin_nested()
    SAVEPOINT context manager."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.side_effect = first_side_effect
    cm = MagicMock()
    cm.__enter__.return_value = None
    cm.__exit__.return_value = False  # do NOT swallow the IntegrityError
    db.begin_nested.return_value = cm
    return db


def test_get_or_create_row_returns_existing_without_insert():
    """Row already present -> return it, no SAVEPOINT / INSERT."""
    existing = object()
    db = _mock_db_row_lookup([existing])
    row = LivenessGate(db)._get_or_create_row("ch01", "1.2.3.4")
    assert row is existing
    db.begin_nested.assert_not_called()
    db.flush.assert_not_called()


def test_get_or_create_row_reuses_winner_on_concurrent_insert_race():
    """Minor #5: first-cycle same-(app, IP) INSERT race. Two same-cycle
    deployments of a shared-IP app each miss the SELECT and race the INSERT; the
    loser's flush raises IntegrityError (uq_fdm_ip_liveness_app_ip). The gate
    must roll the failed insert back to its SAVEPOINT and return the winner's
    now-visible row instead of propagating the error (which would fail-open the
    whole deployment for that cycle)."""
    winner = object()
    # 1st first(): initial lookup misses. 2nd first(): post-IntegrityError re-query hits.
    db = _mock_db_row_lookup([None, winner])
    db.flush.side_effect = IntegrityError("INSERT", {}, Exception("duplicate key"))

    row = LivenessGate(db)._get_or_create_row("ch01", "1.2.3.4")

    assert row is winner
    db.begin_nested.assert_called_once()
    assert db.query.return_value.filter.return_value.first.call_count == 2


def test_get_or_create_row_reraises_if_row_still_missing_after_conflict():
    """A genuine IntegrityError with no row on re-query (not the benign race)
    must propagate — don't mask a real DB fault as a phantom success."""
    db = _mock_db_row_lookup([None, None])
    db.flush.side_effect = IntegrityError("INSERT", {}, Exception("not-null violation"))

    try:
        LivenessGate(db)._get_or_create_row("ch01", "1.2.3.4")
        assert False, "expected IntegrityError to propagate"
    except IntegrityError:
        pass
