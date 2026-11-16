"""FDM sync must release every SAVEPOINT it opens, not only roll back on error.

Several FDM helpers did `savepoint = self.db.begin_nested(); try: ... except:
savepoint.rollback()`, leaving the SAVEPOINT open on every success path. In
a loop each item nests one level deeper; with 635 healthy domains
_validate_domain_ips_against_instances left a chain so deep that the next
phase's commit() hit "maximum recursion depth exceeded" (prod, 2026-10-24),
so _auto_deactivate_phantom_deployments failed every cycle.

Real Postgres: SAVEPOINT nesting is the behavior under test."""

import asyncio

import pytest

from app.core.database import SessionLocal
from app.models.fdm import FdmDeployment, FdmDomain
from app.models.ip_management import ProtocolInstance
from app.models.subscription import Protocol
from app.services.fdm.fdm_sync_service import FdmSyncService

APP = "sptest01"
PROTO_ID = 1


def _ip(i):
    return f"198.51.{100 + i // 250}.{1 + i % 250}"


@pytest.fixture
def db(tables):
    s = SessionLocal()

    def clean():
        dep_ids = [
            d.id
            for d in s.query(FdmDeployment).filter(FdmDeployment.flux_app_name == APP)
        ]
        if dep_ids:
            s.query(FdmDomain).filter(FdmDomain.deployment_id.in_(dep_ids)).delete(
                synchronize_session=False
            )
        s.query(FdmDeployment).filter(FdmDeployment.flux_app_name == APP).delete()
        s.query(ProtocolInstance).filter(ProtocolInstance.flux_app_name == APP).delete()
        s.commit()

    clean()
    if s.get(Protocol, PROTO_ID) is None:
        s.add(Protocol(id=PROTO_ID, name="sptest-ssh", slug="sptest-ssh"))
        s.commit()
    yield s
    s.rollback()
    clean()
    s.close()


def _seed(db, n):
    dep = FdmDeployment(flux_app_name=APP, region="DE", base_domain="sp.test")
    db.add(dep)
    db.flush()
    for i in range(n):
        db.add(
            ProtocolInstance(
                protocol_id=PROTO_ID,
                flux_app_name=APP,
                component_name="multi-protocol",
                instance_number=i + 1,
                ip_address=_ip(i),
                country_code="DE",
                country_name="Germany",
                is_active=True,
            )
        )
        db.add(
            FdmDomain(
                deployment_id=dep.id,
                domain_name=f"sp{i}.sp.test",
                domain_id=f"sp{i}",
                current_ip=_ip(i),
                health_status="healthy",
            )
        )
    db.commit()
    return dep


def _svc(db):
    return FdmSyncService(db)


def test_validate_domain_ips_releases_its_savepoints(db):
    _seed(db, 3)
    asyncio.run(_svc(db)._validate_domain_ips_against_instances())
    assert not db.in_nested_transaction()


def test_hundreds_of_healthy_domains_then_commit_does_not_overflow(db):
    # The prod failure: validate, then the next phase commits.
    _seed(db, 500)
    asyncio.run(_svc(db)._validate_domain_ips_against_instances())
    db.commit()  # raised RecursionError before the fix


def test_filter_ips_by_region_releases_its_savepoints(db):
    _seed(db, 3)
    out = asyncio.run(_svc(db)._filter_ips_by_region([_ip(0), _ip(1)], "DE"))
    assert sorted(out) == sorted([_ip(0), _ip(1)])
    assert not db.in_nested_transaction()


def test_resolve_ip_region_releases_its_savepoint(db):
    _seed(db, 1)
    assert asyncio.run(_svc(db)._resolve_ip_region(_ip(0))) == "DE"
    assert not db.in_nested_transaction()


def test_ensure_pi_for_fdm_domains_releases_its_savepoints(db):
    _seed(db, 3)
    asyncio.run(_svc(db)._ensure_pi_for_fdm_domains())
    assert not db.in_nested_transaction()


def test_get_or_create_instance_releases_its_savepoint(db):
    dep = _seed(db, 1)
    inst = _svc(db)._get_or_create_instance(
        deployment=dep, ip=_ip(0), instance_number=1
    )
    assert inst is not None
    assert not db.in_nested_transaction()


def test_create_pi_row_for_ip_releases_its_savepoint(db):
    _seed(db, 1)
    _svc(db)._create_pi_row_for_ip(_ip(0), "DE", "Germany", None)
    assert not db.in_nested_transaction()
