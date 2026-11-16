"""Phase 4b.1: FDM sync generates FdmDomain rows per active fdm TLD.

Group A (VM) tests — construct FdmSyncService against the fluxvpn_test DB.
Run via the _vm_drive runner (asserts current_database == fluxvpn_test).

db_session fixture + tables fixture come from conftest (same pattern as
tests/unit/services/test_tld_selection.py). Use a UNIQUE flux_app_name per
test: the shared StaticPool session resets the schema only between runs.

DB-test scaffolding (mirror tests/unit/test_super_admin_tld_lifecycle.py:23-29):
every DB test is @pytest.mark.database-marked, takes (db_session, monkeypatch),
and calls _stub_commit(db_session, monkeypatch) FIRST. db_session wraps each
test in a connection-level transaction rolled back at teardown; the service
methods under test call self.db.commit(), which would otherwise commit that
outer transaction and leak rows into later tests in the run (StaticPool
reuses one connection; schema resets only between runs).
"""
from datetime import datetime, timezone

import pytest

from app.models.fdm import FdmDeployment, FdmDomain
from app.models.registered_tld import RegisteredTld
from app.services.fdm.fdm_sync_service import FdmSyncService


def _stub_commit(db_session, monkeypatch):
    """Map session.commit -> flush so service self.db.commit() doesn't persist
    beyond this test (leaks rows across the StaticPool single-connection run).
    Verbatim from tests/unit/test_super_admin_tld_lifecycle.py:23-29."""
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
        flux_app_name=app_name,
        region="CH",
        base_domain=base_domain,
        domain_pool_size=2,
    )
    db.add(dep)
    db.flush()
    return dep


# ---------------------------------------------------------------------------
# Task 4b.1.1 — _active_fdm_tlds + per-TLD _ensure_domains_exist
# ---------------------------------------------------------------------------


@pytest.mark.database
def test_active_fdm_tlds_returns_only_active_non_deleted_fdm(db_session, monkeypatch):
    _stub_commit(db_session, monkeypatch)
    svc = FdmSyncService(db=db_session)
    _tld(db_session, "a.link")
    _tld(db_session, "b.link", active=False)  # inactive  -> excluded
    _tld(db_session, "c.link", deleted=True)  # deleted   -> excluded
    db_session.add(
        RegisteredTld(  # other purpose -> excluded
            domain="s.link",
            dns_provider="cloudflare",
            zone_id="z",
            purpose="subscription",
            server_ip="1.1.1.1",
            is_active=True,
        )
    )
    db_session.flush()

    result = svc._active_fdm_tlds()

    assert [t.domain for t in result] == ["a.link"], [t.domain for t in result]


@pytest.mark.database
def test_ensure_domains_exist_creates_one_pool_per_active_tld(db_session, monkeypatch):
    """With 2 active fdm TLDs, generation fans out: target_count domains PER
    TLD, each tagged with its tld_id and suffixed by its tld.domain."""
    _stub_commit(db_session, monkeypatch)
    svc = FdmSyncService(db=db_session)
    tld_a = _tld(db_session, "tlda.link")
    tld_b = _tld(db_session, "tldb.link")
    dep = _deployment(db_session, "fluxvpn-ch-01", "tlda.link")

    created = svc._ensure_domains_exist(dep, healthy_ip_count=2)

    assert len(created) == 4, [d.domain_name for d in created]  # 2 per TLD
    for_a = [d for d in created if d.tld_id == tld_a.id]
    for_b = [d for d in created if d.tld_id == tld_b.id]
    assert len(for_a) == 2 and len(for_b) == 2
    assert all(d.domain_name.endswith(".tlda.link") for d in for_a)
    assert all(d.domain_name.endswith(".tldb.link") for d in for_b)
    # slug is reusable across TLDs (domain_name stays globally unique via suffix)
    assert {d.domain_id for d in for_a} == {d.domain_id for d in for_b}


@pytest.mark.database
def test_ensure_domains_exist_single_active_matches_legacy_shape(
    db_session, monkeypatch
):
    """Under single-active, per-TLD generation == today's global generation:
    one pool of target_count domains, all tagged with the one active tld_id."""
    _stub_commit(db_session, monkeypatch)
    svc = FdmSyncService(db=db_session)
    only = _tld(db_session, "only.link")
    dep = _deployment(db_session, "fluxvpn-ch-02", "only.link")

    created = svc._ensure_domains_exist(dep, healthy_ip_count=3)

    assert len(created) == 3
    assert all(d.tld_id == only.id for d in created)
    assert all(d.domain_name.endswith(".only.link") for d in created)


@pytest.mark.database
def test_ensure_domains_exist_no_active_tld_is_a_safe_noop(db_session, monkeypatch):
    """No active fdm TLD -> do NOT generate tld_id-less rows; return existing."""
    _stub_commit(db_session, monkeypatch)
    svc = FdmSyncService(db=db_session)
    dep = _deployment(db_session, "fluxvpn-ch-03", "orphan.link")

    created = svc._ensure_domains_exist(dep, healthy_ip_count=2)

    assert created == []


@pytest.mark.database
def test_ensure_domains_exist_counts_legacy_null_tld_rows(db_session, monkeypatch):
    """Legacy tld_id=NULL rows (pre-4a-backfill, or created by an earlier phase)
    count toward the active TLD's pool — mirroring the 4a read filter where NULL
    resolves to effective — so the sync tops up rather than over-creating."""
    _stub_commit(db_session, monkeypatch)
    svc = FdmSyncService(db=db_session)
    only = _tld(db_session, "legacy.link")
    dep = _deployment(db_session, "fluxvpn-ch-04", "legacy.link")
    # A pre-existing legacy row with no tld_id (e.g. created before 4a backfill).
    db_session.add(
        FdmDomain(
            deployment_id=dep.id,
            tld_id=None,
            domain_name="cdn-99.legacy.link",
            domain_id="cdn-99",
            health_status="healthy",
        )
    )
    db_session.flush()

    created = svc._ensure_domains_exist(dep, healthy_ip_count=2)  # target_count = 2

    # The 1 NULL row counts toward the active TLD's pool -> only 1 more created.
    assert len(created) == 2, [d.domain_name for d in created]
    tagged = [d for d in created if d.tld_id == only.id]
    assert len(tagged) == 1, [d.domain_name for d in created]


@pytest.mark.database
def test_create_domains_for_tld_dedup_is_suffix_aware_not_tld_id_scoped(
    db_session,
    monkeypatch,
):
    """REGRESSION (fdm_sync_crashloop_2026-06-27): a legacy tld_id=NULL row
    sharing the active TLD's base-domain suffix MUST be in the dedup set.
    Under the old tld_id-scoped dedup (.filter(tld_id == tld.id)) the NULL row
    is invisible, so generate_domain_names re-emits its slug -- cdn-01 is the
    first slug it emits -- and the INSERT collides on the GLOBAL
    fdm_domains_domain_name_key unique constraint -> IntegrityError -> poisoned
    session -> sync_all_deployments dies. The dedup is suffix-aware: any
    existing domain_name ending '.{tld.domain}', regardless of tld_id."""
    _stub_commit(db_session, monkeypatch)
    svc = FdmSyncService(db=db_session)
    only = _tld(db_session, "collide.link")
    dep = _deployment(db_session, "fluxvpn-ch-99", "collide.link")
    # Legacy NULL row whose slug (cdn-01) is the FIRST slug generate emits.
    db_session.add(
        FdmDomain(
            deployment_id=dep.id,
            tld_id=None,
            domain_name="cdn-01.collide.link",
            domain_id="cdn-01",
            health_status="healthy",
        )
    )
    db_session.flush()

    created = svc._create_domains_for_tld(dep, only, count=2)

    # 2 created, NONE reusing the legacy NULL row's slug -> no collision.
    assert created == 2
    new_rows = (
        db_session.query(FdmDomain)
        .filter(
            FdmDomain.deployment_id == dep.id,
            FdmDomain.tld_id == only.id,
        )
        .all()
    )
    assert len(new_rows) == 2, [r.domain_name for r in new_rows]
    assert all(
        r.domain_id != "cdn-01" for r in new_rows
    ), "dedup missed the legacy NULL cdn-01 row: %r" % [r.domain_name for r in new_rows]
    # The legacy NULL row is untouched.
    null_rows = (
        db_session.query(FdmDomain)
        .filter(FdmDomain.deployment_id == dep.id, FdmDomain.tld_id.is_(None))
        .all()
    )
    assert len(null_rows) == 1 and null_rows[0].domain_id == "cdn-01"


# ---------------------------------------------------------------------------
# Task 4b.1.2 — per-TLD replenish in _manage_domain_lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.database
def test_manage_domain_lifecycle_replenishes_per_tld(db_session, monkeypatch):
    """Replenish tops up each active TLD's healthy-domain pool; new rows carry
    tld_id + the TLD's suffix + the seed IP (healthy_ips[0])."""
    _stub_commit(db_session, monkeypatch)
    import asyncio

    svc = FdmSyncService(db=db_session)
    tld_a = _tld(db_session, "lca.link")
    tld_b = _tld(db_session, "lcb.link")
    dep = _deployment(db_session, "fluxvpn-ch-10", "lca.link")

    # No domains yet -> target_pool = max(2, 2) = 2 created per TLD.
    asyncio.run(svc._manage_domain_lifecycle(dep, healthy_ips=["10.0.0.1", "10.0.0.2"]))

    rows = db_session.query(FdmDomain).filter(FdmDomain.deployment_id == dep.id).all()
    for_a = [d for d in rows if d.tld_id == tld_a.id]
    for_b = [d for d in rows if d.tld_id == tld_b.id]
    assert len(for_a) == 2 and len(for_b) == 2, [d.domain_name for d in rows]
    assert all(d.current_ip == "10.0.0.1" for d in for_a + for_b)
    assert all(d.domain_name.endswith(".lca.link") for d in for_a)
    assert all(d.domain_name.endswith(".lcb.link") for d in for_b)


# ---------------------------------------------------------------------------
# Task 4b.1.3 — _delete_dns_record_for_domain resolves via domain.tld_id
# ---------------------------------------------------------------------------


@pytest.mark.database
def test_delete_dns_record_uses_domain_own_tld_not_active(db_session, monkeypatch):
    """The DNS client is built from the domain's OWN tld (domain.tld_id), not
    whichever fdm TLD is active — so a record created under an inactive TLD
    is still deleted via that TLD's provider."""
    _stub_commit(db_session, monkeypatch)
    import asyncio

    from app.services.fdm import fdm_sync_service

    svc = FdmSyncService(db=db_session)
    _tld(
        db_session, "active.link", active=True, provider="cloudflare"
    )  # the active one
    other = _tld(db_session, "other.link", active=False, provider="arvancloud")
    dep = _deployment(db_session, "fluxvpn-ch-20", "other.link")
    dom = FdmDomain(
        deployment_id=dep.id,
        tld_id=other.id,
        domain_name="cdn-01.other.link",
        domain_id="cdn-01",
        dns_record_id="rec-xyz",
        health_status="healthy",
    )
    db_session.add(dom)
    db_session.flush()

    captured: dict = {}

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def delete_dns_record(self, record_id):
            captured["deleted"] = record_id

    def _fake_create(provider, domain, zone_id=None):
        captured["provider"] = provider
        captured["domain"] = domain
        captured["zone_id"] = zone_id
        return _FakeClient()

    monkeypatch.setattr(fdm_sync_service, "create_dns_client", _fake_create)

    asyncio.run(svc._delete_dns_record_for_domain(dom))

    assert captured.get("deleted") == "rec-xyz"
    # domain's OWN tld (arvancloud/other.link), NOT the active cloudflare one
    assert captured.get("provider") == "arvancloud", captured
    assert captured.get("domain") == "other.link"
