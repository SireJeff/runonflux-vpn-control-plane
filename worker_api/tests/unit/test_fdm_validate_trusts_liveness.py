"""_validate_domain_ips_against_instances must not mark a live IP's domains
stale just because its protocol_instances row is inactive.

flux.check_all_instances_health (0/59 healthy on prod, 2026-10-24) keeps
deactivating live IPs' PI rows, and FDM re-creates them seconds later. Once
validate could commit (SAVEPOINT fix), it marked those live IPs' domains
unhealthy in between, queueing them for deletion. FDM's own liveness gate
(fdm_ip_liveness: probed this cycle, not demoted) is the reliable signal
that an IP is still in Flux consensus."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.core.database import SessionLocal
from app.models.fdm import FdmDeployment, FdmDomain
from app.models.fdm_ip_liveness import FdmIpLiveness
from app.models.ip_management import ProtocolInstance
from app.models.subscription import Protocol
from app.services.fdm.fdm_sync_service import FdmSyncService

APP = "vltest01"
OTHER_APP = "vltest02"
IP = "198.51.100.77"
PROTO_ID = 1


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.fixture
def db(tables):
    s = SessionLocal()

    def clean():
        ids = [
            d.id
            for d in s.query(FdmDeployment).filter(FdmDeployment.flux_app_name == APP)
        ]
        if ids:
            s.query(FdmDomain).filter(FdmDomain.deployment_id.in_(ids)).delete(
                synchronize_session=False
            )
        s.query(FdmDeployment).filter(FdmDeployment.flux_app_name == APP).delete()
        s.query(ProtocolInstance).filter(ProtocolInstance.flux_app_name == APP).delete()
        s.query(FdmIpLiveness).filter(
            FdmIpLiveness.flux_app_name.in_([APP, OTHER_APP])
        ).delete(synchronize_session=False)
        s.commit()

    clean()
    if s.get(Protocol, PROTO_ID) is None:
        s.add(Protocol(id=PROTO_ID, name="vltest-ssh", slug="vltest-ssh"))
        s.commit()
    dep = FdmDeployment(flux_app_name=APP, region="DE", base_domain="vl.test")
    s.add(dep)
    s.flush()
    # The PI row exists but the broken health monitor has deactivated it.
    s.add(
        ProtocolInstance(
            protocol_id=PROTO_ID,
            flux_app_name=APP,
            component_name="multi-protocol",
            instance_number=1,
            ip_address=IP,
            country_code="DE",
            country_name="Germany",
            is_active=False,
        )
    )
    s.add(
        FdmDomain(
            deployment_id=dep.id,
            domain_name="vl0.vl.test",
            domain_id="vl0",
            current_ip=IP,
            health_status="healthy",
        )
    )
    s.commit()
    yield s
    s.rollback()
    clean()
    s.close()


def _liveness(db, checked_ago, demoted=False, app=APP):
    db.add(
        FdmIpLiveness(
            flux_app_name=app,
            ip_address=IP,
            consecutive_failures=0,
            last_checked_at=_now() - checked_ago,
            demoted_at=_now() if demoted else None,
        )
    )
    db.commit()


def _validate_and_status(db):
    marked = asyncio.run(FdmSyncService(db)._validate_domain_ips_against_instances())
    db.expire_all()
    status = db.query(FdmDomain).filter(FdmDomain.domain_name == "vl0.vl.test").one()
    return marked, status.health_status


def test_ip_the_liveness_gate_just_probed_stays_healthy(db):
    _liveness(db, checked_ago=timedelta(minutes=5))
    assert _validate_and_status(db) == (0, "healthy")


def test_ip_unknown_to_the_liveness_gate_is_marked_stale(db):
    assert _validate_and_status(db) == (1, "unhealthy")


def test_ip_the_liveness_gate_stopped_probing_is_marked_stale(db):
    # Left Flux consensus: FDM hasn't probed it for 2 hours.
    _liveness(db, checked_ago=timedelta(hours=2))
    assert _validate_and_status(db) == (1, "unhealthy")


def test_ip_the_liveness_gate_demoted_is_marked_stale(db):
    _liveness(db, checked_ago=timedelta(minutes=5), demoted=True)
    assert _validate_and_status(db) == (1, "unhealthy")


@pytest.mark.parametrize("own_state", ["unknown", "expired", "demoted"])
def test_other_apps_live_ip_does_not_hide_a_stale_endpoint(db, own_state):
    # Flux apps can share a host but use different ports. A recent probe of
    # another app cannot establish that this app still serves on the host.
    if own_state == "expired":
        _liveness(db, checked_ago=timedelta(hours=2))
    elif own_state == "demoted":
        _liveness(db, checked_ago=timedelta(minutes=5), demoted=True)
    _liveness(db, checked_ago=timedelta(minutes=5), app=OTHER_APP)

    assert _validate_and_status(db) == (1, "unhealthy")


def test_other_apps_demotion_does_not_override_this_apps_live_ip(db):
    _liveness(db, checked_ago=timedelta(minutes=5))
    _liveness(db, checked_ago=timedelta(minutes=5), demoted=True, app=OTHER_APP)

    assert _validate_and_status(db) == (0, "healthy")
