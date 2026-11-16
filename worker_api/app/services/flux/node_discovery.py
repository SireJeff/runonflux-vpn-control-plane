"""
Flux Node Discovery Service

Fetches and caches Flux node lists with health checking.
This service provides the foundation for node-first queries in the hybrid client.

Architecture:
1. Fetch initial node list from centralized API (/flux_node_list endpoint)
2. Cache nodes for 24 hours (configurable)
3. Health check each node via /ip endpoint
4. Return only healthy nodes for queries
5. Refresh daily via Celery task

This addresses the issue where centralized API doesn't show actual app state.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class FluxNode:
    """
    Represents a Flux node with health status.

    Attributes:
        ip: Node IP address
        port: API port (default 16127)
        tier: Node tier (Cumulus, Nimbus, Stratus, CumulusExtended)
        geolocation: Node geolocation (e.g., "acNA_US_Missouri")
        is_healthy: Health check status
        last_checked: Timestamp of last health check
        response_time_ms: Last health check response time
        failures: Number of consecutive health check failures
    """

    ip: str
    port: int = 16127
    tier: str = "Unknown"
    geolocation: str = "Unknown"
    is_healthy: bool = True
    last_checked: Optional[datetime] = None
    response_time_ms: Optional[float] = None
    failures: int = 0

    @property
    def base_url(self) -> str:
        """Get the base URL for this node."""
        return f"http://{self.ip}:{self.port}"

    @property
    def identifier(self) -> str:
        """Get unique identifier for this node."""
        return f"{self.ip}:{self.port}"

    def mark_healthy(self, response_time_ms: float) -> None:
        """Mark node as healthy with response time."""
        self.is_healthy = True
        self.last_checked = datetime.now()
        self.response_time_ms = response_time_ms
        self.failures = 0

    def mark_unhealthy(self) -> None:
        """Mark node as unhealthy and increment failure count."""
        self.is_healthy = False
        self.last_checked = datetime.now()
        self.failures += 1


@dataclass
class NodeCache:
    """
    Cache for Flux nodes with TTL.

    Attributes:
        nodes: Dictionary mapping node identifier to FluxNode
        last_refresh: Timestamp of last cache refresh
        ttl_hours: Cache TTL in hours
    """

    nodes: Dict[str, FluxNode] = field(default_factory=dict)
    last_refresh: Optional[datetime] = None
    ttl_hours: int = 24

    def is_expired(self) -> bool:
        """Check if cache has expired."""
        if self.last_refresh is None:
            return True

        expiry_time = self.last_refresh + timedelta(hours=self.ttl_hours)
        return datetime.now() > expiry_time

    def get_healthy_nodes(self) -> List[FluxNode]:
        """Get list of healthy nodes."""
        return [node for node in self.nodes.values() if node.is_healthy]

    def get_all_nodes(self) -> List[FluxNode]:
        """Get list of all nodes."""
        return list(self.nodes.values())

    def get_node(self, ip: str, port: int = 16127) -> Optional[FluxNode]:
        """Get a specific node by IP and port."""
        identifier = f"{ip}:{port}"
        return self.nodes.get(identifier)

    def add_or_update_node(self, node: FluxNode) -> None:
        """Add or update a node in the cache."""
        self.nodes[node.identifier] = node

    def remove_node(self, ip: str, port: int = 16127) -> None:
        """Remove a node from the cache."""
        identifier = f"{ip}:{port}"
        self.nodes.pop(identifier, None)

    def update_refresh_time(self) -> None:
        """Update the last refresh timestamp."""
        self.last_refresh = datetime.now()

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        healthy_count = len(self.get_healthy_nodes())
        total_count = len(self.nodes)

        return {
            "total_nodes": total_count,
            "healthy_nodes": healthy_count,
            "unhealthy_nodes": total_count - healthy_count,
            "last_refresh": (
                self.last_refresh.isoformat() if self.last_refresh else None
            ),
            "is_expired": self.is_expired(),
        }


class NodeDiscoveryService:
    """
    Service for discovering and managing Flux nodes.

    This service handles:
    1. Fetching node lists from the centralized Flux API
    2. Caching nodes with configurable TTL
    3. Health checking nodes
    4. Providing healthy nodes for queries

    Usage:
        discovery = NodeDiscoveryService()
        nodes = await discovery.get_healthy_nodes()
        # Use nodes for consensus queries
    """

    def __init__(
        self,
        cache_ttl_hours: Optional[int] = None,
        api_url: Optional[str] = None,
        initial_nodes: Optional[List[str]] = None,
        health_check_timeout: float = 5.0,
    ):
        """
        Initialize the Node Discovery Service.

        Args:
            cache_ttl_hours: Cache TTL in hours (default from settings)
            api_url: Flux API URL (default from settings)
            initial_nodes: Initial static list of node IPs (fallback)
            health_check_timeout: Timeout for node health checks
        """
        self.cache_ttl_hours = int(
            cache_ttl_hours or getattr(settings, "FLUX_NODE_CACHE_TTL_HOURS", 24) or 24
        )
        configured_api_url = (
            api_url
            or getattr(settings, "FLUX_API_URL", "https://api.runonflux.io")
            or "https://api.runonflux.io"
        )
        self.api_url = str(configured_api_url).rstrip("/")
        self.health_check_timeout = health_check_timeout

        # Initialize cache
        self._cache = NodeCache(ttl_hours=self.cache_ttl_hours)

        # Static fallback nodes (from settings or defaults)
        self._static_nodes = initial_nodes or getattr(
            settings,
            "FLUX_INITIAL_NODES",
            [
                "65.108.35.59",
                "65.21.237.11",
                "65.108.166.14",
                "135.181.207.122",
                "167.86.84.37",
            ],
        )

        # HTTP client for health checks
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.health_check_timeout)
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    # ========================================================================
    # PUBLIC API
    # ========================================================================

    async def get_healthy_nodes(
        self,
        force_refresh: bool = False,
        count: Optional[int] = None,
    ) -> List[FluxNode]:
        """
        Get a list of healthy Flux nodes.

        Args:
            force_refresh: Force cache refresh even if not expired
            count: Maximum number of nodes to return (None for all)

        Returns:
            List of healthy Flux nodes
        """
        # Check if we need to refresh the cache
        if force_refresh or self._cache.is_expired():
            logger.info("Node cache expired or force refresh requested, refreshing...")
            await self.refresh_cache()

        # Get healthy nodes
        healthy_nodes = self._cache.get_healthy_nodes()

        if not healthy_nodes:
            logger.warning("No healthy nodes in cache, attempting emergency refresh...")
            await self.refresh_cache()
            healthy_nodes = self._cache.get_healthy_nodes()

        # If still no healthy nodes, use static fallback
        if not healthy_nodes and self._static_nodes:
            logger.warning(
                "Still no healthy nodes after refresh, using static fallback"
            )
            healthy_nodes = await self._initialize_static_nodes()

        # Limit count if requested
        if count and len(healthy_nodes) > count:
            healthy_nodes = healthy_nodes[:count]

        logger.info(f"Returning {len(healthy_nodes)} healthy nodes")
        return healthy_nodes

    async def get_all_nodes(self, force_refresh: bool = False) -> List[FluxNode]:
        """
        Get all nodes (healthy and unhealthy).

        Args:
            force_refresh: Force cache refresh even if not expired

        Returns:
            List of all Flux nodes
        """
        if force_refresh or self._cache.is_expired():
            await self.refresh_cache()

        return self._cache.get_all_nodes()

    async def refresh_cache(self) -> Dict[str, Any]:
        """
        Refresh the node cache from the Flux API.

        This method:
        1. Fetches the node list from the centralized API
        2. Parses node information
        3. Performs health checks on all nodes
        4. Updates the cache

        Returns:
            Statistics about the refresh operation
        """
        logger.info("Refreshing Flux node cache...")

        start_time = time.time()

        # Fetch node list from API
        nodes_data = await self._fetch_node_list_from_api()

        if not nodes_data:
            logger.warning("Failed to fetch nodes from API, using static fallback")
            static_nodes = await self._initialize_static_nodes()
            node_dict = {node.identifier: node for node in static_nodes}
        else:
            # Parse nodes from API response
            node_dict = {}
            for node_info in nodes_data:
                node = self._parse_node_info(node_info)
                if node:
                    node_dict[node.identifier] = node

        # Perform health checks
        if node_dict:
            await self._health_check_nodes(list(node_dict.values()))

        # Update cache
        self._cache.nodes = node_dict
        self._cache.update_refresh_time()

        elapsed = time.time() - start_time
        stats = self._cache.get_stats()
        stats["refresh_time_seconds"] = round(elapsed, 2)

        logger.info(
            f"Node cache refreshed: {stats['healthy_nodes']}/{stats['total_nodes']} healthy "
            f"in {elapsed:.2f}s"
        )

        return stats

    async def health_check_node(self, ip: str, port: int = 16127) -> bool:
        """
        Health check a specific node.

        Args:
            ip: Node IP address
            port: Node API port

        Returns:
            True if node is healthy, False otherwise
        """
        node = self._cache.get_node(ip, port)
        if not node:
            # Create temporary node for check
            node = FluxNode(ip=ip, port=port)

        return await self._check_node_health(node)

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        return self._cache.get_stats()

    # ========================================================================
    # PRIVATE METHODS
    # ========================================================================

    async def _fetch_node_list_from_api(self) -> List[Dict]:
        """
        Fetch node list from the centralized Flux API.

        Returns:
            List of node information dictionaries
        """
        url = f"{self.api_url}/flux_node_list"

        try:
            client = self._get_client()
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()

            data = response.json()

            # Handle different response formats
            if isinstance(data, dict):
                # Look for data field
                nodes = data.get("data", [])
            elif isinstance(data, list):
                nodes = data
            else:
                nodes = []

            logger.info(f"Fetched {len(nodes)} nodes from API")
            return nodes

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching nodes: {e.response.status_code}")
            return []
        except httpx.TimeoutException:
            logger.error("Timeout fetching nodes from API")
            return []
        except Exception as e:
            logger.error(f"Error fetching nodes from API: {e}")
            return []

    async def _initialize_static_nodes(self) -> List[FluxNode]:
        """
        Initialize static fallback nodes.

        Returns:
            List of FluxNode objects from static configuration
        """
        nodes = []
        for ip in self._static_nodes:
            node = FluxNode(
                ip=ip,
                port=getattr(settings, "FLUX_NODE_API_PORT", 16127),
                tier="Unknown",
                geolocation="Static",
                is_healthy=True,  # Assume healthy until checked
            )
            nodes.append(node)

        logger.info(f"Initialized {len(nodes)} static fallback nodes")
        return nodes

    def _parse_node_info(self, node_info: Dict) -> Optional[FluxNode]:
        """
        Parse node information from API response.

        Args:
            node_info: Dictionary with node information

        Returns:
            FluxNode object or None if parsing fails
        """
        try:
            # Extract IP address (various field names possible)
            ip = (
                node_info.get("ip")
                or node_info.get("IP")
                or node_info.get("ip_address")
                or node_info.get("public_ip")
                or node_info.get("node_ip")
            )

            if not ip:
                logger.warning(f"Node info missing IP: {node_info}")
                return None

            # Extract other information
            tier = node_info.get("tier", node_info.get("node_tier", "Unknown"))
            geo = node_info.get("geolocation", node_info.get("location", "Unknown"))

            # Create FluxNode object
            node = FluxNode(
                ip=ip,
                port=getattr(settings, "FLUX_NODE_API_PORT", 16127),
                tier=tier,
                geolocation=geo,
                is_healthy=True,  # Assume healthy until checked
            )

            return node

        except Exception as e:
            logger.warning(f"Error parsing node info: {e}")
            return None

    async def _health_check_nodes(self, nodes: List[FluxNode]) -> None:
        """
        Health check multiple nodes concurrently.

        Args:
            nodes: List of FluxNode objects to check
        """
        if not nodes:
            return

        logger.info(f"Health checking {len(nodes)} nodes...")

        # Execute concurrently with limited concurrency
        # to avoid overwhelming the network
        semaphore = asyncio.Semaphore(10)  # Max 10 concurrent checks

        async def checked_task(node: FluxNode) -> bool:
            async with semaphore:
                return await self._check_node_health(node)

        results = await asyncio.gather(
            *[checked_task(node) for node in nodes], return_exceptions=False
        )

        healthy_count = sum(1 for r in results if r)
        logger.info(f"Health check complete: {healthy_count}/{len(nodes)} healthy")

    async def _check_node_health(self, node: FluxNode) -> bool:
        """
        Health check a single node via the /apps/location endpoint.

        Note: The /ip endpoint doesn't exist on Flux nodes.
        We use /apps/location with a test app name instead.

        Args:
            node: FluxNode to check

        Returns:
            True if node is healthy, False otherwise
        """
        # Use /apps/location/{test} as health check endpoint
        # This endpoint exists on all Flux nodes and responds even if app doesn't exist
        url = f"{node.base_url}/apps/location/_health_check_test_"

        try:
            client = self._get_client()
            start_time = time.time()

            response = await client.get(url, timeout=self.health_check_timeout)

            response_time = (time.time() - start_time) * 1000  # Convert to ms

            # Accept 200 (app found) or 404 (app not found but node responding)
            if response.status_code in [200, 404]:
                node.mark_healthy(response_time)
                logger.debug(f"Node {node.ip} healthy ({response_time:.0f}ms)")
                return True
            else:
                node.mark_unhealthy()
                logger.warning(f"Node {node.ip} returned status {response.status_code}")
                return False

        except httpx.TimeoutException:
            node.mark_unhealthy()
            logger.warning(f"Node {node.ip} health check timeout")
            return False
        except httpx.ConnectError:
            node.mark_unhealthy()
            logger.warning(f"Node {node.ip} connection failed")
            return False
        except Exception as e:
            node.mark_unhealthy()
            logger.debug(f"Node {node.ip} health check error: {e}")
            return False


# Singleton instance for easy access
_instance: Optional[NodeDiscoveryService] = None


def get_node_discovery_service() -> NodeDiscoveryService:
    """
    Get or create the singleton NodeDiscoveryService instance.

    Returns:
        Shared NodeDiscoveryService instance
    """
    global _instance
    if _instance is None:
        _instance = NodeDiscoveryService()
    return _instance
