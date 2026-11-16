"""De-duped DNS-dark superadmin alert (spec §4.3). A fdm TLD that is fully
DNS-dark this cycle (in dns_errors AND 0 healthy domains) alerts the
superadmin ONCE per 6h via platform_settings tld_dns_alert:{id}.

Group A (VM) DB-backed: @pytest.mark.database, (db_session, monkeypatch),
_stub_commit FIRST. NotificationRouter.send_to_super_admin is monkeypatched
to record calls (no real Telegram).
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.models.fdm import FdmDeployment, FdmDomain
from app.models.platform_settings import PlatformSetting
from app.models.registered_tld import RegisteredTld
from app.services.fdm.fdm_sync_service import FdmSyncService
from app.services.notifications import router as router_mod


def _stub_commit(db_session, monkeypatch):
    monkeypatch.setattr(db_session, "commit", db_session.flush)


def _tld(db, domain):
    t = RegisteredTld(
        domain=domain,
        dns_provider="arvancloud",
        zone_id=domain,
        purpose="fdm",
        server_ip="1.2.3.4",
        is_active=True,
    )
    db.add(t)
    db.flush()
    return t


def _dark_error(tld):
    return {
        "step": "dns",
        "tld_id": tld.id,
        "tld_domain": tld.domain,
        "provider": tld.dns_provider,
        "failed": 3,
        "sample": "ArvanCloud API error during create record: 403",
    }


@pytest.mark.database
def test_alert_fires_once_and_writes_marker(db_session, monkeypatch):
    """Dark TLD, no prior marker -> fires once and stamps platform_settings."""
    import asyncio

    _stub_commit(db_session, monkeypatch)
    svc = FdmSyncService(db=db_session)
    dark = _tld(db_session, "dark.link")  # 0 healthy domains

    fired = []
    monkeypatch.setattr(
        router_mod.NotificationRouter,
        "send_to_super_admin",
        lambda self, msg: fired.append(msg) or True,
    )

    asyncio.run(svc._alert_dns_dark_tlds([_dark_error(dark)]))

    assert len(fired) == 1
    assert "dark.link" in fired[0]
    row = (
        db_session.query(PlatformSetting)
        .filter(PlatformSetting.key == f"tld_dns_alert:{dark.id}")
        .first()
    )
    assert row is not None and row.value  # stamp written


@pytest.mark.database
def test_alert_skipped_within_cooldown(db_session, monkeypatch):
    """Marker < 6h old -> does not re-fire."""
    import asyncio

    _stub_commit(db_session, monkeypatch)
    svc = FdmSyncService(db=db_session)
    dark = _tld(db_session, "dark.link")
    recent = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    db_session.add(PlatformSetting(key=f"tld_dns_alert:{dark.id}", value=recent))
    db_session.flush()

    fired = []
    monkeypatch.setattr(
        router_mod.NotificationRouter,
        "send_to_super_admin",
        lambda self, msg: fired.append(msg) or True,
    )

    asyncio.run(svc._alert_dns_dark_tlds([_dark_error(dark)]))
    assert fired == []  # cooled down -> no re-fire


@pytest.mark.database
def test_no_alert_when_tld_has_healthy_domain(db_session, monkeypatch):
    """TLD appears in dns_errors (partial failure) but still has a healthy
    domain -> NOT fully dark -> no alert."""
    import asyncio

    _stub_commit(db_session, monkeypatch)
    svc = FdmSyncService(db=db_session)
    dep = FdmDeployment(
        flux_app_name="app", region="CH", base_domain="lit.link", domain_pool_size=2
    )
    db_session.add(dep)
    db_session.flush()
    lit = _tld(db_session, "lit.link")
    db_session.add(
        FdmDomain(
            deployment_id=dep.id,
            tld_id=lit.id,
            domain_name="a.lit.link",
            domain_id="a",
            health_status="healthy",
        )
    )
    db_session.flush()

    fired = []
    monkeypatch.setattr(
        router_mod.NotificationRouter,
        "send_to_super_admin",
        lambda self, msg: fired.append(msg) or True,
    )

    asyncio.run(svc._alert_dns_dark_tlds([_dark_error(lit)]))
    assert fired == []
