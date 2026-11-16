"""DB-gated (VM): LivenessGate.gate() demotes a confirmed-dead IP and restores
a recovered one against a real Postgres. Run via scripts/_vm_test.py."""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.core.database import SessionLocal
from app.models.fdm_ip_liveness import FdmIpLiveness
from app.models.flux_app_registration import FluxAppRegistration
from app.models.ip_management import ProtocolInstance
from app.models.subscription import Protocol
from app.services.fdm.liveness import LivenessGate

APP = "livetest01"
DEAD_IP = "203.0.113.7"
PROTO_ID = 1


@pytest.fixture
def db(tables):
    # `tables` (conftest, session-scoped) runs Base.metadata.create_all so the
    # schema — including fdm_ip_liveness — exists. We use a real autocommit
    # SessionLocal (not conftest's rollback-per-test db_session) because gate()
    # commits and we re-query the committed state across cycles.
    s = SessionLocal()
    # Clean slate for this app/IP.
    s.query(FdmIpLiveness).filter(FdmIpLiveness.flux_app_name == APP).delete()
    s.query(ProtocolInstance).filter(ProtocolInstance.ip_address == DEAD_IP).delete()
    s.query(FluxAppRegistration).filter(FluxAppRegistration.app_name == APP).delete()
    s.commit()
    # ProtocolInstance.protocol_id is a NOT NULL FK -> protocols.id; the VM test
    # runs against a freshly create_all()'d empty schema, so seed a parent row.
    if s.get(Protocol, PROTO_ID) is None:
        s.add(Protocol(id=PROTO_ID, name="livetest-ssh", slug="livetest-ssh"))
        s.commit()
    s.add(FluxAppRegistration(app_name=APP, protocol_ports={"ssh": 12345}))
    # A minimal ProtocolInstance for the dead IP (is_active True to start).
    s.add(
        ProtocolInstance(
            protocol_id=1,
            flux_app_name=APP,
            instance_number=1,
            ip_address=DEAD_IP,
            country_code="XX",
            country_name="Test",
            is_active=True,
        )
    )
    s.commit()
    yield s
    s.query(FdmIpLiveness).filter(FdmIpLiveness.flux_app_name == APP).delete()
    s.query(ProtocolInstance).filter(ProtocolInstance.ip_address == DEAD_IP).delete()
    s.query(FluxAppRegistration).filter(FluxAppRegistration.app_name == APP).delete()
    s.query(Protocol).filter(Protocol.id == PROTO_ID).delete()
    s.commit()
    s.close()


def _run(coro):
    return asyncio.run(coro)


def test_gate_demotes_after_threshold_and_restores_on_recovery(db, monkeypatch):
    # Force N=2, min_interval=0 so each gate() call re-probes.
    from app.core.config import settings

    monkeypatch.setattr(settings, "FDM_LIVENESS_DEAD_CYCLES", 2)
    monkeypatch.setattr(settings, "FDM_LIVENESS_MIN_INTERVAL", 0.0)
    monkeypatch.setattr(settings, "FDM_LIVENESS_MAX_DEAD_FRACTION", 1.0)

    gate = LivenessGate(db)

    with patch(
        "app.services.fdm.liveness.is_ip_live", new=AsyncMock(return_value=False)
    ):
        # Cycle 1: failures -> 1, not yet dead.
        dead1 = _run(gate.gate(APP, [DEAD_IP]))
        assert dead1 == set()
        assert (
            db.query(ProtocolInstance)
            .filter(ProtocolInstance.ip_address == DEAD_IP)
            .first()
            .is_active
            is True
        )
        # Cycle 2: failures -> 2 == threshold, confirmed dead + demoted.
        dead2 = _run(gate.gate(APP, [DEAD_IP]))
        assert dead2 == {DEAD_IP}
        pi = (
            db.query(ProtocolInstance)
            .filter(ProtocolInstance.ip_address == DEAD_IP)
            .first()
        )
        assert pi.is_active is False
        row = (
            db.query(FdmIpLiveness)
            .filter(
                FdmIpLiveness.flux_app_name == APP,
                FdmIpLiveness.ip_address == DEAD_IP,
            )
            .first()
        )
        assert row.demoted_at is not None

    # Recovery: probe now live -> restore is_active, clear demoted_at.
    with patch(
        "app.services.fdm.liveness.is_ip_live", new=AsyncMock(return_value=True)
    ):
        dead3 = _run(gate.gate(APP, [DEAD_IP]))
        assert dead3 == set()
        pi = (
            db.query(ProtocolInstance)
            .filter(ProtocolInstance.ip_address == DEAD_IP)
            .first()
        )
        assert pi.is_active is True
        row = (
            db.query(FdmIpLiveness)
            .filter(
                FdmIpLiveness.flux_app_name == APP,
                FdmIpLiveness.ip_address == DEAD_IP,
            )
            .first()
        )
        assert row.demoted_at is None
        assert row.consecutive_failures == 0


def test_gate_failsafe_holds_serving_open_during_sustained_outage(db, monkeypatch):
    """Regression guard for the fail-safe merge-blocker: during a sustained
    egress outage (all of an app's IPs failing every cycle) the guard must trip
    on EVERY cycle — including cycles AFTER the IPs first cross the confirmed-dead
    threshold — so the fleet is never demoted. The old newly-confirmed logic
    tripped only on the crossover cycle then demoted everything the next cycle;
    running three all-dead cycles and asserting no demotion on any is what
    distinguishes the fixed behavior from that regression."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "FDM_LIVENESS_DEAD_CYCLES", 2)
    monkeypatch.setattr(settings, "FDM_LIVENESS_MIN_INTERVAL", 0.0)
    monkeypatch.setattr(settings, "FDM_LIVENESS_MAX_DEAD_FRACTION", 0.5)

    ips = ["203.0.113.10", "203.0.113.11", "203.0.113.12"]
    for idx, ip in enumerate(ips, start=2):
        db.add(
            ProtocolInstance(
                protocol_id=PROTO_ID,
                flux_app_name=APP,
                instance_number=idx,
                ip_address=ip,
                country_code="XX",
                country_name="Test",
                is_active=True,
            )
        )
    db.commit()

    gate = LivenessGate(db)
    try:
        with patch(
            "app.services.fdm.liveness.is_ip_live",
            new=AsyncMock(return_value=False),
        ):
            # 3/3 failing -> fraction 1.0 > 0.5 -> fail-safe trips EVERY cycle.
            # Cycle 3 is the discriminating one: by then all IPs are already
            # confirmed dead, so the old newly-confirmed guard would go empty and
            # demote the whole fleet.
            for cycle in range(3):
                actionable = _run(gate.gate(APP, ips))
                assert actionable == set(), f"cycle {cycle}: expected no demotion"
                actives = [
                    pi.is_active
                    for pi in db.query(ProtocolInstance)
                    .filter(ProtocolInstance.ip_address.in_(ips))
                    .all()
                ]
                assert all(actives), f"cycle {cycle}: an IP was wrongly demoted"
    finally:
        db.query(ProtocolInstance).filter(ProtocolInstance.flux_app_name == APP).delete(
            synchronize_session=False
        )
        db.query(FdmIpLiveness).filter(FdmIpLiveness.flux_app_name == APP).delete()
        db.commit()
