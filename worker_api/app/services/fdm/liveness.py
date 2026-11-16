"""FDM endpoint-liveness gating (Problem B).

Any-port-alive TCP liveness with N-cycle hysteresis, used by
FdmSyncService.sync_deployment to exclude allocated-but-dead Flux IPs from
domain assignment and to flip their ProtocolInstance.is_active gate. See
docs/superpowers/specs/2026-08-01-fdm-endpoint-liveness-design.md.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional, Set

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.fdm_ip_liveness import FdmIpLiveness
from app.models.flux_app_registration import FluxAppRegistration
from app.models.ip_management import ProtocolInstance

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def next_failure_count(prev: int, is_live: bool) -> int:
    """New consecutive-failure count: reset to 0 on live, else prev + 1."""
    return 0 if is_live else (prev or 0) + 1


def is_confirmed_dead(failures: int, dead_cycles: int) -> bool:
    """An IP is confirmed dead once it has failed >= dead_cycles in a row."""
    return failures >= dead_cycles


def failing_fraction(failing_count: int, total: int) -> float:
    """Fraction of an app's consensus IPs currently in a failing state
    (latest probe failed). 0.0 when total is 0 (nothing to judge)."""
    if total <= 0:
        return 0.0
    return failing_count / total


def failsafe_tripped(failing_count: int, total: int, max_fraction: float) -> bool:
    """Probe-side / worker-egress outage guard, keyed on the CURRENT
    probe-failure fraction (not on hysteresis-threshold crossings).

    True when the fraction of the app's consensus IPs currently failing exceeds
    max_fraction — the signature of an egress outage, which fails ~all probes
    simultaneously and so keeps the fraction high for the whole outage (fires
    every cycle, synchronized deaths or not). A small steady fraction of genuine
    deaths stays below the threshold and is demoted normally. Strict ``>`` so
    max_fraction=1.0 disables the guard.
    """
    return failing_fraction(failing_count, total) > max_fraction


async def _check_port(ip: str, port: int, timeout: float) -> bool:
    """True if a TCP connection to ip:port completes within timeout.

    On Python 3.11 ``asyncio.wait_for`` awaits cancellation of the inner
    ``open_connection`` on timeout, so a timed-out attempt does not leak. Any
    writer we DO obtain is closed in ``finally`` so no successful/late-completing
    connection is left open (avoids per-probe 'unclosed transport'
    ResourceWarnings under real timeouts).
    """
    writer = None
    try:
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port), timeout=timeout
        )
        return True
    except Exception:
        return False
    finally:
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass


async def is_ip_live(ip: str, ports: List[int], timeout: float) -> bool:
    """Any-port-alive: True if ip answers on >=1 of ports.

    Fail-open when ports is empty (unknown port map) — never demote an IP we
    cannot judge.
    """
    if not ports:
        return True
    results = await asyncio.gather(
        *[_check_port(ip, p, timeout) for p in ports], return_exceptions=True
    )
    return any(r is True for r in results)


class LivenessGate:
    """Refresh per-(app, IP) liveness and gate dead IPs out of FDM serving."""

    def __init__(self, db: Session):
        self.db = db

    def _app_ports(self, flux_app_name: str) -> List[int]:
        reg: Optional[FluxAppRegistration] = (
            self.db.query(FluxAppRegistration)
            .filter(FluxAppRegistration.app_name == flux_app_name)
            .first()
        )
        if not reg or not reg.protocol_ports:
            return []
        ports: List[int] = []
        for val in dict(reg.protocol_ports).values():
            try:
                ports.append(int(val))
            except (TypeError, ValueError):
                logger.warning(
                    "Ignoring non-integer port %r in protocol_ports for %s",
                    val,
                    flux_app_name,
                )
                continue
        return ports

    def _query_row(self, flux_app_name: str, ip: str) -> Optional[FdmIpLiveness]:
        return (
            self.db.query(FdmIpLiveness)
            .filter(
                FdmIpLiveness.flux_app_name == flux_app_name,
                FdmIpLiveness.ip_address == ip,
            )
            .first()
        )

    def _get_or_create_row(self, flux_app_name: str, ip: str) -> FdmIpLiveness:
        row = self._query_row(flux_app_name, ip)
        if row is not None:
            return row
        # First-ever cycle for this (app, IP): two same-cycle deployments of a
        # shared-IP app each sync on their OWN SessionLocal (Phase 4.6), so both
        # can miss the SELECT above and then race the INSERT — the loser hits
        # uq_fdm_ip_liveness_app_ip. Wrap the insert in a SAVEPOINT so the
        # loser's failed INSERT rolls back on its own WITHOUT discarding the
        # rows this Pass has already materialized in the outer transaction, then
        # re-query the winner's now-committed row (PG READ COMMITTED: the fresh
        # SELECT after ROLLBACK TO SAVEPOINT sees it).
        try:
            with self.db.begin_nested():
                row = FdmIpLiveness(
                    flux_app_name=flux_app_name,
                    ip_address=ip,
                    consecutive_failures=0,
                )
                self.db.add(row)
                self.db.flush()
            return row
        except IntegrityError:
            row = self._query_row(flux_app_name, ip)
            if row is None:
                raise
            return row

    def _set_instances_active(self, ip: str, active: bool) -> None:
        (
            self.db.query(ProtocolInstance)
            .filter(ProtocolInstance.ip_address == ip)
            .update({ProtocolInstance.is_active: active}, synchronize_session=False)
        )

    async def _probe_many(
        self, ips: List[str], ports: List[int], timeout: float, concurrency: int
    ) -> dict:
        """Probe every IP's liveness CONCURRENTLY, bounded by a semaphore.

        Serial probing timed out the whole FDM sync in prod: a blackholed IP
        hangs the full per-port timeout, and an app can have dozens of them
        (ch01=27 IPs -> ~89s serial). Fanning the probes out turns per-app
        latency from N*timeout into ~ceil(N/concurrency)*timeout while the
        semaphore keeps the open-socket count bounded.
        """
        if not ips:
            return {}
        sem = asyncio.Semaphore(max(1, concurrency))

        async def one(ip: str) -> tuple:
            async with sem:
                return ip, await is_ip_live(ip, ports, timeout)

        results = await asyncio.gather(*(one(ip) for ip in ips))
        return dict(results)

    async def gate(self, flux_app_name: str, all_ips: List[str]) -> Set[str]:
        """Probe due IPs, update hysteresis, demote/restore ProtocolInstance,
        and return the actionable confirmed-dead set (post fail-safe) to
        exclude from target_ips."""
        if not all_ips:
            return set()

        ports = self._app_ports(flux_app_name)
        timeout = settings.FDM_LIVENESS_PORT_TIMEOUT
        min_interval = settings.FDM_LIVENESS_MIN_INTERVAL
        dead_cycles = settings.FDM_LIVENESS_DEAD_CYCLES
        concurrency = settings.FDM_LIVENESS_CONCURRENCY
        now = _now()

        confirmed_dead: Set[str] = set()
        rows: dict = {}
        due_ips: List[str] = []

        # Pass 1 (DB): materialize each row and collect the IPs due for a probe.
        for ip in all_ips:
            row = self._get_or_create_row(flux_app_name, ip)
            rows[ip] = row
            due = (
                row.last_checked_at is None
                or (now - row.last_checked_at).total_seconds() >= min_interval
            )
            if due:
                due_ips.append(ip)

        # Pass 2 (network): probe all due IPs at once, bounded — no DB in flight.
        liveness = await self._probe_many(due_ips, ports, timeout, concurrency)

        # Pass 3 (DB): apply probe results with the original per-IP hysteresis.
        for ip in due_ips:
            row = rows[ip]
            prev = row.consecutive_failures or 0
            live = liveness[ip]
            row.consecutive_failures = next_failure_count(prev, live)
            row.last_checked_at = now
            if live:
                row.last_live_at = now
                # Recovery: restore only what the gate itself demoted.
                if row.demoted_at is not None:
                    self._set_instances_active(ip, True)
                    row.demoted_at = None
            self.db.add(row)

        # Non-due IPs keep their persisted count; both contribute to the set.
        for ip in all_ips:
            new_count = rows[ip].consecutive_failures or 0
            if is_confirmed_dead(new_count, dead_cycles):
                confirmed_dead.add(ip)

        # Fail-safe scopes to a probe-side / worker-egress outage: it keys on the
        # CURRENT probe-failure fraction (IPs whose latest probe failed), read
        # from persisted per-IP state so every same-cycle deployment of a
        # shared-IP app reaches the same decision. An egress outage fails ~all
        # probes simultaneously -> fraction ~1.0 -> trips EVERY cycle of the
        # outage (not just the crossover), regardless of death synchronization;
        # a small steady fraction of genuine deaths stays below the threshold and
        # demotes normally.
        failing_count = sum(
            1 for ip in all_ips if (rows[ip].consecutive_failures or 0) > 0
        )
        tripped = failsafe_tripped(
            failing_count, len(all_ips), settings.FDM_LIVENESS_MAX_DEAD_FRACTION
        )
        actionable: Set[str] = set() if tripped else confirmed_dead
        if tripped:
            logger.warning(
                "Liveness fail-safe tripped for %s: %d/%d consensus IPs currently "
                "failing — probable probe-side egress outage, skipping demotion.",
                flux_app_name,
                failing_count,
                len(all_ips),
            )

        for ip in actionable:
            self._set_instances_active(ip, False)
            row = rows[ip]
            if row.demoted_at is None:
                row.demoted_at = now
            self.db.add(row)

        self.db.commit()
        return actionable
