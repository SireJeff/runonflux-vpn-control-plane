"""Analytics endpoints (phase 5.3). DB-backed: live snapshot == active_user_counts
(drift-proof); series returns TldUsageDaily rows chart-ready.

The bad-purpose Query(pattern=...) contract only validates through the HTTP
layer (TestClient), not a direct call, so it is not asserted here — the two
real drift-proof assertions are the load-bearing ones.

Run via the VM driver against fluxvpn_test (never the prod fluxvpn db).
"""
import asyncio
from datetime import date, timedelta

import pytest

from app.api.v1.endpoints import super_admin as sa
from app.models.admin_tld_state import AdminTldState
from app.models.admin_users import AdminUser
from app.models.admins import Admin
from app.models.registered_tld import RegisteredTld
from app.services.tlds.selection import TldSelectionService
from app.tasks.tld_analytics import run_tld_snapshot


def _stub_commit(db_session, monkeypatch):
    monkeypatch.setattr(db_session, "commit", db_session.flush)


def _seed(db, domain, purpose, n_users):
    tld = RegisteredTld(
        domain=domain, dns_provider="cloudflare", purpose=purpose, is_active=True
    )
    db.add(tld)
    db.flush()
    adm = Admin(username=f"r{domain}", password_hash="x", status="active")
    db.add(adm)
    db.flush()
    db.add(
        AdminTldState(
            admin_id=adm.id, purpose=purpose, effective_tld_id=tld.id, source="lb"
        )
    )
    for i in range(n_users):
        db.add(AdminUser(admin_id=adm.id, username=f"{domain}_u{i}"))
    db.flush()
    return tld


@pytest.mark.database
def test_get_tld_analytics_snapshot_matches_active_user_counts(db_session, monkeypatch):
    _stub_commit(db_session, monkeypatch)
    a = _seed(db_session, "a.com", "fdm", 3)
    b = _seed(db_session, "b.com", "fdm", 1)

    snap = asyncio.run(sa.get_tld_analytics(db=db_session, current={"id": 1}))

    counts = TldSelectionService(db_session).active_user_counts("fdm")
    by_id = {t.tld_id: t.active_user_count for t in snap.fdm}
    assert by_id == counts  # drift-proof
    assert {t.tld_id for t in snap.fdm} == {a.id, b.id}
    # other purposes empty (none seeded)
    assert snap.subscription == []


@pytest.mark.database
def test_get_tld_analytics_series_returns_chart_ready_rows(db_session, monkeypatch):
    _stub_commit(db_session, monkeypatch)
    _seed(db_session, "a.com", "fdm", 0)
    # relative to "today" so the snapshot stays inside the 30-day `days`
    # window used by get_tld_analytics_series regardless of when the test
    # suite is actually run (a hardcoded absolute date ages out of the
    # window and the series query legitimately returns nothing).
    snapshot_date = date.today() - timedelta(days=5)
    run_tld_snapshot(db_session, today=snapshot_date)

    series = asyncio.run(
        sa.get_tld_analytics_series(
            purpose="fdm",
            days=30,
            db=db_session,
            current={"id": 1},
        )
    )

    assert series.purpose == "fdm"
    assert "a.com" in series.domains
    assert len(series.series) == 1
    day = series.series[0]
    assert day.date == snapshot_date.isoformat()
    assert day.values["a.com"] == 0  # seeded 0 active users


@pytest.mark.database
def test_get_tld_analytics_dns_health_for_fdm_tlds(db_session, monkeypatch):
    """fdm TLDs carry a dns_health block (healthy/total/all_dns_failed/last_error)
    sourced from FdmDomain counts + the latest dns error sample. Non-fdm
    purposes have dns_health is None. Spec §4.3."""
    from datetime import datetime, timezone

    from app.models.fdm import FdmDeployment, FdmDomain, FdmSyncLog

    _stub_commit(db_session, monkeypatch)
    db = db_session
    # fdm TLD with 2 healthy + 1 unhealthy domain, and a logged dns error
    dep = FdmDeployment(
        flux_app_name="app", region="CH", base_domain="lit.link", domain_pool_size=3
    )
    db.add(dep)
    db.flush()
    lit = _seed(db, "lit.link", "fdm", 0)  # _seed makes the TLD active
    db.add(
        FdmDomain(
            deployment_id=dep.id,
            tld_id=lit.id,
            domain_name="a.lit.link",
            domain_id="a",
            health_status="healthy",
        )
    )
    db.add(
        FdmDomain(
            deployment_id=dep.id,
            tld_id=lit.id,
            domain_name="b.lit.link",
            domain_id="b",
            health_status="healthy",
        )
    )
    db.add(
        FdmDomain(
            deployment_id=dep.id,
            tld_id=lit.id,
            domain_name="c.lit.link",
            domain_id="c",
            health_status="unhealthy",
        )
    )
    db.flush()
    db.add(
        FdmSyncLog(
            deployment_id=dep.id,
            sync_started_at=datetime.now(timezone.utc),
            status="partial",
            errors=[{"step": "dns", "tld_id": lit.id, "sample": "arvan 403"}],
        )
    )
    db.flush()
    # a subscription TLD (no domains, no health concept)
    sub = _seed(db, "sub.link", "subscription", 0)

    snap = asyncio.run(sa.get_tld_analytics(db=db, current={"id": 1}))

    fdm = {t.tld_id: t for t in snap.fdm}
    assert lit.id in fdm
    h = fdm[lit.id].dns_health
    assert h is not None
    assert h.healthy_domains == 2
    assert h.total_domains == 3
    assert h.all_dns_failed is False
    assert h.last_error == "arvan 403"

    # non-fdm: no dns_health
    sub_snap = {t.tld_id: t for t in snap.subscription}
    assert sub_snap[sub.id].dns_health is None


@pytest.mark.database
def test_get_tld_analytics_dns_health_all_dns_failed_when_no_healthy(
    db_session, monkeypatch
):
    """A fdm TLD whose domains are ALL unhealthy surfaces all_dns_failed=True
    (the badge's red 'DNS down' state) with the latest dns error as last_error.
    Guards the high-signal branch left uncovered by the happy-path test. Spec §4.3."""
    from datetime import datetime, timezone

    from app.models.fdm import FdmDeployment, FdmDomain, FdmSyncLog

    _stub_commit(db_session, monkeypatch)
    db = db_session
    dep = FdmDeployment(
        flux_app_name="app", region="CH", base_domain="dark.link", domain_pool_size=2
    )
    db.add(dep)
    db.flush()
    dark = _seed(db, "dark.link", "fdm", 0)
    db.add(
        FdmDomain(
            deployment_id=dep.id,
            tld_id=dark.id,
            domain_name="a.dark.link",
            domain_id="a",
            health_status="unhealthy",
        )
    )
    db.add(
        FdmDomain(
            deployment_id=dep.id,
            tld_id=dark.id,
            domain_name="b.dark.link",
            domain_id="b",
            health_status="unhealthy",
        )
    )
    db.flush()
    db.add(
        FdmSyncLog(
            deployment_id=dep.id,
            sync_started_at=datetime.now(timezone.utc),
            status="partial",
            errors=[
                {"step": "dns", "tld_id": dark.id, "sample": "arvan 403 forbidden"}
            ],
        )
    )
    db.flush()

    snap = asyncio.run(sa.get_tld_analytics(db=db, current={"id": 1}))

    h = {t.tld_id: t for t in snap.fdm}[dark.id].dns_health
    assert h is not None
    assert h.healthy_domains == 0
    assert h.total_domains == 2
    assert h.all_dns_failed is True  # the red badge state
    assert h.last_error == "arvan 403 forbidden"
