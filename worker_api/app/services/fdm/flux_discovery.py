"""
Flux Discovery Service for FDM (Flux DNS Manager)

Discovers and health-checks Flux VPN instances using consensus from multiple nodes.
This service queries multiple Flux nodes to find the actual IPs where an app is running,
then verifies connectivity via TCP health checks.

Architecture:
1. Query multiple Flux nodes for app instance locations (/apps/location/{app_name})
2. Aggregate responses to find consensus IPs
3. Health check each IP via TCP connection to the specified port
4. Return all discovered IPs and healthy IPs

Usage:
    async with FluxDiscoveryService() as discovery:
        all_ips, healthy_ips = await discovery.get_app_instances("ch01", 8080)
"""

import asyncio
import logging
import socket
from collections import Counter
from typing import List, Optional, Tuple

import httpx

from app.core.config import settings
from app.services.flux.node_discovery import get_node_discovery_service

logger = logging.getLogger(__name__)


# Constants
FLUX_API_PORT = 16127
NODE_TIMEOUT = 10.0
HEALTH_CHECK_TIMEOUT = 3.0
MIN_CONSENSUS_NODES = 3


class FluxDiscoveryServiceError(Exception):
    """Base exception for Flux Discovery Service errors."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class FluxDiscoveryService:
    """
    Service for discovering Flux VPN instances using node consensus.

    This service queries multiple Flux nodes to determine the actual
    IP addresses where a specific app is deployed, then validates
    connectivity via TCP health checks.

    The consensus approach ensures accuracy even when individual nodes
    have stale or inconsistent data.
    """

    def __init__(
        self,
        flux_api_port: int = FLUX_API_PORT,
        node_timeout: float = NODE_TIMEOUT,
        health_check_timeout: float = HEALTH_CHECK_TIMEOUT,
        min_consensus_nodes: int = MIN_CONSENSUS_NODES,
    ):
        """
        Initialize the Flux Discovery Service.

        Args:
            flux_api_port: Flux node API port (default: 16127)
            node_timeout: Timeout for node queries in seconds
            health_check_timeout: Timeout for TCP health checks in seconds
            min_consensus_nodes: Minimum nodes required for consensus
        """
        self.flux_api_port = flux_api_port
        self.node_timeout = node_timeout
        self.health_check_timeout = health_check_timeout
        self.min_consensus_nodes = min_consensus_nodes

        # HTTP client for node queries
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """
        Get or create the HTTP client.

        Returns:
            Configured httpx.AsyncClient instance
        """
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.node_timeout)
        return self._client

    async def close(self) -> None:
        """Close the HTTP client connection."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - ensures client is closed."""
        await self.close()

    # ========================================================================
    # PUBLIC API
    # ========================================================================

    async def get_app_instances(
        self,
        app_name: str,
        port: int,
        nodes: Optional[List[str]] = None,
    ) -> Tuple[List[str], List[str]]:
        """
        Discover and health-check Flux app instances.

        This method:
        1. Queries multiple Flux nodes for app location
        2. Aggregates responses to find consensus IPs
        3. Performs TCP health checks on discovered IPs
        4. Returns all discovered IPs and healthy IPs

        Args:
            app_name: Flux application name (e.g., "ch01")
            port: Port to check for TCP connectivity
            nodes: List of Flux node IPs to query (default: dynamic panel from
                NodeDiscoveryService via _resolve_discovery_nodes, else the
                first max(count, 5) of FLUX_INITIAL_NODES)

        Returns:
            Tuple of (all_ips, healthy_ips) where:
                - all_ips: List of all discovered IPs (with consensus)
                - healthy_ips: List of IPs that passed TCP health check

        Raises:
            FluxDiscoveryServiceError: If discovery fails
        """
        # Use default nodes if not provided (Phase 4.2: dynamic, with static fallback)
        if nodes is None:
            nodes = await self._resolve_discovery_nodes()

        if not nodes:
            raise FluxDiscoveryServiceError(
                "No Flux nodes available for discovery. "
                "Configure FLUX_INITIAL_NODES in settings."
            )

        if len(nodes) < self.min_consensus_nodes:
            logger.warning(
                f"Fewer than {self.min_consensus_nodes} nodes provided. "
                f"Consensus may be unreliable."
            )

        logger.info(
            f"Discovering instances for app '{app_name}' "
            f"on port {port} using {len(nodes)} nodes..."
        )

        # Query all nodes for app location
        all_ips = await self._discover_app_ips(app_name, nodes)

        if not all_ips:
            logger.warning(f"No IPs discovered for app '{app_name}'")
            return [], []

        logger.info(f"Discovered {len(all_ips)} IPs for app '{app_name}': {all_ips}")

        # Health check each IP
        healthy_ips = await self._health_check_ips(all_ips, port)

        logger.info(f"Health check results: {len(healthy_ips)}/{len(all_ips)} healthy")

        return all_ips, healthy_ips

    # ========================================================================
    # PRIVATE METHODS
    # ========================================================================

    async def _resolve_discovery_nodes(self) -> List[str]:
        """Resolve the consensus node panel: dynamic healthy nodes first, static fallback.

        Panel size is governed by settings.FLUX_FDM_DISCOVERY_NODE_COUNT (default 10).
        Read via getattr-with-default so a frozen-image config.py (pre-Phase-4) without
        the attribute does not AttributeError. Never raises: on any dynamic failure or
        empty result, falls back to the static FLUX_INITIAL_NODES list. (Phase 4.2)
        """
        count = int(getattr(settings, "FLUX_FDM_DISCOVERY_NODE_COUNT", 10) or 10)
        try:
            healthy = await get_node_discovery_service().get_healthy_nodes(count=count)
            ips = [n.ip for n in healthy]
            if ips:
                logger.info(
                    f"FDM discovery: using {len(ips)} dynamic node(s) "
                    f"(FLUX_FDM_DISCOVERY_NODE_COUNT={count})"
                )
                return ips
            logger.info(
                "FDM discovery: dynamic node list empty; "
                "using static FLUX_INITIAL_NODES fallback"
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(
                f"Dynamic node discovery failed ({type(e).__name__}: {e}); "
                f"using static FLUX_INITIAL_NODES fallback"
            )
        static = list(getattr(settings, "FLUX_INITIAL_NODES", []))
        return static[: max(count, 5)]

    async def _discover_app_ips(self, app_name: str, nodes: List[str]) -> List[str]:
        """
        Discover app IPs by querying multiple Flux nodes.

        Uses consensus to find the most common IPs across node responses.

        Args:
            app_name: Application name to query
            nodes: List of Flux node IPs to query

        Returns:
            List of consensus IP addresses
        """
        await self._get_client()

        # Query all nodes in parallel
        tasks = [self._query_app_location(node_ip, app_name) for node_ip in nodes]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect all IPs from successful responses
        all_ips: List[str] = []
        successful_queries = 0

        for i, result in enumerate(results):
            if isinstance(result, BaseException):
                logger.debug(f"Node {nodes[i]} query failed: {result}")
                continue

            if result:
                all_ips.extend(result)
                successful_queries += 1

        if successful_queries < self.min_consensus_nodes:
            logger.warning(
                f"Insufficient successful queries: {successful_queries} "
                f"< {self.min_consensus_nodes}"
            )

        # Find consensus IPs (appearing in multiple responses)
        if not all_ips:
            return []

        # Count IP occurrences
        ip_counter = Counter(all_ips)

        # Return IPs that appear at least twice (consensus)
        # If no IP appears twice, return all unique IPs
        consensus_ips = [ip for ip, count in ip_counter.items() if count >= 2] or list(
            set(all_ips)
        )

        return consensus_ips

    async def _query_app_location(self, node_ip: str, app_name: str) -> List[str]:
        """
        Query a single Flux node for app location.

        Args:
            node_ip: Flux node IP address
            app_name: Application name to query

        Returns:
            List of IP addresses where the app is running
        """
        url = f"http://{node_ip}:{self.flux_api_port}/apps/location/{app_name}"

        try:
            client = await self._get_client()
            response = await client.get(url)

            if response.status_code == 404:
                # App not found on this node
                return []

            response.raise_for_status()

            data = response.json()

            # Extract IPs from response
            # Response format: {"status":"success","data":[{"ip":"1.2.3.4",...},...]}
            items = data.get("data", [])

            if isinstance(items, list):
                ips = []
                for item in items:
                    if isinstance(item, dict) and "ip" in item:
                        raw_ip = str(item["ip"])
                        ip = raw_ip.split(":")[
                            0
                        ]  # Strip port suffix from Flux API (e.g., "1.2.3.4:16127")
                        ips.append(ip)
                return ips
            else:
                logger.warning(
                    f"Unexpected response format from {node_ip}: {type(items)}"
                )
                return []

        except httpx.TimeoutException:
            logger.debug(f"Timeout querying node {node_ip}")
            return []
        except httpx.ConnectError:
            logger.debug(f"Connection error to node {node_ip}")
            return []
        except httpx.HTTPStatusError as e:
            logger.debug(f"HTTP error from {node_ip}: {e.response.status_code}")
            if e.response.status_code == 404:
                return []
            return []
        except Exception as e:
            logger.debug(f"Error querying {node_ip}: {e}")
            return []

    async def _health_check_ips(self, ips: List[str], port: int) -> List[str]:
        """
        Health check multiple IPs via TCP connection.

        Args:
            ips: List of IP addresses to check
            port: Port to connect to

        Returns:
            List of IPs that passed health check
        """
        if not ips:
            return []

        # Check all IPs concurrently
        tasks = [self._check_tcp_connection(ip, port) for ip in ips]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        healthy_ips = [
            ip
            for ip, result in zip(ips, results)
            if result is True and not isinstance(result, Exception)
        ]

        return healthy_ips

    async def _check_tcp_connection(self, ip: str, port: int) -> bool:
        """
        Check TCP connectivity to an IP:port.

        Args:
            ip: IP address to check
            port: Port to connect to

        Returns:
            True if connection succeeds, False otherwise
        """
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port), timeout=self.health_check_timeout
            )
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            return True
        except asyncio.TimeoutError:
            logger.debug(f"TCP timeout to {ip}:{port}")
            return False
        except OSError:
            logger.debug(f"TCP connection failed to {ip}:{port}")
            return False
        except Exception as e:
            logger.debug(f"TCP check error for {ip}:{port}: {e}")
            return False

    # ========================================================================
    # STATIC METHODS
    # ========================================================================

    @staticmethod
    def check_tcp_connection_sync(ip: str, port: int, timeout: float = 3.0) -> bool:
        """
        Synchronous TCP connection check.

        This is a static method for use in non-async contexts.

        Args:
            ip: IP address to check
            port: Port to connect to
            timeout: Connection timeout in seconds

        Returns:
            True if connection succeeds, False otherwise
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((ip, port))
            sock.close()
            return result == 0
        except Exception:
            return False


# Singleton instance for easy access
_instance: Optional[FluxDiscoveryService] = None


def get_flux_discovery_service() -> FluxDiscoveryService:
    """
    Get or create the singleton FluxDiscoveryService instance.

    Returns:
        Shared FluxDiscoveryService instance
    """
    global _instance
    if _instance is None:
        _instance = FluxDiscoveryService()
    return _instance
