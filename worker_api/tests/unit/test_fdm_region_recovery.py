"""Region discovery must honor endpoint demotion and keep recovery reachable."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.fdm import FdmDeployment
from app.models.fdm_ip_liveness import FdmIpLiveness
from app.models.flux_app_registration import FluxAppRegistration
from app.services.fdm.fdm_sync_service import FdmSyncService, _DiscoveryResult

APP = "region-recovery-test"
LIVE_IP = "198.51.100.1"
DEAD_IP = "198.51.100.2"


@pytest.fixture
def db(tables):
    with SessionLocal() as session:
        yield session
        session.rollback()
        session.query(FdmDeployment).delete()
        session.query(FdmIpLiveness).delete()
        session.query(FluxAppRegistration).delete()
        session.commit()


@pytest.fixture
def svc(db, monkeypatch):
    monkeypatch.setattr(settings, "FDM_LIVENESS_ENABLED", True)
    monkeypatch.setattr(settings, "FDM_LIVENESS_MIN_INTERVAL", 0.0)
    monkeypatch.setattr(settings, "FDM_LIVENESS_DEAD_CYCLES", 3)
    monkeypatch.setattr(settings, "FDM_LIVENESS_MAX_DEAD_FRACTION", 0.5)
    service = FdmSyncService(db)
    service._spec_expected = {APP: 6}
    monkeypatch.setattr(
        service,
        "_get_cached_instances",
        AsyncMock(return_value=_DiscoveryResult([LIVE_IP, DEAD_IP], [], True, None)),
    )
    monkeypatch.setattr(
        service,
        "_resolve_ip_region",
        AsyncMock(side_effect=lambda ip: "JP" if ip == LIVE_IP else "SG"),
    )
    monkeypatch.setattr(
        "app.services.fdm.liveness.is_ip_live",
        AsyncMock(side_effect=lambda ip, ports, timeout: ip == LIVE_IP),
    )
    return service


def _seed(db, *, sibling=True, active=False, enabled=True, region="SG"):
    db.add(
        FluxAppRegistration(
            app_name=APP, protocol_ports={"ssh": 12345}, is_active=enabled
        )
    )
    if sibling:
        db.add(FdmDeployment(flux_app_name=APP, region="JP", is_active=True))
    dep = FdmDeployment(
        flux_app_name=APP,
        region=region,
        is_active=active,
        consecutive_failures=3,
        base_domain="recovery.test",
    )
    db.add(dep)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(
        FdmIpLiveness(
            flux_app_name=APP,
            ip_address=DEAD_IP,
            consecutive_failures=10,
            last_checked_at=now - timedelta(minutes=10),
            demoted_at=now - timedelta(hours=1),
        )
    )
    db.commit()
    return dep


def test_allocated_dead_region_stays_inactive_and_pool_target_stays_stable(db, svc):
    dep = _seed(db)
    jp = db.query(FdmDeployment).filter_by(region="JP").one()
    for _ in range(3):
        asyncio.run(svc._detect_new_countries())
        db.refresh(dep)
        assert dep.is_active is False
        assert dep.consecutive_failures == 3
        assert svc._spec_pool_target(jp, 1) == 6


@pytest.mark.parametrize("sibling", [False, True])
def test_recovered_endpoint_reactivates_even_when_no_regions_are_active(
    db, svc, monkeypatch, sibling
):
    dep = _seed(db, sibling=sibling)
    monkeypatch.setattr(
        "app.services.fdm.liveness.is_ip_live", AsyncMock(return_value=True)
    )
    asyncio.run(svc._detect_new_countries())
    asyncio.run(svc._auto_deactivate_phantom_deployments())
    db.refresh(dep)
    assert dep.is_active is True
    assert dep.consecutive_failures == 0
    assert (
        db.query(FdmIpLiveness).filter_by(ip_address=DEAD_IP).one().demoted_at is None
    )


def test_recovery_at_phantom_threshold_preserves_active_region(db, svc, monkeypatch):
    dep = _seed(db, active=True)
    monkeypatch.setattr(
        "app.services.fdm.liveness.is_ip_live", AsyncMock(return_value=True)
    )
    asyncio.run(svc._detect_new_countries())
    asyncio.run(svc._auto_deactivate_phantom_deployments())
    db.refresh(dep)
    assert dep.is_active is True
    assert dep.consecutive_failures == 0


def test_all_dead_failsafe_does_not_revive_a_previously_demoted_region(
    db, svc, monkeypatch
):
    dep = _seed(db)
    monkeypatch.setattr(
        "app.services.fdm.liveness.is_ip_live", AsyncMock(return_value=False)
    )
    asyncio.run(svc._detect_new_countries())
    db.refresh(dep)
    assert dep.is_active is False
    assert dep.consecutive_failures == 3
    assert db.query(FdmDeployment).filter_by(region="JP").one().is_active is True


def test_probe_error_preserves_existing_region_state(db, svc, monkeypatch):
    dep = _seed(db)
    monkeypatch.setattr(
        "app.services.fdm.liveness.is_ip_live",
        AsyncMock(side_effect=RuntimeError("probe unavailable")),
    )
    asyncio.run(svc._detect_new_countries())
    db.refresh(dep)
    assert dep.is_active is False
    assert dep.consecutive_failures == 3
    assert db.query(FdmDeployment).filter_by(region="JP").one().is_active is True


def test_disabled_app_is_not_reactivated_or_probed(db, svc, monkeypatch):
    dep = _seed(db, enabled=False)
    probe = AsyncMock(return_value=True)
    monkeypatch.setattr("app.services.fdm.liveness.is_ip_live", probe)
    asyncio.run(svc._detect_new_countries())
    db.refresh(dep)
    assert dep.is_active is False
    assert probe.await_count == 0


def test_discovery_failure_keeps_inactive_region_unchanged(db, svc, monkeypatch):
    dep = _seed(db)
    monkeypatch.setattr(
        svc,
        "_get_cached_instances",
        AsyncMock(return_value=_DiscoveryResult([], [], False, "unavailable")),
    )
    asyncio.run(svc._detect_new_countries())
    db.refresh(dep)
    assert dep.is_active is False
    assert dep.consecutive_failures == 3


def test_unregistered_app_is_not_reactivated(db, svc):
    dep = _seed(db)
    db.query(FluxAppRegistration).delete()
    db.commit()
    asyncio.run(svc._detect_new_countries())
    db.refresh(dep)
    assert dep.is_active is False


def test_another_apps_demotion_does_not_block_recovery(db, svc, monkeypatch):
    dep = _seed(db)
    db.add(
        FdmIpLiveness(
            flux_app_name="another-app",
            ip_address=DEAD_IP,
            consecutive_failures=20,
            demoted_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
    )
    db.commit()
    monkeypatch.setattr(
        "app.services.fdm.liveness.is_ip_live", AsyncMock(return_value=True)
    )
    asyncio.run(svc._detect_new_countries())
    db.refresh(dep)
    assert dep.is_active is True
    assert (
        db.query(FdmIpLiveness).filter_by(flux_app_name="another-app").one().demoted_at
        is not None
    )


def test_discovery_and_serving_share_probe_throttle(db, svc, monkeypatch):
    dep = _seed(db)
    monkeypatch.setattr(settings, "FDM_LIVENESS_MIN_INTERVAL", 300.0)
    probe = AsyncMock(return_value=True)
    monkeypatch.setattr("app.services.fdm.liveness.is_ip_live", probe)
    asyncio.run(svc._detect_new_countries())
    assert probe.await_count == 2
    result = asyncio.run(svc._apply_liveness_gate(dep, [LIVE_IP, DEAD_IP]))
    assert result == [LIVE_IP, DEAD_IP]
    assert probe.await_count == 2


def test_liveness_kill_switch_retains_consensus_based_country_detection(
    db, svc, monkeypatch
):
    dep = _seed(db)
    monkeypatch.setattr(settings, "FDM_LIVENESS_ENABLED", False)
    asyncio.run(svc._detect_new_countries())
    db.refresh(dep)
    assert dep.is_active is True
    assert dep.consecutive_failures == 0


def test_new_live_region_works_without_port_443_health(db, svc):
    _seed(db, sibling=False)
    asyncio.run(svc._detect_new_countries())
    assert db.query(FdmDeployment).filter_by(region="JP").one().is_active is True


def test_xx_split_does_not_bypass_app_liveness_demotion(db, svc, monkeypatch):
    dep = _seed(db, sibling=False)
    db.add(FdmDeployment(flux_app_name=APP, region="XX", is_active=True))
    db.commit()
    # The discovery port may answer even when the registered VPN ports do not.
    monkeypatch.setattr(
        svc,
        "_get_cached_instances",
        AsyncMock(
            return_value=_DiscoveryResult([LIVE_IP, DEAD_IP], [DEAD_IP], True, None)
        ),
    )
    asyncio.run(svc._auto_split_regions())
    db.refresh(dep)
    assert dep.is_active is False
    assert db.query(FdmDeployment).filter_by(region="JP").one().is_active is True
