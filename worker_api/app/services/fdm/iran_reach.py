"""FDM Iran reachability: stop serving node IPs that Iran blocks.

FDM's liveness gate (liveness.py) probes from the prod VM in Dallas, so it
can't see Iranian filtering: a node can be fully alive yet unreachable from
every Iranian ISP (ch01/DE 168.119.128.24, 2026-10-24). This module asks
check-host.net's Iranian probe nodes instead, plus a non-Iranian control node
so a dead node is never mistaken for a blocked one.

Split in two so the FDM sync never waits on check-host:
- IranReachChecker (Celery beat task fdm.check_iran_reachability) collects the
  results of the checks it submitted on its previous run, then submits a small,
  rate-limited batch of new ones. State lives in fdm_ip_iran_reach.
- iran_blocked_ips() is the read side FdmSyncService uses to drop confirmed
  Iran-blocked IPs from a deployment's target_ips.

Every uncertain outcome (HTTP error, rate limit, pending/expired result, control
node failing, too few Iranian answers) is INCONCLUSIVE and changes nothing.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.fdm_ip_iran_reach import FdmIpIranReach
from app.models.fdm_ip_liveness import FdmIpLiveness
from app.models.flux_app_registration import FluxAppRegistration

logger = logging.getLogger(__name__)

BLOCKED = "blocked"
REACHABLE = "reachable"
INCONCLUSIVE = "inconclusive"

CHECK_HOST_BASE = "https://check-host.net"
NODE_SUFFIX = ".node.check-host.net"
# check-host.net answers Python's default User-Agent with HTTP 403.
_HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
}
_PORT_PREFERENCE = ("vless", "trojan")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def node_host(node: str) -> str:
    """'ir1' -> 'ir1.node.check-host.net' (full names pass through)."""
    return node if node.endswith(NODE_SUFFIX) else f"{node}{NODE_SUFFIX}"


def _tcp_ok(value: Any) -> Optional[bool]:
    """One node's check-tcp result: True connected, False failed, None unknown.

    check-host returns null while a node is still running the check,
    [{"address": ip, "time": secs}] on success and [{"error": "..."}] on
    failure. Anything else is treated as unknown, never as a failure.
    """
    if isinstance(value, list) and value:
        value = value[0]
    if isinstance(value, dict):
        if "address" in value:
            return True
        if "error" in value:
            return False
    return None


def classify(
    result: Optional[Mapping[str, Any]],
    iran_nodes: List[str],
    control_node: str,
    min_nodes: int,
) -> str:
    """Verdict for one check-tcp result.

    BLOCKED only when the control node connected AND at least min_nodes
    Iranian nodes answered AND a strict majority of those answers failed.
    REACHABLE when a strict majority of the Iranian answers connected.
    Everything else is INCONCLUSIVE.
    """
    if not isinstance(result, Mapping):
        return INCONCLUSIVE
    answers = [_tcp_ok(result.get(node_host(n))) for n in iran_nodes]
    known = [a for a in answers if a is not None]
    ok = sum(1 for a in known if a)
    failed = len(known) - ok
    if known and ok * 2 > len(known):
        return REACHABLE
    if _tcp_ok(result.get(node_host(control_node))) is not True:
        return INCONCLUSIVE
    if len(known) >= min_nodes and failed * 2 > len(known):
        return BLOCKED
    return INCONCLUSIVE


def next_blocked_streak(prev: Optional[int], verdict: str) -> int:
    """Consecutive BLOCKED verdicts. REACHABLE resets; INCONCLUSIVE holds."""
    prev = prev or 0
    if verdict == BLOCKED:
        return prev + 1
    if verdict == REACHABLE:
        return 0
    return prev


def is_iran_blocked(streak: int, blocked_checks: int) -> bool:
    return streak >= blocked_checks


def pick_check_port(protocol_ports: Optional[Mapping[str, Any]]) -> Optional[int]:
    """The TCP port to test an app's IPs on: VLESS, else Trojan, else any.

    Iran filters these nodes by IP, so one port is enough to see a block.
    """
    if not protocol_ports:
        return None
    keys = [k for k in _PORT_PREFERENCE if k in protocol_ports]
    keys += [k for k in protocol_ports if k not in _PORT_PREFERENCE]
    for key in keys:
        try:
            return int(protocol_ports[key])
        except (TypeError, ValueError):
            continue
    return None


def _summary(
    result: Optional[Mapping[str, Any]], iran_nodes: List[str], control: str
) -> str:
    """Compact per-node record for logs/DB, e.g. 'ir1:x ir2:+ ... de1:+'."""
    marks = {True: "+", False: "x", None: "?"}
    res = result if isinstance(result, Mapping) else {}
    parts = [
        f"{n}:{marks[_tcp_ok(res.get(node_host(n)))]}" for n in iran_nodes + [control]
    ]
    return " ".join(parts)[:255]


def _has_unanswered(result: Optional[Mapping[str, Any]], nodes: List[str]) -> bool:
    if not isinstance(result, Mapping):
        return True
    return any(result.get(node_host(n)) is None for n in nodes)


def _node_list(raw: str) -> List[str]:
    return [n.strip() for n in (raw or "").split(",") if n.strip()]


class CheckHostClient:
    """Minimal check-host.net client. Every failure returns None (fail-open)."""

    def __init__(
        self,
        timeout: Optional[float] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self._timeout = timeout or settings.FDM_IRAN_REACH_HTTP_TIMEOUT
        self._transport = transport  # tests inject httpx.MockTransport

    async def _get(self, path: str, params: Any = None) -> Optional[Dict[str, Any]]:
        try:
            async with httpx.AsyncClient(
                base_url=CHECK_HOST_BASE,
                headers=_HEADERS,
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                resp = await client.get(path, params=params)
            if resp.status_code != 200:
                logger.warning("check-host %s returned HTTP %s", path, resp.status_code)
                return None
            data = resp.json()
            return data if isinstance(data, dict) else None
        except Exception as e:  # network, timeout, bad JSON
            logger.warning("check-host %s failed: %s", path, e)
            return None

    async def submit_tcp(self, target: str, nodes: List[str]) -> Optional[str]:
        params = [("host", target)] + [("node", n) for n in nodes]
        data = await self._get("/check-tcp", params=params)
        rid = data.get("request_id") if data else None
        return str(rid) if rid else None

    async def fetch_result(self, request_id: str) -> Optional[Dict[str, Any]]:
        return await self._get(f"/check-result/{request_id}")


class IranReachChecker:
    """One run of the fdm.check_iran_reachability task.

    1. Collect: fetch results for checks submitted on earlier runs and apply
       them to the per-IP hysteresis.
    2. Submit: start new checks for at most FDM_IRAN_REACH_MAX_CHECKS_PER_RUN
       due IPs (never checked first, then suspects, then the oldest).

    Never sleeps waiting for check-host: results are collected a run later.
    """

    def __init__(self, db: Session, client: Optional[Any] = None):
        self.db = db
        self.client = client or CheckHostClient()
        self.iran_nodes = _node_list(settings.FDM_IRAN_REACH_NODES)
        self.control = settings.FDM_IRAN_REACH_CONTROL_NODE.strip()

    def _candidates(self, now: datetime) -> List[Tuple[str, str, int]]:
        """(app, ip, port) for every IP the liveness gate currently serves:
        probed within the candidate window and not demoted as dead."""
        since = now - timedelta(seconds=settings.FDM_IRAN_REACH_CANDIDATE_WINDOW)
        rows = (
            self.db.query(FdmIpLiveness)
            .filter(
                FdmIpLiveness.last_checked_at >= since,
                FdmIpLiveness.demoted_at.is_(None),
            )
            .all()
        )
        ports: Dict[str, Optional[int]] = {}
        out: List[Tuple[str, str, int]] = []
        for row in rows:
            app = row.flux_app_name
            if app not in ports:
                reg = (
                    self.db.query(FluxAppRegistration)
                    .filter(FluxAppRegistration.app_name == app)
                    .first()
                )
                ports[app] = pick_check_port(reg.protocol_ports if reg else None)
            port = ports[app]
            if port is not None:
                out.append((app, str(row.ip_address), port))
        return out

    def _query_row(self, app: str, ip: str) -> Optional[FdmIpIranReach]:
        return (
            self.db.query(FdmIpIranReach)
            .filter(
                FdmIpIranReach.flux_app_name == app,
                FdmIpIranReach.ip_address == ip,
            )
            .first()
        )

    def _get_or_create(self, app: str, ip: str) -> FdmIpIranReach:
        row = self._query_row(app, ip)
        if row is not None:
            return row
        try:
            with self.db.begin_nested():
                row = FdmIpIranReach(flux_app_name=app, ip_address=ip, blocked_streak=0)
                self.db.add(row)
                self.db.flush()
            return row
        except IntegrityError:  # an overlapping run inserted it first
            row = self._query_row(app, ip)
            if row is None:
                raise
            return row

    async def _collect(self, now: datetime) -> Dict[str, List[str]]:
        changes: Dict[str, List[str]] = {"blocked": [], "restored": []}
        pending = (
            self.db.query(FdmIpIranReach)
            .filter(FdmIpIranReach.pending_request_id.isnot(None))
            .all()
        )
        nodes = self.iran_nodes + [self.control]
        for row in pending:
            age = (now - row.submitted_at).total_seconds() if row.submitted_at else 1e9
            if age < settings.FDM_IRAN_REACH_RESULT_DELAY:
                continue
            result = await self.client.fetch_result(str(row.pending_request_id))
            verdict = classify(
                result,
                self.iran_nodes,
                self.control,
                settings.FDM_IRAN_REACH_MIN_NODES,
            )
            if (
                verdict == INCONCLUSIVE
                and _has_unanswered(result, nodes)
                and age < settings.FDM_IRAN_REACH_RESULT_TTL
            ):
                continue  # still running, or a transient fetch error: next run
            summary = _summary(result, self.iran_nodes, self.control)
            self._apply(row, verdict, summary, now, changes)
        return changes

    def _apply(
        self,
        row: FdmIpIranReach,
        verdict: str,
        summary: str,
        now: datetime,
        changes: Dict[str, List[str]],
    ) -> None:
        ip = str(row.ip_address)
        row.pending_request_id = None
        row.last_verdict = verdict
        row.last_summary = summary
        row.blocked_streak = next_blocked_streak(row.blocked_streak, verdict)
        if verdict != INCONCLUSIVE:
            row.checked_at = now
        if (
            verdict == BLOCKED
            and row.blocked_at is None
            and is_iran_blocked(
                row.blocked_streak, settings.FDM_IRAN_REACH_BLOCKED_CHECKS
            )
        ):
            row.blocked_at = now
            changes["blocked"].append(ip)
            logger.warning(
                "Iran reachability: %s/%s BLOCKED from Iran (%s), excluding from FDM",
                row.flux_app_name,
                ip,
                summary,
            )
        elif verdict == REACHABLE and row.blocked_at is not None:
            row.blocked_at = None
            changes["restored"].append(ip)
            logger.info(
                "Iran reachability: %s/%s reachable from Iran again (%s), restoring",
                row.flux_app_name,
                ip,
                summary,
            )
        else:
            logger.info(
                "Iran reachability: %s/%s %s (streak %d, %s)",
                row.flux_app_name,
                ip,
                verdict,
                row.blocked_streak,
                summary,
            )
        self.db.add(row)

    def _is_due(self, row: FdmIpIranReach, now: datetime) -> bool:
        if row.pending_request_id is not None:
            return False
        if row.submitted_at is None:
            return True
        interval = (
            settings.FDM_IRAN_REACH_SUSPECT_INTERVAL
            if (row.blocked_streak or 0) > 0
            else settings.FDM_IRAN_REACH_INTERVAL
        )
        return (now - row.submitted_at).total_seconds() >= interval

    async def _submit(self, now: datetime) -> List[str]:
        due: List[Tuple[FdmIpIranReach, str, int]] = []
        for app, ip, port in self._candidates(now):
            row = self._get_or_create(app, ip)
            if self._is_due(row, now):
                due.append((row, ip, port))
        # Never-checked first, then suspects (re-confirm quickly), then oldest.
        due.sort(
            key=lambda d: (
                d[0].submitted_at is not None,
                (d[0].blocked_streak or 0) == 0,
                d[0].submitted_at or now,
            )
        )
        nodes = [node_host(n) for n in self.iran_nodes + [self.control]]
        submitted: List[str] = []
        limit = max(0, settings.FDM_IRAN_REACH_MAX_CHECKS_PER_RUN)
        for row, ip, port in due[:limit]:
            target = f"{ip}:{port}"
            rid = await self.client.submit_tcp(target, nodes)
            if not rid:
                # Rate-limited or down: be polite and try again next run.
                logger.warning(
                    "Iran reachability: check-host refused %s, stopping this run",
                    target,
                )
                break
            row.pending_request_id = rid
            row.submitted_at = now
            row.port = port
            self.db.add(row)
            submitted.append(target)
        return submitted

    async def run(self) -> Dict[str, Any]:
        now = _now()
        changes = await self._collect(now)
        self.db.commit()
        submitted = await self._submit(now)
        self.db.commit()
        return {"submitted": submitted, **changes}


def iran_blocked_ips(db: Session, flux_app_name: str, ips: List[str]) -> Set[str]:
    """The IPs among ips that are confirmed blocked from Iran for this app.

    A block not re-confirmed within FDM_IRAN_REACH_STALE_AFTER is ignored, so
    a stalled checker (check-host down, task not running) fails open instead
    of excluding IPs forever.
    """
    if not ips:
        return set()
    fresh_since = _now() - timedelta(seconds=settings.FDM_IRAN_REACH_STALE_AFTER)
    rows = (
        db.query(FdmIpIranReach.ip_address)
        .filter(
            FdmIpIranReach.flux_app_name == flux_app_name,
            FdmIpIranReach.blocked_at.isnot(None),
            FdmIpIranReach.checked_at >= fresh_since,
        )
        .all()
    )
    wanted = set(ips)
    return {str(r[0]) for r in rows if str(r[0]) in wanted}
