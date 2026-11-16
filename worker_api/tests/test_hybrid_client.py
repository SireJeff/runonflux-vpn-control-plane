"""
Unit tests for Flux Hybrid Client

Tests the unified client that combines node-first queries with API fallback.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from app.services.flux.client import FluxCloudClient
from app.services.flux.consensus_manager import ConsensusResult
from app.services.flux.hybrid_client import FluxHybridClient


@pytest.fixture
def mock_api_client():
    """Create a mock FluxCloudAPI client."""
    client = Mock(spec=FluxCloudClient)
    client.list_apps = AsyncMock(return_value={"data": [{"name": "app1"}]})
    client.get_app = AsyncMock(return_value={"name": "app1", "ip": ["1.2.3.4"]})
    client.get_app_logs = AsyncMock(return_value={"logs": "Test log"})
    client.get_app_health = AsyncMock(return_value={"status": "healthy"})
    client.deploy_app = AsyncMock(return_value={"status": "success"})
    client.deploy_multi_component_app = AsyncMock(return_value={"status": "success"})
    client.update_app = AsyncMock(return_value={"status": "success"})
    client.delete_app = AsyncMock(return_value={"status": "success"})
    client.restart_app = AsyncMock(return_value={"status": "success"})
    client.ping = AsyncMock(return_value=True)
    client.get_api_status = AsyncMock(return_value={"status": "ok"})
    # _request is async in FluxCloudClient; must be AsyncMock to avoid
    # "coroutine was never awaited" RuntimeWarning during test execution.
    client._request = AsyncMock(return_value=None)
    client.close = AsyncMock()
    return client


@pytest.fixture
def mock_consensus_result():
    """Create a mock ConsensusResult."""
    return ConsensusResult(
        app_name="msz109476",
        ips=["1.2.3.4", "5.6.7.8", "9.10.11.12", "13.14.15.16", "17.18.19.20"],
        status="active",
        instance_count=5,
        consensus_level="5/5",
        confidence=1.0,
    )


@pytest.fixture
def mock_node_discovery():
    """Create a mock NodeDiscoveryService."""
    discovery = Mock()
    discovery.get_healthy_nodes = AsyncMock(
        return_value=[
            Mock(ip="1.2.3.4"),
            Mock(ip="5.6.7.8"),
            Mock(ip="9.10.11.12"),
            Mock(ip="13.14.15.16"),
            Mock(ip="17.18.19.20"),
        ]
    )
    discovery.get_cache_stats = Mock(
        return_value={
            "total_nodes": 5,
            "healthy_nodes": 5,
            "last_refresh": datetime.now().isoformat(),
        }
    )
    return discovery


@pytest.fixture
def hybrid_client(mock_api_client):
    """Create a FluxHybridClient instance for testing."""
    client = FluxHybridClient(api_client=mock_api_client)
    client.use_nodes = True
    return client


class TestFluxHybridClient:
    """Tests for FluxHybridClient class"""

    @pytest.mark.asyncio
    async def test_list_apps_from_nodes(self, hybrid_client, mock_node_discovery):
        """Test listing apps using node consensus."""
        hybrid_client.node_discovery = mock_node_discovery

        mock_apps = [
            {"name": "app1", "ip": ["1.2.3.4"]},
            {"name": "app2", "ip": ["5.6.7.8"]},
        ]

        with patch.object(
            hybrid_client.consensus_manager,
            "list_apps_consensus",
            return_value=mock_apps,
        ):
            result = await hybrid_client.list_apps()

            assert len(result) == 2
            assert result[0]["name"] == "app1"
            assert hybrid_client.stats["node_queries"] == 1

    @pytest.mark.asyncio
    async def test_list_apps_fallback_to_api(
        self, hybrid_client, mock_node_discovery, mock_api_client
    ):
        """Test listing apps falls back to API when nodes fail."""
        hybrid_client.node_discovery = mock_node_discovery

        # Make consensus fail
        with patch.object(
            hybrid_client.consensus_manager,
            "list_apps_consensus",
            side_effect=Exception("Consensus failed"),
        ):
            await hybrid_client.list_apps()

            # Should fall back to API
            assert hybrid_client.stats["api_fallbacks"] == 1
            mock_api_client.list_apps.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_apps_nodes_disabled(self, hybrid_client, mock_api_client):
        """Test listing apps when nodes are disabled."""
        hybrid_client.use_nodes = False

        await hybrid_client.list_apps()

        # Should use API directly
        mock_api_client.list_apps.assert_called_once()
        assert hybrid_client.stats["api_writes"] == 1

    @pytest.mark.asyncio
    async def test_get_app_from_nodes(
        self, hybrid_client, mock_node_discovery, mock_consensus_result
    ):
        """Test getting app using node consensus."""
        hybrid_client.node_discovery = mock_node_discovery

        with patch.object(
            hybrid_client.consensus_manager,
            "get_app_consensus",
            return_value=mock_consensus_result,
        ):
            result = await hybrid_client.get_app("msz109476")

            assert result is not None
            assert result["name"] == "msz109476"
            assert len(result["ip"]) == 5
            assert result["status"] == "active"

    @pytest.mark.asyncio
    async def test_get_app_location_from_nodes(
        self, hybrid_client, mock_node_discovery, mock_consensus_result
    ):
        """Test getting app location using node consensus."""
        hybrid_client.node_discovery = mock_node_discovery

        with patch.object(
            hybrid_client.consensus_manager,
            "get_app_consensus",
            return_value=mock_consensus_result,
        ):
            result = await hybrid_client.get_app_location("msz109476")

            assert result is not None
            assert result["name"] == "msz109476"
            assert len(result["ip"]) == 5
            assert result["status"] == "active"
            assert result["instance_count"] == 5
            assert result["confidence"] == 1.0

    @pytest.mark.asyncio
    async def test_deploy_app(self, hybrid_client, mock_api_client):
        """Test deploying an app (always uses API)."""
        await hybrid_client.deploy_app(
            app_name="test_app",
            docker_image="nginx:latest",
            ports=[80, 443],
        )

        mock_api_client.deploy_app.assert_called_once()
        assert hybrid_client.stats["api_writes"] == 1

    @pytest.mark.asyncio
    async def test_deploy_multi_component_app(self, hybrid_client, mock_api_client):
        """Test deploying a multi-component app."""
        components = [
            {"name": "web", "repotag": "nginx:latest", "ports": [80]},
            {"name": "api", "repotag": "python:latest", "ports": [8080]},
        ]

        await hybrid_client.deploy_multi_component_app(
            app_name="test_app",
            components=components,
        )

        mock_api_client.deploy_multi_component_app.assert_called_once()
        assert hybrid_client.stats["api_writes"] == 1

    @pytest.mark.asyncio
    async def test_delete_app(self, hybrid_client, mock_api_client):
        """Test deleting an app."""
        await hybrid_client.delete_app("test_app")

        mock_api_client.delete_app.assert_called_once_with("test_app")
        assert hybrid_client.stats["api_writes"] == 1

    @pytest.mark.asyncio
    async def test_restart_app_from_node(self, hybrid_client, mock_node_discovery):
        """Test restarting an app using node (faster)."""
        hybrid_client.node_discovery = mock_node_discovery

        with patch.object(hybrid_client.node_client, "restart_app", return_value=True):
            result = await hybrid_client.restart_app("test_app")

            assert result is True

    @pytest.mark.asyncio
    async def test_restart_app_fallback_to_api(
        self, hybrid_client, mock_node_discovery, mock_api_client
    ):
        """Test restart falls back to API when node fails."""
        hybrid_client.node_discovery = mock_node_discovery

        with patch.object(hybrid_client.node_client, "restart_app", return_value=False):
            await hybrid_client.restart_app("test_app")

            # Should fall back to API
            mock_api_client.restart_app.assert_called_once_with("test_app")

    @pytest.mark.asyncio
    async def test_get_app_logs(self, hybrid_client, mock_api_client):
        """Test getting app logs (uses API)."""
        await hybrid_client.get_app_logs("test_app", lines=100)

        mock_api_client.get_app_logs.assert_called_once_with("test_app", 100)

    @pytest.mark.asyncio
    async def test_get_app_health(self, hybrid_client, mock_api_client):
        """Test getting app health."""
        await hybrid_client.get_app_health("test_app")

        mock_api_client.get_app_health.assert_called_once_with("test_app")

    @pytest.mark.asyncio
    async def test_ping(self, hybrid_client, mock_api_client):
        """Test ping."""
        result = await hybrid_client.ping()

        mock_api_client.ping.assert_called_once()
        assert result is True

    @pytest.mark.asyncio
    async def test_get_stats(self, hybrid_client):
        """Test getting usage statistics."""
        # Simulate some activity
        hybrid_client.stats["node_queries"] = 5
        hybrid_client.stats["api_fallbacks"] = 1
        hybrid_client.stats["api_writes"] = 3

        stats = hybrid_client.get_stats()

        assert stats["node_queries"] == 5
        assert stats["api_fallbacks"] == 1
        assert stats["api_writes"] == 3

    @pytest.mark.asyncio
    async def test_reset_stats(self, hybrid_client):
        """Test resetting statistics."""
        # Set some stats
        hybrid_client.stats["node_queries"] = 5
        hybrid_client.stats["api_fallbacks"] = 1

        hybrid_client.reset_stats()

        stats = hybrid_client.get_stats()

        assert stats["node_queries"] == 0
        assert stats["api_fallbacks"] == 0
        assert stats["api_writes"] == 0

    @pytest.mark.asyncio
    async def test_close(self, hybrid_client, mock_api_client):
        """Test closing the client."""
        await hybrid_client.close()

        mock_api_client.close.assert_called_once()


@pytest.mark.asyncio
async def test_hybrid_client_context_manager(mock_api_client):
    """Test using hybrid client as async context manager."""
    async with FluxHybridClient(api_client=mock_api_client) as client:
        assert client is not None
        assert client.api_client is not None


@pytest.mark.asyncio
async def test_hybrid_client_with_nodes_disabled(mock_api_client):
    """Test hybrid client with nodes disabled."""
    client = FluxHybridClient(api_client=mock_api_client, use_nodes=False)

    assert client.use_nodes is False

    # List apps should use API directly
    await client.list_apps()
    mock_api_client.list_apps.assert_called_once()

    await client.close()


@pytest.mark.asyncio
async def test_compatibility_alias(mock_api_client):
    """Test that FluxClient is an alias for FluxHybridClient."""
    from app.services.flux.hybrid_client import FluxClient

    assert FluxClient is FluxHybridClient
