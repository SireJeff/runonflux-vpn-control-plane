"""
Unit tests for Flux Node Client

Tests the direct node communication functionality.
"""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.services.flux.node_client import FluxNodeClient, FluxNodeClientException


@pytest.fixture
def node_client():
    """Create a FluxNodeClient instance for testing."""
    return FluxNodeClient()


@pytest.fixture
def mock_httpx_response():
    """Create a mock httpx response."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json = Mock(return_value={"status": "ok"})
    return mock_response


class TestFluxNodeClient:
    """Tests for FluxNodeClient class"""

    @pytest.mark.asyncio
    async def test_get_app_location(self, node_client, mock_httpx_response):
        """Test getting app location from a node."""
        with patch.object(node_client.client, "get", return_value=mock_httpx_response):
            result = await node_client.get_app_location("test_app", "1.2.3.4")

            assert result is not None
            assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_get_app_location_with_ips(self, node_client):
        """Test getting app location that returns IP list."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(
            return_value={
                "name": "msz109476",
                "ip": ["1.2.3.4", "5.6.7.8", "9.10.11.12"],
                "status": "active",
            }
        )

        with patch.object(node_client.client, "get", return_value=mock_response):
            result = await node_client.get_app_location("msz109476", "1.2.3.4")

            assert result["name"] == "msz109476"
            assert len(result["ip"]) == 3
            assert result["status"] == "active"

    @pytest.mark.asyncio
    async def test_get_app_location_not_found(self, node_client):
        """Test getting app location when app is not found."""
        mock_response = Mock()
        mock_response.status_code = 404

        with patch.object(node_client.client, "get", return_value=mock_response):
            result = await node_client.get_app_location("missing_app", "1.2.3.4")

            assert result["name"] is None
            assert result["ip"] == []
            assert result["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_get_app_info(self, node_client, mock_httpx_response):
        """Test getting app info from a node."""
        mock_httpx_response.json = Mock(
            return_value={
                "name": "test_app",
                "repotag": "nginx:latest",
                "ports": [80, 443],
                "cpu": 0.5,
                "ram": 512,
                "hdd": 5,
            }
        )

        with patch.object(node_client.client, "get", return_value=mock_httpx_response):
            result = await node_client.get_app_info("test_app", "1.2.3.4")

            assert result["name"] == "test_app"
            assert result["repotag"] == "nginx:latest"

    @pytest.mark.asyncio
    async def test_list_apps(self, node_client):
        """Test listing apps from a node."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(
            return_value={
                "data": [
                    {"name": "app1", "ip": ["1.2.3.4"]},
                    {"name": "app2", "ip": ["5.6.7.8"]},
                ]
            }
        )

        with patch.object(node_client.client, "get", return_value=mock_response):
            result = await node_client.list_apps("1.2.3.4")

            assert len(result) == 2
            assert result[0]["name"] == "app1"
            assert result[1]["name"] == "app2"

    @pytest.mark.asyncio
    async def test_get_app_logs(self, node_client):
        """Test getting app logs from a node."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(
            return_value={
                "logs": "Container started\nListening on port 80\nRequest received"
            }
        )

        with patch.object(node_client.client, "get", return_value=mock_response):
            result = await node_client.get_app_logs("test_app", "1.2.3.4", lines=100)

            assert "Container started" in result
            assert "Request received" in result

    @pytest.mark.asyncio
    async def test_restart_app(self, node_client):
        """Test restarting an app."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value={"status": "success"})

        with patch.object(node_client.client, "get", return_value=mock_response):
            result = await node_client.restart_app("test_app", "1.2.3.4")

            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_restart_app_failure(self, node_client):
        """Test restarting an app that fails."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value={"status": "error"})

        with patch.object(node_client.client, "get", return_value=mock_response):
            result = await node_client.restart_app("test_app", "1.2.3.4")

            assert result["success"] is False

    @pytest.mark.asyncio
    async def test_check_node_health(self, node_client):
        """Test checking node health."""
        mock_response = Mock()
        mock_response.status_code = 200

        with patch.object(node_client.client, "get", return_value=mock_response):
            result = await node_client.check_node_health("1.2.3.4")

            assert result is True

    @pytest.mark.asyncio
    async def test_check_node_health_unhealthy(self, node_client):
        """Test checking unhealthy node."""
        mock_response = Mock()
        mock_response.status_code = 503

        with patch.object(node_client.client, "get", return_value=mock_response):
            result = await node_client.check_node_health("1.2.3.4")

            assert result is False

    @pytest.mark.asyncio
    async def test_query_multiple_nodes(self, node_client):
        """Test querying multiple nodes in parallel."""

        async def mock_get(url):
            mock_response = Mock()
            mock_response.status_code = 200

            # Return different data based on IP
            if "1.2.3.4" in url:
                mock_response.json = Mock(
                    return_value={"ip": ["1.2.3.4"], "name": "app1"}
                )
            elif "5.6.7.8" in url:
                mock_response.json = Mock(
                    return_value={"ip": ["5.6.7.8"], "name": "app1"}
                )
            else:
                mock_response.json = Mock(return_value={"ip": [], "name": "app1"})

            return mock_response

        with patch.object(node_client.client, "get", side_effect=mock_get):
            result = await node_client.query_multiple_nodes(
                ["1.2.3.4", "5.6.7.8", "9.10.11.12"], "/apps/location/app1"
            )

            assert len(result) == 3
            assert "1.2.3.4" in result
            assert "5.6.7.8" in result
            assert "9.10.11.12" in result

    @pytest.mark.asyncio
    async def test_timeout_handling(self, node_client):
        """Test timeout handling."""
        from httpx import TimeoutException

        with patch.object(
            node_client.client, "get", side_effect=TimeoutException("Request timed out")
        ):
            result = await node_client.get_app_location("test_app", "1.2.3.4")

            # Should return None after retries
            assert result is None

    @pytest.mark.asyncio
    async def test_connection_error_handling(self, node_client):
        """Test connection error handling."""
        from httpx import ConnectError

        with patch.object(
            node_client.client, "get", side_effect=ConnectError("Connection failed")
        ):
            result = await node_client.get_app_location("test_app", "1.2.3.4")

            # Should return None after retries
            assert result is None


@pytest.mark.asyncio
async def test_client_context_manager():
    """Test using client as async context manager."""
    async with FluxNodeClient() as client:
        assert client is not None
        assert client.client is not None
