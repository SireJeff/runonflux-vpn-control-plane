"""The domain pool floor must be per REGION, not the app's whole instance count.

FDM names are `{prefix}-01..99` per TLD (ArvanCloud zones cap records near 100),
so every region of every app shares 99 slots per TLD. `_spec_pool_target` used
the app's TOTAL expected instances as the floor for EACH region deployment:
ch01 (18 instances, 6 regions) claimed 18 domains per TLD per region, ~90 of the
99. Regions that lost their domains (as01/SG on 2026-10-24) or never got any
(na01/CA, row01/AR, row01/DZ, ch01/ES) were starved out of every subscription.

DB-backed (real Postgres via `db_session`).
"""

import pytest

from app.models.fdm import FdmDeployment
from app.services.fdm.fdm_sync_service import FdmSyncService

# Production topology on 2026-10-24: app -> (expected instances, active regions)
PROD_APPS = {
    "ch01": (18, ["CH", "DE", "FR", "PL", "RU", "ES"]),
    "as01": (6, ["SG", "JP", "AE"]),
    "na01": (5, ["US", "CA"]),
    "row01": (6, ["CL", "AU", "AR", "DZ"]),
}
NAMES_PER_TLD = 99  # generate_domain_names: range(1, 100)


def _deployments(db, apps, inactive=()):
    rows = {}
    for app, (_expected, regions) in apps.items():
        for region in regions:
            dep = FdmDeployment(flux_app_name=app, region=region, is_active=True)
            db.add(dep)
            rows[(app, region)] = dep
    for app, region in inactive:
        db.add(FdmDeployment(flux_app_name=app, region=region, is_active=False))
    db.flush()
    return rows


def _service(db, apps):
    svc = FdmSyncService(db)
    svc._spec_expected = {app: expected for app, (expected, _r) in apps.items()}
    return svc


def test_floor_is_split_across_the_apps_active_regions(db_session):
    apps = {"ch01": PROD_APPS["ch01"]}
    deps = _deployments(db_session, apps)
    svc = _service(db_session, apps)
    # 18 instances over 6 regions -> 3 per region (was 18)
    assert svc._spec_pool_target(deps[("ch01", "CH")], 1) == 3


def test_live_ips_above_the_floor_still_win(db_session):
    apps = {"ch01": PROD_APPS["ch01"]}
    deps = _deployments(db_session, apps)
    svc = _service(db_session, apps)
    assert svc._spec_pool_target(deps[("ch01", "CH")], 8) == 8


def test_inactive_deployments_do_not_dilute_the_floor(db_session):
    apps = {"ch01": PROD_APPS["ch01"]}
    deps = _deployments(db_session, apps, inactive=[("ch01", "IT"), ("ch01", "NL")])
    svc = _service(db_session, apps)
    assert svc._spec_pool_target(deps[("ch01", "CH")], 1) == 3


def test_floor_rounds_up_and_never_drops_below_min_pool(db_session):
    apps = {"na01": PROD_APPS["na01"], "as01": PROD_APPS["as01"]}
    deps = _deployments(db_session, apps)
    svc = _service(db_session, apps)
    assert svc._spec_pool_target(deps[("na01", "US")], 0) == 3  # ceil(5/2)
    assert svc._spec_pool_target(deps[("as01", "SG")], 0) == 2  # ceil(6/3)=2=MIN


def test_prod_topology_fits_in_one_tlds_name_space(db_session):
    """Regression for the 2026-10-24 starvation: the summed per-TLD demand of
    every region (at floor, i.e. 1 live IP each) must fit in the 99 names, with
    room left so a region that drops to zero can win its slots back."""
    deps = _deployments(db_session, PROD_APPS)
    svc = _service(db_session, PROD_APPS)
    demand = sum(svc._spec_pool_target(dep, 1) for dep in deps.values())
    assert demand <= NAMES_PER_TLD // 2, demand


@pytest.mark.parametrize("live", [0, 1, 3])
def test_no_spec_falls_back_to_min_pool(db_session, live):
    deps = _deployments(db_session, {"newapp": (0, ["XX"])})
    svc = FdmSyncService(db_session)
    svc._spec_expected = {}
    assert svc._spec_pool_target(deps[("newapp", "XX")], live) == max(
        live, svc.MIN_POOL
    )


# --- Safe rightsizing ---------------------------------------------------------
# Shrinking the over-allocated regions prunes hundreds of domains. DNS deletes
# were best-effort (errors swallowed, DB row deleted anyway), so a rate-limited
# ArvanCloud delete orphaned a record in a ~100-record zone. Prune only rows
# whose record is really gone, and only a bounded number per cycle.

import asyncio  # noqa: E402
from unittest.mock import AsyncMock, patch  # noqa: E402

from app.models.fdm import FdmDomain  # noqa: E402
from app.models.registered_tld import RegisteredTld  # noqa: E402
from app.services.fdm import fdm_sync_service as sync_mod  # noqa: E402
from app.services.fdm.arvancloud_client import ArvanCloudDnsClientError  # noqa: E402


def _tld(db):
    tld = RegisteredTld(
        domain="example.test", dns_provider="arvancloud", purpose="fdm", is_active=True
    )
    db.add(tld)
    db.flush()
    return tld


def _pool(db, dep, tld, n):
    for i in range(1, n + 1):
        db.add(
            FdmDomain(
                deployment_id=dep.id,
                tld_id=tld.id,
                domain_name=f"cdn-{i:02d}.example.test",
                domain_id=f"cdn-{i:02d}",
                dns_record_id=f"rec-{i}",
            )
        )
    db.flush()


def _count(db, dep):
    return db.query(FdmDomain).filter(FdmDomain.deployment_id == dep.id).count()


def test_rightsize_keeps_rows_whose_dns_delete_failed(db_session):
    apps = {"ch01": PROD_APPS["ch01"]}
    deps = _deployments(db_session, apps)
    dep = deps[("ch01", "CH")]
    _pool(db_session, dep, _tld(db_session), 8)
    svc = _service(db_session, apps)
    with patch.object(
        svc, "_delete_dns_record_for_domain", AsyncMock(return_value=False)
    ):
        pruned = asyncio.run(svc._rightsize_domain_pool(dep, 1))
    assert pruned == 0
    assert _count(db_session, dep) == 8


def test_rightsize_prunes_a_bounded_number_per_cycle(db_session, monkeypatch):
    monkeypatch.setattr(
        sync_mod.settings, "FDM_RIGHTSIZE_MAX_PRUNE_PER_CYCLE", 4, raising=False
    )
    apps = {"ch01": PROD_APPS["ch01"]}
    deps = _deployments(db_session, apps)
    dep = deps[("ch01", "CH")]
    _pool(db_session, dep, _tld(db_session), 12)  # target 3 -> 9 excess
    svc = _service(db_session, apps)
    with patch.object(
        svc, "_delete_dns_record_for_domain", AsyncMock(return_value=True)
    ):
        assert asyncio.run(svc._rightsize_domain_pool(dep, 1)) == 4
        assert _count(db_session, dep) == 8
        assert asyncio.run(svc._rightsize_domain_pool(dep, 1)) == 4
        assert asyncio.run(svc._rightsize_domain_pool(dep, 1)) == 1
    assert _count(db_session, dep) == 3


class _FakeDns:
    def __init__(self, exc=None):
        self.exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def delete_dns_record(self, record_id):
        if self.exc:
            raise self.exc


@pytest.mark.parametrize(
    "exc, expected",
    [
        (None, True),
        (ArvanCloudDnsClientError("gone", status_code=404), True),
        (ArvanCloudDnsClientError("rate limited", status_code=429), False),
        (RuntimeError("network"), False),
    ],
)
def test_delete_dns_record_reports_whether_the_record_is_gone(
    db_session, exc, expected
):
    tld = _tld(db_session)
    dom = FdmDomain(
        deployment_id=None,
        tld_id=tld.id,
        domain_name="x-01.example.test",
        domain_id="x-01",
        dns_record_id="rec-x",
    )
    svc = FdmSyncService(db_session)
    with patch.object(sync_mod, "create_dns_client", return_value=_FakeDns(exc)):
        assert asyncio.run(svc._delete_dns_record_for_domain(dom)) is expected


def test_delete_dns_record_without_a_record_id_counts_as_gone(db_session):
    dom = FdmDomain(
        domain_name="y-01.example.test", domain_id="y-01", dns_record_id=None
    )
    assert (
        asyncio.run(FdmSyncService(db_session)._delete_dns_record_for_domain(dom))
        is True
    )
