"""Which failed syncs count toward phantom-deployment deactivation.

_auto_deactivate_phantom_deployments deactivates a deployment after 3
consecutive failures. Only "discovery found instances, but none live in this
region" is a phantom. A region with live IPs that fails for another reason
(no free domain names, DNS provider down) must not be counted, or a name
shortage switches the region off after 30 minutes (2026-10-24: ES, SG, CA, AR
and DZ were failing with "No domains available" every cycle)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.services.fdm.fdm_sync_service import FdmSyncService

IPS = ["1.1.1.1", "2.2.2.2"]


@pytest.fixture(autouse=True)
def _gates_off(monkeypatch):
    monkeypatch.setattr(settings, "FDM_LIVENESS_ENABLED", False)
    monkeypatch.setattr(settings, "FDM_IRAN_REACH_ENABLED", False)


def _sync(region_ips, domains, dns_result=(0, [])):
    svc = FdmSyncService(MagicMock())
    dep = MagicMock(id=1, flux_app_name="ch01", region="ES", consecutive_failures=2)
    with patch.object(
        svc, "_discover_instances", new_callable=AsyncMock, return_value=(IPS, IPS)
    ), patch.object(
        svc, "_filter_ips_by_region", new_callable=AsyncMock, return_value=region_ips
    ), patch.object(
        svc, "_manage_domain_lifecycle", new_callable=AsyncMock
    ), patch.object(
        svc, "_ensure_domains_exist", return_value=domains
    ), patch.object(
        svc,
        "_update_dns_records_v2",
        new_callable=AsyncMock,
        return_value=dns_result,
    ), patch.object(
        svc, "_alert_dns_dark_tlds", new_callable=AsyncMock
    ), patch.object(
        svc, "_inject_spec_gap_into_log", new_callable=MagicMock
    ):
        log = asyncio.run(svc.sync_deployment(dep))
    return log, dep


def test_no_live_ip_in_region_counts_as_a_phantom_failure():
    log, dep = _sync(region_ips=[], domains=[])
    assert log.status == "failed"
    assert dep.consecutive_failures == 3


def test_live_region_without_domain_names_is_not_a_phantom():
    log, dep = _sync(region_ips=["1.1.1.1"], domains=[])
    assert log.status == "failed"
    assert dep.consecutive_failures == 2


def test_live_region_whose_dns_updates_all_failed_is_not_a_phantom():
    domains = [MagicMock(), MagicMock()]
    dns_errors = [{"step": "dns", "error": "provider down"}]
    log, dep = _sync(
        region_ips=["1.1.1.1"], domains=domains, dns_result=(0, dns_errors)
    )
    assert log.status == "failed"
    assert dep.consecutive_failures == 2
