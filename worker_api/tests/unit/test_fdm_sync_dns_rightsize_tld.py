# worker_api/tests/unit/test_fdm_sync_dns_rightsize_tld.py
"""Phase 4b.2: FDM DNS-update + pool-rightsize write paths are per-active-TLD.

Group A (VM) DB-backed tests. Run via the _vm_drive runner (asserts
current_database == fluxvpn_test). Same scaffolding as
test_fdm_sync_tld_generation.py: @pytest.mark.database, (db_session, monkeypatch),
_stub_commit FIRST.
"""
from datetime import datetime, timezone

import pytest

from app.models.fdm import FdmDeployment, FdmDomain
from app.models.registered_tld import RegisteredTld
from app.services.fdm.fdm_sync_service import FdmSyncService


def _stub_commit(db_session, monkeypatch):
    monkeypatch.setattr(db_session, "commit", db_session.flush)


def _tld(db, domain, *, active=True, deleted=False, provider="cloudflare"):
    tld = RegisteredTld(
        domain=domain,
        dns_provider=provider,
        zone_id="zone-" + domain,
        purpose="fdm",
        server_ip="1.2.3.4",
        is_active=active,
        deleted_at=(
            datetime.now(timezone.utc).replace(tzinfo=None) if deleted else None
        ),
    )
    db.add(tld)
    db.flush()
    return tld


def _deployment(db, app_name, base_domain):
    dep = FdmDeployment(
        flux_app_name=app_name, region="CH", base_domain=base_domain, domain_pool_size=2
    )
    db.add(dep)
    db.flush()
    return dep


class _FakeClient:
    def __init__(self, provider, domain):
        self.provider = provider
        self.domain = domain

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def ensure_record_exists(self, name, ip, existing_record_id=None):
        return {"id": f"rec-{self.provider}-{name}"}


@pytest.mark.database
def test_update_dns_records_v2_routes_each_domain_to_its_own_tld(
    db_session, monkeypatch
):
    """Each FdmDomain is DNS-updated via its OWN tld's provider/zone, not a
    single active-TLD client. A cloudflare-TLD domain must NOT be pushed
    through the arvancloud client (and vice versa)."""
    import asyncio

    from app.services.fdm import fdm_sync_service

    _stub_commit(db_session, monkeypatch)
    svc = FdmSyncService(db=db_session)
    tld_a = _tld(db_session, "dnsv2a.link", provider="cloudflare")
    tld_b = _tld(db_session, "dnsv2b.link", provider="arvancloud")
    dep = _deployment(db_session, "fluxvpn-dnsv2-01", "dnsv2a.link")
    da = FdmDomain(
        deployment_id=dep.id,
        tld_id=tld_a.id,
        domain_name="cdn-01.dnsv2a.link",
        domain_id="cdn-01",
    )
    db_b = FdmDomain(
        deployment_id=dep.id,
        tld_id=tld_b.id,
        domain_name="cdn-01.dnsv2b.link",
        domain_id="cdn-01",
    )
    db_session.add_all([da, db_b])
    db_session.flush()

    built = {}

    def _fake_create(provider, domain, zone_id=None):
        built[(provider, domain)] = built.get((provider, domain), 0) + 1
        return _FakeClient(provider, domain)

    monkeypatch.setattr(fdm_sync_service, "create_dns_client", _fake_create)
    monkeypatch.setattr(
        svc, "_get_or_create_instance", lambda **kw: None
    )  # no PI side effects

    n, errs = asyncio.run(svc._update_dns_records_v2(dep, [da, db_b], ["10.0.0.1"]))

    assert n == 2
    assert errs == []  # no failures -> no error entries
    # one client per TLD, each built from that TLD's OWN domain/provider
    assert (cloudflare := ("cloudflare", "dnsv2a.link")) in built
    assert (arvancloud := ("arvancloud", "dnsv2b.link")) in built
    assert built[cloudflare] == 1 and built[arvancloud] == 1
    # legacy NULL-tld domain resolves to an active TLD (mirrors 4a read filter)
    legacy = FdmDomain(
        deployment_id=dep.id,
        tld_id=None,
        domain_name="cdn-99.dnsv2a.link",
        domain_id="cdn-99",
    )
    db_session.add(legacy)
    db_session.flush()
    built.clear()
    _n2, _e2 = asyncio.run(svc._update_dns_records_v2(dep, [legacy], ["10.0.0.1"]))
    assert any(p == "cloudflare" for (p, _) in built), built  # fell back to active TLD


@pytest.mark.database
def test_update_dns_records_v2_isolates_tld_client_creation_failure(
    db_session, monkeypatch
):
    """If create_dns_client fails for ONE tld (even with a non-ValueError), that
    tld's domains are marked unhealthy but the OTHER tld is still updated
    (multi-active isolation). Using RuntimeError (not the documented ValueError)
    locks in that ANY construction failure isolates per-TLD."""
    import asyncio

    from app.services.fdm import fdm_sync_service

    _stub_commit(db_session, monkeypatch)
    svc = FdmSyncService(db=db_session)
    tld_ok = _tld(db_session, "ok.link", provider="cloudflare")
    tld_bad = _tld(db_session, "bad.link", provider="arvancloud")
    dep = _deployment(db_session, "fluxvpn-dnsv2-02", "ok.link")
    d_ok = FdmDomain(
        deployment_id=dep.id,
        tld_id=tld_ok.id,
        domain_name="cdn-01.ok.link",
        domain_id="cdn-01",
    )
    d_bad = FdmDomain(
        deployment_id=dep.id,
        tld_id=tld_bad.id,
        domain_name="cdn-01.bad.link",
        domain_id="cdn-01",
    )
    db_session.add_all([d_ok, d_bad])
    db_session.flush()

    def _fake_create(provider, domain, zone_id=None):
        if provider == "arvancloud":
            raise RuntimeError("arvancloud misconfigured")  # non-ValueError
        return _FakeClient(provider, domain)

    monkeypatch.setattr(fdm_sync_service, "create_dns_client", _fake_create)
    monkeypatch.setattr(svc, "_get_or_create_instance", lambda **kw: None)

    n, errs = asyncio.run(svc._update_dns_records_v2(dep, [d_ok, d_bad], ["10.0.0.1"]))

    assert n == 1  # only the OK tld's domain updated
    assert d_ok.health_status == "healthy"
    assert d_bad.health_status == "unhealthy"  # bad tld isolated, marked unhealthy
    # per-TLD DNS failure is now RETURNED (spec §4.2), not silently swallowed
    assert len(errs) == 1
    assert errs[0]["tld_id"] == tld_bad.id
    assert errs[0]["step"] == "dns"
    assert errs[0]["failed"] == 1
    assert "arvancloud misconfigured" in errs[0]["sample"]


@pytest.mark.database
def test_rightsize_prunes_excess_per_tld(db_session, monkeypatch):
    """With 2 active TLDs, each TLD's pool is sized independently to
    max(healthy_count, 2). Excess is pruned WITHIN each TLD, not globally."""
    import asyncio

    _stub_commit(db_session, monkeypatch)
    svc = FdmSyncService(db=db_session)
    tld_a = _tld(db_session, "rsa.link")
    tld_b = _tld(db_session, "rsb.link")
    dep = _deployment(db_session, "fluxvpn-rs-01", "rsa.link")
    # 4 domains per TLD, healthy_count=2 -> prune 2 per TLD (4 total)
    for tld in (tld_a, tld_b):
        for i in range(4):
            db_session.add(
                FdmDomain(
                    deployment_id=dep.id,
                    tld_id=tld.id,
                    domain_name=f"cdn-{i:02d}.{tld.domain}",
                    domain_id=f"cdn-{i:02d}",
                    health_status="healthy",
                )
            )
    db_session.flush()

    pruned = asyncio.run(svc._rightsize_domain_pool(dep, healthy_count=2))

    remaining = (
        db_session.query(FdmDomain).filter(FdmDomain.deployment_id == dep.id).all()
    )
    per_tld = {tld_a.id: 0, tld_b.id: 0}
    for d in remaining:
        per_tld[d.tld_id] += 1
    assert pruned == 4
    assert per_tld == {tld_a.id: 2, tld_b.id: 2}, per_tld  # MIN_POOL=2 per TLD


@pytest.mark.database
def test_rightsize_no_change_when_each_tld_balanced(db_session, monkeypatch):
    """Each TLD already at target -> no pruning, no commit of deletes."""
    import asyncio

    _stub_commit(db_session, monkeypatch)
    svc = FdmSyncService(db=db_session)
    tld_a = _tld(db_session, "rsb.link")
    dep = _deployment(db_session, "fluxvpn-rs-02", "rsb.link")
    for i in range(2):
        db_session.add(
            FdmDomain(
                deployment_id=dep.id,
                tld_id=tld_a.id,
                domain_name=f"cdn-{i:02d}.rsb.link",
                domain_id=f"cdn-{i:02d}",
                health_status="healthy",
            )
        )
    db_session.flush()
    pruned = asyncio.run(svc._rightsize_domain_pool(dep, healthy_count=2))
    assert pruned == 0


@pytest.mark.database
def test_update_dns_records_v2_skips_orphan_domains_of_deactivated_tld(
    db_session, monkeypatch
):
    """A domain whose tld_id points at a DEACTIVATED (non-active) TLD is an orphan
    (D8: deactivate preserves rows for re-activation). It must NOT be re-routed
    through an active TLD's DNS provider -- its DNS write + dns_record_id + health
    stay untouched. (Distinct from a legacy NULL-tld row, which DOES fall back.)"""
    import asyncio

    from app.services.fdm import fdm_sync_service

    _stub_commit(db_session, monkeypatch)
    svc = FdmSyncService(db=db_session)
    tld_a = _tld(db_session, "alive.link", provider="cloudflare")  # active
    tld_dead = _tld(
        db_session, "dead.link", provider="arvancloud", active=False
    )  # deactivated
    dep = _deployment(db_session, "fluxvpn-orphan-01", "alive.link")
    d_alive = FdmDomain(
        deployment_id=dep.id,
        tld_id=tld_a.id,
        domain_name="cdn-01.alive.link",
        domain_id="cdn-01",
        health_status="healthy",
        dns_record_id="rec-alive",
    )
    d_orphan = FdmDomain(
        deployment_id=dep.id,
        tld_id=tld_dead.id,
        domain_name="cdn-01.dead.link",
        domain_id="cdn-01",
        health_status="unhealthy",
        dns_record_id="rec-orphan",
    )
    db_session.add_all([d_alive, d_orphan])
    db_session.flush()

    ensured = []

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def ensure_record_exists(self, name, ip, existing_record_id=None):
            ensured.append(existing_record_id)
            return {"id": f"new-{existing_record_id}"}

    monkeypatch.setattr(
        fdm_sync_service,
        "create_dns_client",
        lambda provider, domain, zone_id=None: _FakeClient(),
    )
    monkeypatch.setattr(svc, "_get_or_create_instance", lambda **kw: None)

    n, _errs = asyncio.run(
        svc._update_dns_records_v2(dep, [d_alive, d_orphan], ["10.0.0.1"])
    )

    assert n == 1  # only the alive domain updated
    assert d_alive.health_status == "healthy"
    assert d_alive.dns_record_id == "new-rec-alive"
    # orphan UNTOUCHED: not re-routed, no DNS write, id + health preserved
    assert "rec-orphan" not in ensured
    assert d_orphan.dns_record_id == "rec-orphan"
    assert d_orphan.health_status == "unhealthy"


@pytest.mark.database
def test_update_dns_records_v2_records_failure_per_tld_bucket(db_session, monkeypatch):
    """A TLD whose creates ALL fail yields exactly one dns_error entry keyed by
    that tld_id (with a sample); a TLD with no failures yields none. Spec §4.2."""
    import asyncio

    from app.services.fdm import fdm_sync_service

    _stub_commit(db_session, monkeypatch)
    svc = FdmSyncService(db=db_session)
    tld_ok = _tld(db_session, "ok2.link", provider="cloudflare")
    tld_bad = _tld(db_session, "bad2.link", provider="arvancloud")
    dep = _deployment(db_session, "fluxvpn-dnsv2-03", "ok2.link")
    d_ok = FdmDomain(
        deployment_id=dep.id,
        tld_id=tld_ok.id,
        domain_name="cdn-01.ok2.link",
        domain_id="cdn-01",
    )
    d_bad1 = FdmDomain(
        deployment_id=dep.id,
        tld_id=tld_bad.id,
        domain_name="cdn-01.bad2.link",
        domain_id="cdn-01",
    )
    d_bad2 = FdmDomain(
        deployment_id=dep.id,
        tld_id=tld_bad.id,
        domain_name="cdn-02.bad2.link",
        domain_id="cdn-02",
    )
    db_session.add_all([d_ok, d_bad1, d_bad2])
    db_session.flush()

    class _FailClient:
        def __init__(self, provider, domain):
            self.provider = provider
            self.domain = domain

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def ensure_record_exists(self, name, ip, existing_record_id=None):
            raise RuntimeError("arvan 403 forbidden zone")

    def _fake_create(provider, domain, zone_id=None):
        if provider == "arvancloud":
            return _FailClient(provider, domain)
        return _FakeClient(provider, domain)

    monkeypatch.setattr(fdm_sync_service, "create_dns_client", _fake_create)
    monkeypatch.setattr(svc, "_get_or_create_instance", lambda **kw: None)

    n, errs = asyncio.run(
        svc._update_dns_records_v2(dep, [d_ok, d_bad1, d_bad2], ["10.0.0.1"])
    )

    assert n == 1  # only ok tld updated
    assert len(errs) == 1  # one entry for the bad tld
    e = errs[0]
    assert e["tld_id"] == tld_bad.id
    assert e["tld_domain"] == "bad2.link"
    assert e["provider"] == "arvancloud"
    assert e["failed"] == 2  # BOTH bad-tld domains failed
    assert "arvan 403 forbidden zone" in e["sample"]


@pytest.mark.database
def test_update_dns_records_v2_skips_budget_exceeded_domain_without_marking_unhealthy(
    db_session, monkeypatch
):
    """A domain whose ensure_record_exists raises ArvanCloudRateLimitBudgetExceeded
    (Phase 4.4) must be left with its PRIOR health_status untouched, must NOT be
    counted in bucket_err['failed'] / the returned dns_errors list, and must NOT
    be counted in domains_updated. This is what lets the hot loop defer to the
    next cycle instead of falsely flagging a domain unhealthy purely because
    FDM chose not to call ArvanCloud yet."""
    import asyncio

    from app.services.fdm import fdm_sync_service
    from app.services.fdm.arvancloud_client import ArvanCloudRateLimitBudgetExceeded

    _stub_commit(db_session, monkeypatch)
    svc = FdmSyncService(db=db_session)
    tld = _tld(db_session, "budget.link", provider="arvancloud")
    dep = _deployment(db_session, "fluxvpn-budget-01", "budget.link")
    d_throttled = FdmDomain(
        deployment_id=dep.id,
        tld_id=tld.id,
        domain_name="cdn-01.budget.link",
        domain_id="cdn-01",
        health_status="healthy",  # was healthy BEFORE this cycle
    )
    db_session.add(d_throttled)
    db_session.flush()

    class _ThrottledClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def ensure_record_exists(self, name, ip, existing_record_id=None):
            raise ArvanCloudRateLimitBudgetExceeded("budget exhausted")

    monkeypatch.setattr(
        fdm_sync_service,
        "create_dns_client",
        lambda provider, domain, zone_id=None: _ThrottledClient(),
    )
    monkeypatch.setattr(svc, "_get_or_create_instance", lambda **kw: None)

    n, errs = asyncio.run(svc._update_dns_records_v2(dep, [d_throttled], ["10.0.0.1"]))

    assert n == 0  # not counted as updated
    assert d_throttled.health_status == "healthy"  # UNCHANGED, not flipped unhealthy
    assert errs == []  # budget-only skip -> no error entry,
    # no dark-TLD alert trigger


@pytest.mark.database
def test_update_dns_records_v2_reports_skipped_alongside_real_failures(
    db_session, monkeypatch
):
    """A tld bucket with BOTH a real failure and a budget-skip: the returned
    error entry (triggered by the real failure) additionally carries a
    'skipped' count for observability, without inflating 'failed'."""
    import asyncio

    from app.services.fdm import fdm_sync_service
    from app.services.fdm.arvancloud_client import ArvanCloudRateLimitBudgetExceeded

    _stub_commit(db_session, monkeypatch)
    svc = FdmSyncService(db=db_session)
    tld = _tld(db_session, "mixed.link", provider="arvancloud")
    dep = _deployment(db_session, "fluxvpn-mixed-01", "mixed.link")
    d_fail = FdmDomain(
        deployment_id=dep.id,
        tld_id=tld.id,
        domain_name="cdn-01.mixed.link",
        domain_id="cdn-01",
    )
    d_throttled = FdmDomain(
        deployment_id=dep.id,
        tld_id=tld.id,
        domain_name="cdn-02.mixed.link",
        domain_id="cdn-02",
        health_status="healthy",
    )
    db_session.add_all([d_fail, d_throttled])
    db_session.flush()

    class _MixedClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def ensure_record_exists(self, name, ip, existing_record_id=None):
            if name == "cdn-01":
                raise RuntimeError("arvan 500")
            raise ArvanCloudRateLimitBudgetExceeded("budget exhausted")

    monkeypatch.setattr(
        fdm_sync_service,
        "create_dns_client",
        lambda provider, domain, zone_id=None: _MixedClient(),
    )
    monkeypatch.setattr(svc, "_get_or_create_instance", lambda **kw: None)

    n, errs = asyncio.run(
        svc._update_dns_records_v2(dep, [d_fail, d_throttled], ["10.0.0.1"])
    )

    assert n == 0
    assert d_throttled.health_status == "healthy"  # budget-skip: untouched
    assert d_fail.health_status == "unhealthy"  # real failure: marked unhealthy
    assert len(errs) == 1
    assert errs[0]["failed"] == 1  # only the real failure counts
    assert errs[0]["skipped"] == 1  # budget-skip visible, separately
