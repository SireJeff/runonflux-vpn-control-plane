"""Phase 4.7c: sync_deployment's discovery call site must pass the
deployment's own health_check_port through to the discovery cache lookup,
matching _prewarm_discovery_cache's (Phase 4.6) port-aware cache-key
convention -- otherwise the two never agree on a cache key for any
deployment whose health_check_port isn't 443, silently defeating Phase
4.6's one-discovery-call-per-app-per-cycle guarantee for that app.

Uses the plain top-level import (mirrors test_fdm_phase4_6_bounded_concurrency.py
and test_fdm_phase4_discovery_cache.py), NOT the importlib.util swap trick used
by test_fdm_sync_lifecycle.py -- that trick is specific to a sibling-collision
history this file doesn't share.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import app.services.fdm.fdm_sync_service as _fdm

FdmSyncService = _fdm.FdmSyncService
_DiscoveryResult = _fdm._DiscoveryResult


def _run(coro):
    return asyncio.run(coro)


def test_sync_deployment_passes_health_check_port_to_discovery():
    """Phase 4.7c: sync_deployment must look up the discovery cache using
    deployment.health_check_port (falling back to 443), not the unused
    protocol_port=443 default on _discover_instances.

    The 6 downstream patches (_filter_ips_by_region through
    _alert_dns_dark_tlds) mirror test_fdm_phase4_discovery_cache.py's
    test_healthy_sync_of_gapped_app_stays_success_with_spec_gap_in_errors --
    they let sync_deployment's success path complete cleanly without a real
    DB, so this test can focus on the one thing it actually checks: the
    args _get_cached_instances was called with."""
    dep = MagicMock()
    dep.flux_app_name = "ssh01"
    dep.region = "DE"  # non-XX -> skips the ProtocolInstance auto-detect branch
    dep.health_check_port = 8443

    mock_db = MagicMock()
    service = FdmSyncService(mock_db)
    domains = [MagicMock()]

    discovery_calls = []

    async def fake_get_cached(self, app_name, port):
        discovery_calls.append((app_name, port))
        return _DiscoveryResult(["1.1.1.1"], ["1.1.1.1"], ok=True, error=None)

    with patch.object(
        FdmSyncService, "_get_cached_instances", new=fake_get_cached
    ), patch.object(
        FdmSyncService, "_filter_ips_by_region", new=AsyncMock(return_value=["1.1.1.1"])
    ), patch.object(
        FdmSyncService, "_manage_domain_lifecycle", new=AsyncMock()
    ), patch.object(
        FdmSyncService, "_ensure_domains_exist", new=MagicMock(return_value=domains)
    ), patch.object(
        FdmSyncService,
        "_update_dns_records_v2",
        new=AsyncMock(return_value=(len(domains), [])),
    ), patch.object(
        FdmSyncService, "_rightsize_domain_pool", new=AsyncMock()
    ), patch.object(
        FdmSyncService, "_alert_dns_dark_tlds", new=AsyncMock()
    ):
        _run(service.sync_deployment(dep))

    assert discovery_calls == [("ssh01", 8443)], (
        f"expected _get_cached_instances called with the deployment's own "
        f"health_check_port (8443), got {discovery_calls}"
    )


def test_prewarm_then_sync_deployment_share_one_discovery_call():
    """Phase 4.7c end-to-end proof: for a deployment whose health_check_port
    != 443, _prewarm_discovery_cache (Phase 4.6) and sync_deployment's own
    discovery lookup must land on the SAME cache key -- proving the Phase
    4.6 cache-hit guarantee (one discovery call per app per cycle) actually
    holds for non-443 deployments, not just that an argument value changed.

    Uses a REAL service._discovery_cache dict (not mocked) and mocks only at
    the FluxDiscoveryService boundary -- mocking _get_cached_instances itself
    would make the 'called exactly once' assertion below vacuous, since that
    is the exact layer under test."""
    dep = MagicMock()
    dep.flux_app_name = "ssh01"
    dep.region = "DE"
    dep.health_check_port = 8443

    mock_db = MagicMock()
    service = FdmSyncService(mock_db)  # real self._discovery_cache dict

    domains = [MagicMock()]
    inst = AsyncMock()
    inst.get_app_instances = AsyncMock(return_value=(["1.1.1.1"], ["1.1.1.1"]))
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=inst)
    cm.__aexit__ = AsyncMock(return_value=None)

    with patch.object(_fdm, "FluxDiscoveryService", return_value=cm), patch.object(
        FdmSyncService, "_filter_ips_by_region", new=AsyncMock(return_value=["1.1.1.1"])
    ), patch.object(
        FdmSyncService, "_manage_domain_lifecycle", new=AsyncMock()
    ), patch.object(
        FdmSyncService, "_ensure_domains_exist", new=MagicMock(return_value=domains)
    ), patch.object(
        FdmSyncService,
        "_update_dns_records_v2",
        new=AsyncMock(return_value=(len(domains), [])),
    ), patch.object(
        FdmSyncService, "_rightsize_domain_pool", new=AsyncMock()
    ), patch.object(
        FdmSyncService, "_alert_dns_dark_tlds", new=AsyncMock()
    ):
        _run(service._prewarm_discovery_cache([dep]))
        _run(service.sync_deployment(dep))

    assert inst.get_app_instances.await_count == 1, (
        "prewarm should populate the exact cache key sync_deployment looks "
        "up -- a 2nd call means sync_deployment missed the prewarmed entry "
        "and defeated Phase 4.6's one-call-per-app-per-cycle guarantee"
    )
