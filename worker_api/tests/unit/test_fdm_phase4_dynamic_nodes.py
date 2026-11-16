"""Phase 4.2: dynamic Flux node wiring for FDM discovery.

_resolve_discovery_nodes sources the consensus node panel from the dynamic
NodeDiscoveryService (24h cache, daily 02:00 UTC refresh, health-checked) instead
of the hardcoded first-5 of FLUX_INITIAL_NODES. Falls back to the static list on
any dynamic failure or empty result; never raises. get_app_instances(nodes=None)
is rewired to call it. (Spec: docs/superpowers/specs/2026-07-19-fdm-phase4-2-dynamic-nodes-design.md)
"""
import asyncio
import types
from unittest.mock import AsyncMock, MagicMock, patch

import app.services.fdm.flux_discovery as _fd

FluxDiscoveryService = _fd.FluxDiscoveryService


def _run(coro):
    return asyncio.run(coro)


def _nds(ips):
    """Mock get_node_discovery_service() -> object whose get_healthy_nodes awaits
    to a list of FluxNode-like objects (each exposing .ip) for the given IPs."""
    service = MagicMock()
    service.get_healthy_nodes = AsyncMock(return_value=[MagicMock(ip=ip) for ip in ips])
    return service


# --- T1 + rewire: dynamic non-empty -> dynamic IPs passed to discovery ---


def test_get_app_instances_uses_dynamic_nodes_when_available():
    """get_app_instances(nodes=None) consults the dynamic resolver and passes its
    IPs to _discover_app_ips (NOT the static FLUX_INITIAL_NODES). _discover_app_ips
    is patched so no real HTTP runs."""
    service = FluxDiscoveryService()
    dynamic = ["10.0.0.1", "10.0.0.2", "10.0.0.3"]
    fake_discover = AsyncMock(return_value=["1.1.1.1"])
    with patch.object(
        _fd, "get_node_discovery_service", return_value=_nds(dynamic)
    ), patch.object(
        FluxDiscoveryService, "_discover_app_ips", new=fake_discover
    ), patch.object(
        FluxDiscoveryService,
        "_health_check_ips",
        new=AsyncMock(return_value=["1.1.1.1"]),
    ):
        _run(service.get_app_instances("ch01", 443))
    # _discover_app_ips(app_name, nodes) -> args == ("ch01", <nodes>); AsyncMock does not bind self.
    passed_nodes = list(fake_discover.call_args.args[-1])
    assert passed_nodes == dynamic, "dynamic panel must be passed to discovery"
    assert (
        passed_nodes != list(_fd.settings.FLUX_INITIAL_NODES)[:5]
    ), "must not be the static list"


# --- T2: dynamic empty -> static fallback ---


def test_resolve_falls_back_to_static_when_dynamic_empty():
    """get_healthy_nodes returns [] -> resolver returns FLUX_INITIAL_NODES sliced
    to max(count, 5)."""
    service = FluxDiscoveryService()
    with patch.object(_fd, "get_node_discovery_service", return_value=_nds([])):
        result = _run(service._resolve_discovery_nodes())
    static = list(_fd.settings.FLUX_INITIAL_NODES)
    assert result == static[: max(10, 5)]


# --- T3: dynamic raises -> static fallback, no exception escapes ---


def test_resolve_falls_back_to_static_when_dynamic_raises():
    """get_healthy_nodes raises -> resolver returns static and does NOT propagate."""
    service = FluxDiscoveryService()
    boom = MagicMock()
    boom.get_healthy_nodes = AsyncMock(side_effect=RuntimeError("flux api down"))
    with patch.object(_fd, "get_node_discovery_service", return_value=boom):
        result = _run(service._resolve_discovery_nodes())  # must not raise
    static = list(_fd.settings.FLUX_INITIAL_NODES)
    assert result == static[: max(10, 5)]


# --- T4: count honored ---


def test_resolve_passes_configured_count_to_discovery():
    """FLUX_FDM_DISCOVERY_NODE_COUNT=7 -> get_healthy_nodes(count=7)."""
    service = FluxDiscoveryService()
    nds = _nds(["10.0.0.1"] * 7)
    with patch.object(
        _fd.settings, "FLUX_FDM_DISCOVERY_NODE_COUNT", 7, create=True
    ), patch.object(_fd, "get_node_discovery_service", return_value=nds):
        _run(service._resolve_discovery_nodes())
    nds.get_healthy_nodes.assert_awaited_once()
    _, kwargs = nds.get_healthy_nodes.call_args
    assert kwargs.get("count") == 7


# --- T5: frozen-image robustness (missing attr -> default 10, no AttributeError) ---


def test_resolve_uses_default_count_when_attr_absent():
    """A frozen-image settings WITHOUT FLUX_FDM_DISCOVERY_NODE_COUNT must not
    AttributeError; the resolver uses the default (10)."""
    service = FluxDiscoveryService()
    # Mirrors a pre-Phase-4 frozen image: settings object lacks the new attr entirely.
    frozen = types.SimpleNamespace(FLUX_INITIAL_NODES=["9.9.9.9", "8.8.8.8"])
    nds = _nds(["10.0.0.1"])
    with patch.object(_fd, "settings", frozen), patch.object(
        _fd, "get_node_discovery_service", return_value=nds
    ):
        _run(service._resolve_discovery_nodes())
    _, kwargs = nds.get_healthy_nodes.call_args
    assert kwargs.get("count") == 10, "missing attr must fall back to default 10"
