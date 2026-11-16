# worker_api/tests/unit/test_super_admin_fdm_activate.py
"""Phase 4b.2: _activate_fdm_tld is additive (multi-active) + delete_tld cleans
fdm subdomain DNS. Group A (VM) DB-backed. Same scaffolding as
test_super_admin_tld_lifecycle.py."""
from datetime import datetime, timezone

import pytest

from app.models.fdm import FdmDeployment, FdmDomain
from app.models.registered_tld import RegisteredTld


def _stub_commit(db_session, monkeypatch):
    monkeypatch.setattr(db_session, "commit", db_session.flush)


def _tld(db, domain, *, active=True, provider="cloudflare", purpose="fdm"):
    tld = RegisteredTld(
        domain=domain,
        dns_provider=provider,
        zone_id="z-" + domain,
        purpose=purpose,
        server_ip="9.9.9.9",
        is_active=active,
    )
    db.add(tld)
    db.flush()
    return tld


@pytest.mark.database
def test_activate_fdm_tld_is_additive_second_tld_keeps_first(db_session, monkeypatch):
    """Activating a 2nd fdm TLD must NOT wipe the 1st's FdmDomains, NOT rewrite
    base_domain, NOT flip the sibling, and trigger sync + operator alert."""
    import asyncio

    from app.api.v1.endpoints import super_admin as sa

    _stub_commit(db_session, monkeypatch)
    first = _tld(db_session, "first.link", active=True)
    second = _tld(db_session, "second.link", active=False)
    dep = FdmDeployment(
        flux_app_name="fluxvpn-act-01",
        region="CH",
        base_domain="first.link",
        domain_pool_size=2,
    )
    db_session.add(dep)
    db_session.flush()  # populate dep.id before the FdmDomain FK references it
    db_session.add(
        FdmDomain(
            deployment_id=dep.id,
            tld_id=first.id,
            domain_name="cdn-01.first.link",
            domain_id="cdn-01",
            health_status="healthy",
        )
    )
    db_session.flush()

    # Stub external effects: DNS client (no real provider calls), sync task, broadcast.
    sync_calls = {"n": 0}
    broadcast_calls = {"args": None}

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def ensure_record_exists(self, name, ip, ttl=120):
            return {"id": "rec"}

    monkeypatch.setattr(
        sa, "create_dns_client", lambda provider, domain, zone_id=None: _FakeClient()
    )

    def _fake_enqueue():
        sync_calls["n"] += 1
        return True

    monkeypatch.setattr(sa, "_enqueue_fdm_sync", _fake_enqueue)

    async def _fake_broadcast(purpose, old, new, db):
        broadcast_calls["args"] = (purpose, old, new)

    monkeypatch.setattr(sa, "_broadcast_tld_change", _fake_broadcast)

    asyncio.run(sa._activate_fdm_tld(db_session, second, first))

    # 1st TLD's domain SURVIVES (no bulk-wipe)
    surviving = db_session.query(FdmDomain).filter(FdmDomain.tld_id == first.id).all()
    assert (
        len(surviving) == 1
    ), "first TLD's FdmDomains must survive activation of a 2nd"
    # sibling NOT flipped (multi-active)
    assert first.is_active is True, "activating 2nd fdm TLD must not deactivate the 1st"
    assert second.is_active is True
    # base_domain NOT rewritten
    assert dep.base_domain == "first.link"
    # sync triggered + operator alert fired (no end-user notice)
    assert sync_calls["n"] == 1
    assert broadcast_calls["args"] == ("fdm", None, "second.link")


@pytest.mark.database
def test_delete_fdm_tld_removes_subdomain_dns_and_rows(db_session, monkeypatch):
    """Deleting an fdm TLD removes each of its FdmDomains' subdomain DNS records
    and deletes the rows (terminal). The root A-record removal is generic; this
    covers the subdomains. Non-fdm purposes are untouched by this branch."""
    import asyncio

    from app.api.v1.endpoints import super_admin as sa

    _stub_commit(db_session, monkeypatch)
    _tld(
        db_session, "keep.link", active=True
    )  # sibling stays active (last-active guard)
    dying = _tld(db_session, "die.link", active=True)
    dep = FdmDeployment(
        flux_app_name="fluxvpn-del-01",
        region="CH",
        base_domain="die.link",
        domain_pool_size=2,
    )
    db_session.add(dep)
    db_session.flush()  # populate dep.id before the FdmDomain FK
    dom = FdmDomain(
        deployment_id=dep.id,
        tld_id=dying.id,
        domain_name="cdn-01.die.link",
        domain_id="cdn-01",
        dns_record_id="rec-die-01",
        health_status="healthy",
    )
    db_session.add(dom)
    db_session.flush()

    deleted_records = []

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def find_a_record_by_name(self, name):
            return None  # root record already gone

        async def delete_dns_record(self, rid):
            deleted_records.append(rid)
            return True

    monkeypatch.setattr(
        sa, "create_dns_client", lambda provider, domain, zone_id=None: _FakeClient()
    )

    # stub the FDM per-record deleter to capture without real provider calls
    async def _fake_del_dns(self, domain):
        if domain.dns_record_id:
            deleted_records.append(domain.dns_record_id)

    from app.services.fdm.fdm_sync_service import FdmSyncService

    monkeypatch.setattr(FdmSyncService, "_delete_dns_record_for_domain", _fake_del_dns)
    # stub notifications (no Celery / end-user fan-out)
    monkeypatch.setattr(sa, "_notify_tld_migration", lambda *a, **k: None)

    asyncio.run(sa.delete_tld(tld_id=dying.id, db=db_session, current={"id": 1}))

    # FdmDomain row deleted; its subdomain DNS record was removed
    assert db_session.query(FdmDomain).filter(FdmDomain.id == dom.id).first() is None
    assert "rec-die-01" in deleted_records
    # TLD soft-deleted (terminal)
    assert dying.deleted_at is not None


@pytest.mark.database
def test_delete_non_fdm_tld_skips_fdm_subdomain_branch(db_session, monkeypatch):
    """Deleting a NON-fdm TLD must NOT enter the fdm subdomain-cleanup branch
    (the purpose guard). A spy on the per-record deleter must record zero calls
    -- this distinguishes 'branch skipped by the guard' from 'branch ran but had
    nothing to iterate' (a subscription TLD has no FdmDomain rows either way)."""
    import asyncio

    from app.api.v1.endpoints import super_admin as sa
    from app.services.fdm.fdm_sync_service import FdmSyncService

    _stub_commit(db_session, monkeypatch)
    _tld(db_session, "keep-sub.link", active=True, purpose="subscription")
    dying = _tld(db_session, "die-sub.link", active=True, purpose="subscription")
    db_session.flush()

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def find_a_record_by_name(self, name):
            return None

        async def delete_dns_record(self, rid):
            return True

    monkeypatch.setattr(
        sa, "create_dns_client", lambda provider, domain, zone_id=None: _FakeClient()
    )

    del_calls = {"n": 0}

    async def _spy_del_dns(self, domain):
        del_calls["n"] += 1

    monkeypatch.setattr(FdmSyncService, "_delete_dns_record_for_domain", _spy_del_dns)
    monkeypatch.setattr(sa, "_notify_tld_migration", lambda *a, **k: None)

    asyncio.run(sa.delete_tld(tld_id=dying.id, db=db_session, current={"id": 1}))

    assert dying.deleted_at is not None  # generic soft-delete still happens
    assert del_calls["n"] == 0, "fdm subdomain deleter must not run for a non-fdm TLD"
