"""
Flux Hybrid Client

Unified client that combines node-first queries with API fallback.
This is the main entry point for Flux operations in the FluxVPN system.

Architecture:
- Read operations: Try nodes first (with consensus) → fallback to API if needed
- Write operations: Use centralized API (requires authentication, registration)
- Node list: Fetched from NodeDiscoveryService, cached and refreshed daily

This hybrid approach addresses the synchronization issues where the centralized
API doesn't show the actual state of deployed apps.

Example:
    async with FluxHybridClient() as client:
        # Read from nodes with consensus
        apps = await client.list_apps()

        # Write via API
        await client.deploy_app(...)

Configuration:
    FLUX_NODE_DISCOVERY_ENABLED: Enable node queries (default: True)
    FLUX_NODE_MIN_CONSENSUS: Minimum nodes for consensus (default: 3)
    FLUX_NODE_CACHE_TTL_HOURS: Node cache TTL (default: 24)
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.services.flux.client import FluxCloudAPIException, FluxCloudClient
from app.services.flux.consensus_manager import (
    ConsensusManager,
    ConsensusResult,
    find_ip_consensus,
    find_status_consensus,
)
from app.services.flux.node_client import FluxNodeClient, FluxNodeClientException
from app.services.flux.node_discovery import (
    NodeDiscoveryService,
    get_node_discovery_service,
)

logger = logging.getLogger(__name__)


class FluxHybridClient:
    """
    Hybrid client for Flux operations with node-first queries.

    This client provides a unified interface for all Flux operations:
    - Read operations use node consensus when available
    - Write operations use the centralized API
    - Automatic fallback to API when nodes fail

    The client manages its own NodeDiscoveryService and ConsensusManager
    instances, ensuring fresh node lists and proper consensus.

    Usage:
        # Basic usage
        client = FluxHybridClient()
        apps = await client.list_apps()

        # With context manager
        async with FluxHybridClient() as client:
            app = await client.get_app("ch01")

        # Force API usage (feature flag)
        client = FluxHybridClient(use_nodes=False)
        apps = await client.list_apps()
    """

    def __init__(
        self,
        api_client: Optional[FluxCloudClient] = None,
        node_discovery: Optional[NodeDiscoveryService] = None,
        use_nodes: Optional[bool] = None,
    ):
        """
        Initialize the Hybrid Client.

        Args:
            api_client: FluxCloudClient for API operations (creates new if None)
            node_discovery: NodeDiscoveryService instance (uses singleton if None)
            use_nodes: Enable node queries (default from settings)
        """
        # Centralized API client (for writes and fallback)
        self.api_client = api_client or FluxCloudClient()

        # Node discovery service
        self.node_discovery = node_discovery or get_node_discovery_service()

        # Direct node client
        self.node_client = FluxNodeClient()

        # Consensus manager
        min_consensus = getattr(settings, "FLUX_NODE_MIN_CONSENSUS", 3)
        self.consensus_manager = ConsensusManager(
            min_nodes=min_consensus,
            node_client=self.node_client,
        )

        # Feature flag
        self.use_nodes = (
            use_nodes
            if use_nodes is not None
            else getattr(settings, "FLUX_NODE_DISCOVERY_ENABLED", True)
        )

        # Statistics
        self.stats = {
            "node_queries": 0,
            "api_fallbacks": 0,
            "api_writes": 0,
            "node_failures": 0,
        }

        logger.info(
            f"FluxHybridClient initialized: use_nodes={self.use_nodes}, "
            f"min_consensus={min_consensus}"
        )

    async def close(self):
        """Close all clients."""
        await self.api_client.close()
        await self.node_client.close()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    # ========================================================================
    # READ OPERATIONS (Node-First with API Fallback)
    # ========================================================================

    async def list_apps(self) -> List[Dict[str, Any]]:
        """
        List all deployed applications.

        Tries nodes first with consensus, falls back to API if needed.

        Returns:
            List of application dictionaries
        """
        if not self.use_nodes:
            self.stats["api_writes"] += 1
            return await self._list_apps_from_api()

        # Try node consensus
        self.stats["node_queries"] += 1
        try:
            nodes = await self.node_discovery.get_healthy_nodes(count=5)

            if len(nodes) >= self.consensus_manager.min_nodes:
                apps = await self.consensus_manager.list_apps_consensus(nodes)

                if apps:
                    logger.info(f"Found {len(apps)} apps via node consensus")
                    return apps

        except Exception as e:
            logger.warning(f"Node consensus failed: {e}")
            self.stats["node_failures"] += 1

        # Fallback to API
        self.stats["api_fallbacks"] += 1
        logger.info("Falling back to API for list_apps")
        return await self._list_apps_from_api()

    async def get_app(self, app_name: str) -> Optional[Dict[str, Any]]:
        """
        Get application details.

        Tries nodes first with consensus, falls back to API if needed.

        Args:
            app_name: Application name

        Returns:
            Application details dictionary or None
        """
        if not self.use_nodes:
            self.stats["api_writes"] += 1
            return await self._get_app_from_api(app_name)

        # Try node consensus
        self.stats["node_queries"] += 1
        try:
            nodes = await self.node_discovery.get_healthy_nodes(count=5)

            if len(nodes) >= self.consensus_manager.min_nodes:
                result = await self.consensus_manager.get_app_consensus(app_name, nodes)

                if result and result.has_consensus:
                    logger.info(
                        f"Found app {app_name} via node consensus: "
                        f"{len(result.ips)} IPs, status={result.status}"
                    )
                    return result.to_dict()

        except Exception as e:
            logger.warning(f"Node consensus failed for {app_name}: {e}")
            self.stats["node_failures"] += 1

        # Fallback to API
        self.stats["api_fallbacks"] += 1
        logger.info(f"Falling back to API for get_app({app_name})")
        return await self._get_app_from_api(app_name)

    async def get_app_location(self, app_name: str) -> Optional[Dict[str, Any]]:
        """
        Get the location (IP addresses) of an app.

        This is the primary method for finding active apps that the
        centralized API may not show.

        Priority:
        1. Centralized API location endpoint (/apps/location/{app}) - WORKS!
        2. Node consensus
        3. Direct node query
        4. Fallback to /apps/installedapps/{app}

        Args:
            app_name: Application name

        Returns:
            Dictionary with IPs and status, or None
        """
        # Priority 1: Try centralized API's location endpoint first (this works!)
        try:
            response = await self.api_client._request(
                "GET", f"/apps/location/{app_name}", authenticated=False
            )
            if response and response.get("data"):
                items = response["data"]
                if isinstance(items, list) and len(items) > 0:
                    # Extract IPs from the location response
                    ips = []
                    for item in items:
                        ip_with_port = item.get("ip", "")
                        # Strip port if present
                        ip = (
                            ip_with_port.split(":")[0]
                            if ":" in ip_with_port
                            else ip_with_port
                        )
                        if ip:
                            ips.append(ip)

                    return {
                        "name": app_name,
                        "ip": ips,
                        "status": "active",
                        "instance_count": len(items),
                        "source": "api_location",
                        "raw_data": items,
                    }
        except Exception as e:
            logger.debug(f"API location endpoint failed: {e}")

        if not self.use_nodes:
            # API location endpoint failed, try installedapps
            app_data = await self._get_app_from_api(app_name)
            if app_data:
                return {
                    "name": app_data.get("name", app_name),
                    "ip": app_data.get("ip", []),
                    "status": app_data.get("status", "unknown"),
                    "source": "api_installedapps",
                }
            return None

        # Try node consensus
        self.stats["node_queries"] += 1
        try:
            nodes = await self.node_discovery.get_healthy_nodes(count=5)

            if len(nodes) >= self.consensus_manager.min_nodes:
                result = await self.consensus_manager.get_app_consensus(app_name, nodes)

                if result:
                    return {
                        "name": result.app_name,
                        "ip": result.ips,
                        "status": result.status,
                        "instance_count": result.instance_count,
                        "consensus_level": result.consensus_level,
                        "confidence": result.confidence,
                    }

        except Exception as e:
            logger.warning(f"Node location query failed for {app_name}: {e}")
            self.stats["node_failures"] += 1

        # Fallback: Try direct node query if we have at least one node
        try:
            nodes = await self.node_discovery.get_healthy_nodes(count=1)
            if nodes:
                location = await self.node_client.get_app_location(
                    app_name, nodes[0].ip
                )
                if location:
                    return location
        except Exception as e:
            logger.debug(f"Direct node query failed: {e}")

        # Try centralized API's location endpoint (this works!)
        try:
            response = await self.api_client._request(
                "GET", f"/apps/location/{app_name}", authenticated=False
            )
            if response and response.get("data"):
                items = response["data"]
                if isinstance(items, list) and len(items) > 0:
                    # Extract IPs from the location response
                    ips = []
                    for item in items:
                        ip_with_port = item.get("ip", "")
                        # Strip port if present
                        ip = (
                            ip_with_port.split(":")[0]
                            if ":" in ip_with_port
                            else ip_with_port
                        )
                        if ip:
                            ips.append(ip)

                    return {
                        "name": app_name,
                        "ip": ips,
                        "status": "active",
                        "instance_count": len(items),
                        "source": "api_location",
                        "raw_data": items,
                    }
        except Exception as e:
            logger.debug(f"API location endpoint failed: {e}")

        # Final fallback to API
        self.stats["api_fallbacks"] += 1
        app_data = await self._get_app_from_api(app_name)
        if app_data:
            # Extract IPs from API response format
            return {
                "name": app_data.get("name", app_name),
                "ip": app_data.get("ip", []),
                "status": app_data.get("status", "unknown"),
                "source": "api",
            }

        return None

    async def get_app_logs(
        self,
        app_name: str,
        lines: int = 100,
    ) -> Optional[str]:
        """
        Get application logs.

        Args:
            app_name: Application name
            lines: Number of log lines

        Returns:
            Log string or None
        """
        # Logs are best fetched from API (more complete history)
        try:
            logs_response = await self.api_client.get_app_logs(app_name, lines)
            return logs_response.get("logs", "")
        except Exception as e:
            logger.warning(f"Failed to get logs from API: {e}")

            # Try node fallback
            try:
                nodes = await self.node_discovery.get_healthy_nodes(count=1)
                if nodes:
                    return await self.node_client.get_app_logs(
                        app_name, nodes[0].ip, lines
                    )
            except Exception as e2:
                logger.warning(f"Node logs fallback also failed: {e2}")

        return None

    async def get_app_health(self, app_name: str) -> Dict[str, Any]:
        """
        Check application health status.

        Args:
            app_name: Application name

        Returns:
            Health status dictionary
        """
        # Use API for health checks (more complete metrics)
        try:
            return await self.api_client.get_app_health(app_name)
        except Exception as e:
            logger.warning(f"API health check failed: {e}")

        # Fallback to node consensus
        try:
            nodes = await self.node_discovery.get_healthy_nodes(count=5)
            if len(nodes) >= self.consensus_manager.min_nodes:
                result = await self.consensus_manager.get_app_consensus(app_name, nodes)

                if result:
                    return {
                        "name": result.app_name,
                        "status": result.status,
                        "instance_count": result.instance_count,
                        "ips": result.ips,
                        "confidence": result.confidence,
                    }
        except Exception as e2:
            logger.warning(f"Node health check also failed: {e2}")

        return {
            "name": app_name,
            "status": "unknown",
            "error": "Health check failed",
        }

    # ========================================================================
    # WRITE OPERATIONS (API-Only)
    # ========================================================================

    async def deploy_app(
        self,
        app_name: str,
        docker_image: str,
        ports: List[int],
        cpu: float = 0.5,
        ram: int = 512,
        hdd: int = 5,
        tiered: bool = True,
        environment_variables: Optional[Dict[str, str]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Deploy a new application (uses centralized API).

        Write operations require authentication and transaction signing,
        so they always go through the centralized API.

        Args:
            app_name: Unique application name
            docker_image: Docker image to deploy
            ports: List of ports to expose
            cpu: CPU cores
            ram: RAM in MB
            hdd: Disk space in GB
            tiered: Deploy across all tiers
            environment_variables: Dict of environment variables

        Returns:
            Deployment response
        """
        self.stats["api_writes"] += 1
        return await self.api_client.deploy_app(
            app_name=app_name,
            docker_image=docker_image,
            ports=ports,
            cpu=cpu,
            ram=ram,
            hdd=hdd,
            tiered=tiered,
            environment_variables=environment_variables,
            **kwargs,
        )

    async def deploy_multi_component_app(
        self,
        app_name: str,
        components: List[Dict[str, Any]],
        geolocation: Optional[str] = None,
        instances: int = 3,
        expire: int = 22000,
    ) -> Dict[str, Any]:
        """
        Deploy a multi-component application (uses centralized API).

        Args:
            app_name: Unique app name
            components: List of component specs
            geolocation: Optional location constraint
            instances: Number of parallel instances
            expire: App expiration in blocks

        Returns:
            Deployment response
        """
        self.stats["api_writes"] += 1
        return await self.api_client.deploy_multi_component_app(
            app_name=app_name,
            components=components,
            geolocation=geolocation,
            instances=instances,
            expire=expire,
        )

    async def update_app(self, app_name: str, **update_params) -> Dict[str, Any]:
        """
        Update an existing application (uses centralized API).

        Args:
            app_name: Application name to update
            **update_params: Parameters to update

        Returns:
            Update response
        """
        self.stats["api_writes"] += 1
        return await self.api_client.update_app(app_name, **update_params)

    async def delete_app(self, app_name: str) -> Dict[str, Any]:
        """
        Delete an application (uses centralized API).

        Args:
            app_name: Application name to delete

        Returns:
            Deletion confirmation
        """
        self.stats["api_writes"] += 1
        return await self.api_client.delete_app(app_name)

    async def restart_app(self, app_name: str) -> bool:
        """
        Restart an application.

        First tries nodes (faster), falls back to API.

        Args:
            app_name: Application name to restart

        Returns:
            True if restart succeeded
        """
        # Try direct node restart first (faster)
        if self.use_nodes:
            try:
                nodes = await self.node_discovery.get_healthy_nodes(count=1)
                if nodes:
                    result = await self.node_client.restart_app(app_name, nodes[0].ip)
                    if result:
                        return True
            except Exception as e:
                logger.debug(f"Node restart failed: {e}")

        # Fallback to API
        self.stats["api_writes"] += 1
        try:
            response = await self.api_client.restart_app(app_name)
            return response.get("status") == "success"
        except Exception:
            return False

    async def redeploy_app(
        self,
        app_name: str,
        hard: bool = False,
    ) -> Dict[str, Any]:
        """
        Redeploy an application (uses centralized API).

        Args:
            app_name: Application name to redeploy
            hard: Force hard redeploy

        Returns:
            Redeployment response
        """
        self.stats["api_writes"] += 1
        return await self.api_client.redeploy_app(app_name, hard=hard)

    async def register_app(
        self,
        app_spec: Dict[str, Any],
        timestamp: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Register a new application (uses centralized API).

        Args:
            app_spec: Application specification
            timestamp: Unix timestamp in milliseconds

        Returns:
            Registration response
        """
        self.stats["api_writes"] += 1
        return await self.api_client.register_app(app_spec, timestamp)

    async def update_app_spec(
        self,
        app_name: str,
        app_spec: Dict[str, Any],
        timestamp: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Update an application specification (uses centralized API).

        Args:
            app_name: Application name to update
            app_spec: Updated application specification
            timestamp: Unix timestamp in milliseconds

        Returns:
            Update response
        """
        self.stats["api_writes"] += 1
        return await self.api_client.update_app_spec(app_name, app_spec, timestamp)

    # ========================================================================
    # NODE API METHODS
    # ========================================================================

    async def list_nodes(
        self, filter_params: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """List available Flux nodes (from API)."""
        return await self.api_client.list_nodes(filter_params)

    async def get_node(self, node_id: str) -> Dict[str, Any]:
        """Get details for a specific node."""
        return await self.api_client.get_node(node_id)

    async def get_pricing(self, specs: Dict[str, Any]) -> Dict[str, Any]:
        """Get pricing estimate for deployment specs."""
        return await self.api_client.get_pricing(specs)

    # ========================================================================
    # UTILITY METHODS
    # ========================================================================

    async def ping(self) -> bool:
        """Test connectivity (via API)."""
        return await self.api_client.ping()

    async def get_api_status(self) -> Dict[str, Any]:
        """Get FluxCloud API status."""
        return await self.api_client.get_api_status()

    def get_stats(self) -> Dict[str, int]:
        """Get usage statistics."""
        return self.stats.copy()

    def reset_stats(self) -> None:
        """Reset usage statistics."""
        self.stats = {
            "node_queries": 0,
            "api_fallbacks": 0,
            "api_writes": 0,
            "node_failures": 0,
        }

    # ========================================================================
    # PRIVATE METHODS (API Fallbacks)
    # ========================================================================

    async def _list_apps_from_api(self) -> List[Dict[str, Any]]:
        """Fetch app list from centralized API."""
        try:
            response: Any = await self.api_client.list_apps()
            if isinstance(response, dict):
                data = response.get("data", [])
                return data if isinstance(data, list) else []
            return response if isinstance(response, list) else []
        except FluxCloudAPIException as e:
            logger.error(f"API list_apps failed: {e}")
            return []

    async def _get_app_from_api(self, app_name: str) -> Optional[Dict[str, Any]]:
        """Fetch app details from centralized API."""
        try:
            return await self.api_client.get_app(app_name)
        except FluxCloudAPIException as e:
            logger.debug(f"API get_app({app_name}) failed: {e}")
            return None


# Compatibility aliases for easier migration
FluxClient = FluxHybridClient
