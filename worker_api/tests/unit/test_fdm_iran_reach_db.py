"""DB-backed tests for IranReachChecker (the fdm.check_iran_reachability task
body) and the iran_blocked_ips() read side. check-host.net is replaced by an
in-memory fake client; Postgres is real (INET columns, commits across runs)."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.fdm_ip_iran_reach import FdmIpIranReach
from app.models.fdm_ip_liveness import FdmIpLiveness
from app.models.flux_app_registration import FluxAppRegistration
from app.services.fdm.iran_reach import IranReachChecker, iran_blocked_ips

APP = "irantest01"
IP_A = "203.0.113.10"
IP_B = "203.0.113.11"
VLESS = 30519
IR = ["ir1", "ir2", "ir3", "ir4", "ir5", "ir7"]
OK = [{"address": "x", "time": 0.1}]
TIMEOUT = [{"error": "Connection timed out"}]


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _res(ir_value, ctrl_value=OK):
    out = {f"{n}.node.check-host.net": ir_value for n in IR}
    out["de1.node.check-host.net"] = ctrl_value
    return out


BLOCKED_RES = _res(TIMEOUT)
REACHABLE_RES = _res(OK)
PENDING_RES = _res(None, None)


class FakeCheckHost:
    """Records submits; answers each target with the result set for it."""

    def __init__(self):
        self.submits = []  # (target, nodes)
        self.results = {}  # target -> result dict (None = fetch error)
        self.fail_submit = False
        self._by_id = {}

    async def submit_tcp(self, target, nodes):
        self.submits.append((target, list(nodes)))
        if self.fail_submit:
            return None
        rid = f"req{len(self.submits)}"
        self._by_id[rid] = target
        return rid

    async def fetch_result(self, request_id):
        return self.results.get(self._by_id.get(request_id))


@pytest.fixture
def db(tables, monkeypatch):
    for name, value in {
        "FDM_IRAN_REACH_NODES": ",".join(IR),
        "FDM_IRAN_REACH_CONTROL_NODE": "de1",
        "FDM_IRAN_REACH_MIN_NODES": 4,
        "FDM_IRAN_REACH_BLOCKED_CHECKS": 2,
        "FDM_IRAN_REACH_INTERVAL": 3600.0,
        "FDM_IRAN_REACH_SUSPECT_INTERVAL": 0.0,
        "FDM_IRAN_REACH_MAX_CHECKS_PER_RUN": 6,
        "FDM_IRAN_REACH_RESULT_DELAY": 0.0,
        "FDM_IRAN_REACH_RESULT_TTL": 1800.0,
        "FDM_IRAN_REACH_STALE_AFTER": 21600.0,
        "FDM_IRAN_REACH_CANDIDATE_WINDOW": 3600.0,
    }.items():
        monkeypatch.setattr(settings, name, value)
    s = SessionLocal()

    def clean():
        s.query(FdmIpIranReach).filter(FdmIpIranReach.flux_app_name == APP).delete()
        s.query(FdmIpLiveness).filter(FdmIpLiveness.flux_app_name == APP).delete()
        s.query(FluxAppRegistration).filter(
            FluxAppRegistration.app_name == APP
        ).delete()
        s.commit()

    clean()
    s.add(FluxAppRegistration(app_name=APP, protocol_ports={"ss": 1, "vless": VLESS}))
    s.commit()
    yield s
    clean()
    s.close()


def _liveness(db, ip, checked_ago=timedelta(minutes=5), demoted=False):
    db.add(
        FdmIpLiveness(
            flux_app_name=APP,
            ip_address=ip,
            consecutive_failures=0,
            last_checked_at=_now() - checked_ago,
            demoted_at=_now() if demoted else None,
        )
    )
    db.commit()


def _row(db, ip):
    db.expire_all()
    return (
        db.query(FdmIpIranReach)
        .filter(FdmIpIranReach.flux_app_name == APP, FdmIpIranReach.ip_address == ip)
        .one_or_none()
    )


def _run(db, client):
    return asyncio.run(IranReachChecker(db, client).run())


def test_submits_current_ips_on_the_apps_vless_port(db):
    _liveness(db, IP_A)
    _liveness(db, IP_B)
    _liveness(db, "203.0.113.12", checked_ago=timedelta(hours=3))  # no longer seen
    _liveness(db, "203.0.113.13", demoted=True)  # dead from Dallas already
    client = FakeCheckHost()

    _run(db, client)

    targets = sorted(t for t, _ in client.submits)
    assert targets == [f"{IP_A}:{VLESS}", f"{IP_B}:{VLESS}"]
    nodes = client.submits[0][1]
    assert nodes == [f"{n}.node.check-host.net" for n in IR] + [
        "de1.node.check-host.net"
    ]
    assert _row(db, IP_A).pending_request_id is not None
    assert _row(db, IP_A).port == VLESS


def test_blocked_after_two_verdicts_and_restored_by_one_reachable(db):
    _liveness(db, IP_A)
    client = FakeCheckHost()
    client.results[f"{IP_A}:{VLESS}"] = BLOCKED_RES

    _run(db, client)  # submit
    _run(db, client)  # collect BLOCKED #1 (suspect), resubmit
    row = _row(db, IP_A)
    assert row.blocked_streak == 1
    assert row.blocked_at is None
    assert iran_blocked_ips(db, APP, [IP_A]) == set()

    _run(db, client)  # collect BLOCKED #2 -> excluded
    row = _row(db, IP_A)
    assert row.blocked_streak == 2
    assert row.blocked_at is not None
    assert row.last_verdict == "blocked"
    assert iran_blocked_ips(db, APP, [IP_A, IP_B]) == {IP_A}

    client.results[f"{IP_A}:{VLESS}"] = REACHABLE_RES
    _run(db, client)  # collect REACHABLE -> restored
    row = _row(db, IP_A)
    assert row.blocked_streak == 0
    assert row.blocked_at is None
    assert iran_blocked_ips(db, APP, [IP_A]) == set()


def test_reachable_ip_is_not_rechecked_before_the_interval(db):
    _liveness(db, IP_A)
    client = FakeCheckHost()
    client.results[f"{IP_A}:{VLESS}"] = REACHABLE_RES

    _run(db, client)  # submit
    _run(db, client)  # collect REACHABLE; not due again for an hour
    _run(db, client)

    assert len(client.submits) == 1
    assert _row(db, IP_A).last_verdict == "reachable"


def test_pending_result_stays_pending_without_changing_state(db):
    _liveness(db, IP_A)
    client = FakeCheckHost()
    client.results[f"{IP_A}:{VLESS}"] = PENDING_RES

    _run(db, client)
    _run(db, client)

    row = _row(db, IP_A)
    assert row.pending_request_id == "req1"  # kept for the next run
    assert row.blocked_streak == 0
    assert row.checked_at is None
    assert len(client.submits) == 1


def test_fetch_error_keeps_pending_then_expires_without_a_verdict(db, monkeypatch):
    _liveness(db, IP_A)
    client = FakeCheckHost()
    client.results[f"{IP_A}:{VLESS}"] = None  # every fetch fails

    _run(db, client)
    _run(db, client)
    assert _row(db, IP_A).pending_request_id == "req1"

    monkeypatch.setattr(settings, "FDM_IRAN_REACH_RESULT_TTL", 0.0)
    _run(db, client)
    row = _row(db, IP_A)
    assert row.blocked_streak == 0
    assert row.blocked_at is None
    assert row.checked_at is None
    assert row.last_verdict == "inconclusive"


def test_inconclusive_verdict_does_not_reset_a_suspect_streak(db):
    _liveness(db, IP_A)
    client = FakeCheckHost()
    client.results[f"{IP_A}:{VLESS}"] = BLOCKED_RES
    _run(db, client)
    _run(db, client)  # streak 1
    client.results[f"{IP_A}:{VLESS}"] = _res(TIMEOUT, TIMEOUT)  # control down too
    _run(db, client)
    row = _row(db, IP_A)
    assert row.blocked_streak == 1
    assert row.last_verdict == "inconclusive"


def test_submit_failure_stops_the_batch(db):
    _liveness(db, IP_A)
    _liveness(db, IP_B)
    client = FakeCheckHost()
    client.fail_submit = True

    _run(db, client)

    assert len(client.submits) == 1  # backs off after the first refusal
    assert _row(db, IP_A) is None or _row(db, IP_A).pending_request_id is None


def test_max_checks_per_run_limits_submissions(db, monkeypatch):
    monkeypatch.setattr(settings, "FDM_IRAN_REACH_MAX_CHECKS_PER_RUN", 1)
    _liveness(db, IP_A)
    _liveness(db, IP_B)
    client = FakeCheckHost()

    _run(db, client)
    assert len(client.submits) == 1
    _run(db, client)
    assert sorted(t for t, _ in client.submits) == [
        f"{IP_A}:{VLESS}",
        f"{IP_B}:{VLESS}",
    ]


def test_app_without_known_ports_is_skipped(db):
    db.query(FluxAppRegistration).filter(FluxAppRegistration.app_name == APP).delete()
    db.commit()
    _liveness(db, IP_A)
    client = FakeCheckHost()

    _run(db, client)

    assert client.submits == []


def test_block_not_reconfirmed_recently_is_ignored(db):
    db.add(
        FdmIpIranReach(
            flux_app_name=APP,
            ip_address=IP_A,
            blocked_streak=2,
            blocked_at=_now() - timedelta(hours=8),
            checked_at=_now() - timedelta(hours=7),
        )
    )
    db.commit()
    assert iran_blocked_ips(db, APP, [IP_A]) == set()


def test_sync_filter_drops_a_blocked_ip_against_real_postgres(db, monkeypatch):
    from types import SimpleNamespace

    from app.services.fdm.fdm_sync_service import FdmSyncService

    monkeypatch.setattr(settings, "FDM_IRAN_REACH_ENABLED", True)
    monkeypatch.setattr(settings, "FDM_IRAN_REACH_MAX_BLOCKED_FRACTION", 0.5)
    db.add(
        FdmIpIranReach(
            flux_app_name=APP,
            ip_address=IP_A,
            blocked_streak=2,
            blocked_at=_now(),
            checked_at=_now(),
        )
    )
    db.commit()
    svc = FdmSyncService.__new__(FdmSyncService)
    svc.db = db
    dep = SimpleNamespace(flux_app_name=APP, region="DE")
    all_ips = [IP_A, IP_B, "203.0.113.12"]

    out = svc._apply_iran_reach_filter(dep, all_ips, [IP_A, IP_B])

    assert out == [IP_B]
    db.commit()  # the SAVEPOINT left the session usable
