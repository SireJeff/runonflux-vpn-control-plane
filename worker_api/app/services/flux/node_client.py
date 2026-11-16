"""
Flux Direct Node Client

Communicates directly with Flux nodes without going through the centralized API.
This bypasses the synchronization issues where the centralized API doesn't show
the actual state of deployed apps.

Node Endpoint Reference:
- GET /apps/location/{app_name} → Get app location (IP addresses of nodes running app)
- GET /apps/installedapps/{app_name} → Get app info
- GET /apps/applog/{app_name}/{lines} → Get app logs
- GET /apps/apprestart/{app_name} → Restart app
- GET /ip → Node health check

Note: Write operations (deploy, update, delete) still require centralized API
for authentication and transaction signing.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.services.flux.node_discovery import FluxNode as _DiscoveredFluxNode

FluxNode = _DiscoveredFluxNode

logger = logging.getLogger(__name__)


class FluxNodeClientException(Exception):
    """Exception raised for Flux node client errors"""

    pass


class FluxNodeClient:
    """
    Client for direct communication with Flux nodes.

    This client queries individual Flux nodes at their public IP addresses
    on port 16127 (default). It supports both read operations (no auth required)
    and write operations (requires zelidauth authentication).

    Key difference from FluxCloudClient:
    - FluxCloudClient: Queries centralized API (api.runonflux.io)
    - FluxNodeClient: Queries individual nodes directly (node_ip:16127)

    Authentication for Write Operations:
    Some operations like app restart require authentication. Use set_auth()
    to provide zelidauth credentials obtained from DirectNodeAuthProvider or
    FluxCloudClient.

    Usage:
        client = FluxNodeClient()
        location = await client.get_app_location("ch01")
        # Returns {"ip": ["1.2.3.4", "5.6.7.8", ...], "name": "ch01"}

        # For authenticated operations
        client.set_auth("zelid=xxx&signature=yyy&loginPhrase=zzz")
        await client.restart_app("ch01", "1.2.3.4")
    """

    def __init__(
        self,
        timeout: float = 10.0,
        max_retries: int = 2,
    ):
        """
        Initialize the Flux Node Client.

        Args:
            timeout: Request timeout in seconds
            max_retries: Number of retries for failed requests
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.default_port = getattr(settings, "FLUX_NODE_API_PORT", 16127)

        # Authentication state (for write operations)
        self._zelidauth: Optional[str] = None

        # HTTP client configuration
        # Pool limits for concurrent node queries
        limits = httpx.Limits(
            max_keepalive_connections=20,
            max_connections=50,
            keepalive_expiry=30.0,
        )

        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=5.0),
            limits=limits,
        )

    def set_auth(self, zelidauth: str) -> None:
        """
        Set authentication credentials for write operations.

        The zelidauth header is required for operations like:
        - App restart (/apps/apprestart/{app})
        - App update (if supported)
        - App delete (if supported)

        Format: "zelid={address}&signature={sig}&loginPhrase={phrase}"

        Args:
            zelidauth: The zelidauth header value
        """
        self._zelidauth = zelidauth
        logger.debug("Authentication credentials set for node operations")

    def set_auth_from_provider(
        self, zelid: str, signature: str, login_phrase: str
    ) -> None:
        """
        Set authentication from individual components.

        Args:
            zelid: Flux/ZelCore wallet address
            signature: Base64-encoded signature
            login_phrase: The login phrase that was signed
        """
        from urllib.parse import quote

        self._zelidauth = (
            f"zelid={zelid}"
            f"&signature={signature}"
            f"&loginPhrase={quote(login_phrase)}"
        )
        logger.debug("Authentication credentials set from components")

    def clear_auth(self) -> None:
        """Clear authentication credentials."""
        self._zelidauth = None
        logger.debug("Authentication credentials cleared")

    def _get_auth_headers(self) -> Dict[str, str]:
        """
        Get authentication headers for requests.

        Returns:
            Dictionary with zelidauth header if authenticated, empty dict otherwise
        """
        if self._zelidauth:
            return {"zelidauth": self._zelidauth}
        return {}

    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()

    async def __aenter__(self):
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()

    # ========================================================================
    # NODE QUERIES
    # ========================================================================

    async def get_app_location(
        self,
        app_name: str,
        node_ip: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get the location (IP addresses) where an app is deployed.

        This is the primary endpoint for finding active apps.
        It returns the actual state from the Flux network, not the centralized API.

        Endpoint: GET http://{node_ip}:16127/apps/location/{app_name}

        Args:
            app_name: Application name to query
            node_ip: Specific node IP to query (optional, for targeted queries)

        Returns:
            Dictionary with:
                - name: App name
                - ip: List of IPs where app is running
                - status: App status
            Or None if query fails

        Example response:
            {
                "name": "ch01",
                "ip": ["1.2.3.4", "5.6.7.8", "9.10.11.12"],
                "status": "active"
            }
        """
        endpoint = f"/apps/location/{app_name}"

        if node_ip:
            # Query specific node
            result = await self._query_single_node(node_ip, endpoint)
            return result
        else:
            # This would require a node list - use ConsensusManager instead
            raise FluxNodeClientException(
                "node_ip required for get_app_location. "
                "Use ConsensusManager for multi-node queries."
            )

    async def get_app_info(
        self,
        app_name: str,
        node_ip: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about an app.

        Endpoint: GET http://{node_ip}:16127/apps/installedapps/{app_name}

        Args:
            app_name: Application name
            node_ip: Node IP to query

        Returns:
            Dictionary with app details or None if query fails
        """
        endpoint = f"/apps/installedapps/{app_name}"
        return await self._query_single_node(node_ip, endpoint)

    async def list_apps(
        self,
        node_ip: str,
    ) -> List[Dict[str, Any]]:
        """
        List all installed apps on a node.

        Endpoint: GET http://{node_ip}:16127/apps/installedapps/

        Args:
            node_ip: Node IP to query

        Returns:
            List of app dictionaries
        """
        endpoint = "/apps/installedapps/"
        result = await self._query_single_node(node_ip, endpoint)

        if result:
            # Handle different response formats
            if isinstance(result, list):
                return result
            elif isinstance(result, dict) and "data" in result:
                return result["data"]
            elif isinstance(result, dict):
                return [result]

        return []

    async def get_app_logs(
        self,
        app_name: str,
        node_ip: str,
        lines: int = 100,
    ) -> Optional[str]:
        """
        Get application logs from a node.

        Endpoint: GET http://{node_ip}:16127/apps/applog/{app_name}/{lines}

        Args:
            app_name: Application name
            node_ip: Node IP to query
            lines: Number of log lines to retrieve

        Returns:
            Log string or None if query fails
        """
        endpoint = f"/apps/applog/{app_name}/{lines}"
        result = await self._query_single_node(node_ip, endpoint)

        if result:
            # Extract logs from response
            if isinstance(result, str):
                return result
            elif isinstance(result, dict):
                return result.get("logs") or result.get("data") or str(result)

        return None

    async def restart_app(
        self,
        app_name: str,
        node_ip: str,
        authenticated: bool = True,
    ) -> Dict[str, Any]:
        """
        Restart an application on a node.

        WARNING: This requires write permissions and authentication.
        Most nodes require authentication for restart operations.

        Endpoint: GET http://{node_ip}:16127/apps/apprestart/{app_name}

        Args:
            app_name: Application name to restart
            node_ip: Node IP to send restart command
            authenticated: Whether to use authentication headers (default: True)

        Returns:
            Dictionary with restart result:
                {"success": bool, "message": str, "data": dict}
        """
        endpoint = f"/apps/apprestart/{app_name}"

        # Use authenticated query if credentials are available
        if authenticated and self._zelidauth:
            result = await self._query_single_node(
                node_ip, endpoint, use_auth=True, return_errors=True
            )
        else:
            result = await self._query_single_node(
                node_ip, endpoint, return_errors=True
            )

        # Normalize response
        if result and "error" not in result:
            if isinstance(result, dict):
                success = (
                    result.get("status") == "success"
                    or result.get("success") is True
                    or result.get("data", {}).get("success") is True
                )
                return {
                    "success": success,
                    "message": result.get("message")
                    or result.get("data", {}).get("message", ""),
                    "data": result,
                }
            return {"success": True, "message": "Restart initiated", "data": result}

        return {
            "success": False,
            "message": (
                result.get("error", "Unknown error")
                if isinstance(result, dict)
                else "No response"
            ),
            "data": result,
        }

    async def update_app(
        self,
        app_name: str,
        node_ip: str,
        updates: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Update an application on a node.

        NOTE: This operation may not be supported on all nodes.
        Most update operations go through the centralized API which
        handles blockchain transactions for spec changes.

        Endpoint: POST http://{node_ip}:16127/apps/update/{app_name}

        Args:
            app_name: Application name to update
            node_ip: Node IP to send update command
            updates: Dictionary of fields to update

        Returns:
            Dictionary with update result
        """
        if not self._zelidauth:
            return {
                "success": False,
                "message": "Authentication required for app updates",
                "data": None,
            }

        endpoint = f"/apps/update/{app_name}"

        # Use authenticated POST request
        result = await self._query_single_node(
            node_ip,
            endpoint,
            method="POST",
            data=updates,
            use_auth=True,
            return_errors=True,
        )

        if result and "error" not in result:
            return {
                "success": True,
                "message": "Update submitted",
                "data": result,
            }

        return {
            "success": False,
            "message": (
                result.get("error", "Update failed")
                if isinstance(result, dict)
                else "No response"
            ),
            "data": result,
        }

    async def delete_app(
        self,
        app_name: str,
        node_ip: str,
    ) -> Dict[str, Any]:
        """
        Delete an application from a node.

        NOTE: This operation may not be supported on all nodes.
        Most delete operations go through the centralized API which
        handles blockchain transactions for removal.

        Endpoint: GET/DELETE http://{node_ip}:16127/apps/delete/{app_name}

        Args:
            app_name: Application name to delete
            node_ip: Node IP to send delete command

        Returns:
            Dictionary with delete result
        """
        if not self._zelidauth:
            return {
                "success": False,
                "message": "Authentication required for app deletion",
                "data": None,
            }

        endpoint = f"/apps/delete/{app_name}"

        # Use authenticated query
        result = await self._query_single_node(
            node_ip, endpoint, use_auth=True, return_errors=True
        )

        if result and "error" not in result:
            return {
                "success": True,
                "message": "Delete initiated",
                "data": result,
            }

        return {
            "success": False,
            "message": (
                result.get("error", "Delete failed")
                if isinstance(result, dict)
                else "No response"
            ),
            "data": result,
        }

    async def get_app_owner(
        self,
        app_name: str,
        node_ip: str,
    ) -> Optional[str]:
        """
        Get the owner (zelid) of an application.

        This is useful for verifying if you own the app before
        attempting operations like restart or update.

        Endpoint: GET http://{node_ip}:16127/apps/location/{app_name}

        Args:
            app_name: Application name to check
            node_ip: Node IP to query

        Returns:
            Owner zelid or None if not found
        """
        result = await self.get_app_info(app_name, node_ip)

        if result:
            # Check various possible owner fields
            owner = (
                result.get("owner")
                or result.get("zelid")
                or result.get("data", {}).get("owner")
                or result.get("data", {}).get("zelid")
            )
            return owner

        return None

    async def get_supported_operations(
        self,
        node_ip: str,
    ) -> Dict[str, str]:
        """
        Probe a node to determine which operations are supported.

        This attempts various endpoints and reports which ones return
        successful responses (not errors).

        Args:
            node_ip: Node IP to probe

        Returns:
            Dictionary mapping operation names to availability
        """
        operations = {
            "location": "/apps/location/test",
            "installedapps": "/apps/installedapps/",
            "applog": "/apps/applog/test/1",
            "apprestart": "/apps/apprestart/test",
            "delete": "/apps/delete/test",
            "update": "/apps/update/test",
        }

        results: Dict[str, Any] = {}

        for op_name, endpoint in operations.items():
            try:
                # Try unauthenticated first
                result = await self._query_single_node(
                    node_ip, endpoint, return_errors=True
                )

                # Check if endpoint exists (even if returning error for non-existent app)
                if result and isinstance(result, dict):
                    status_code = result.get("status_code", 0)
                    # If we got a proper response (not connection error), endpoint exists
                    if (
                        status_code == 404
                        or status_code == 200
                        or status_code == 400
                        or status_code == 401
                    ):
                        results[op_name] = "exists"
                    elif "error" not in result:
                        results[op_name] = "exists"
                    else:
                        results[op_name] = "unavailable"
                else:
                    results[op_name] = "unknown"
            except Exception:
                results[op_name] = "error"

        return results

    async def check_node_health(self, node_ip: str, port: Optional[int] = None) -> bool:
        """
        Check if a node is healthy and responsive.

        Endpoint: GET http://{node_ip}:16127/ip

        Args:
            node_ip: Node IP to check
            port: Node API port (default from settings)

        Returns:
            True if node is healthy
        """
        port = port or self.default_port
        url = f"http://{node_ip}:{port}/ip"

        try:
            response = await self.client.get(url)
            return response.status_code == 200

        except Exception as e:
            logger.debug(f"Node health check failed for {node_ip}: {e}")
            return False

    async def query_multiple_nodes(
        self,
        node_ips: List[str],
        endpoint: str,
    ) -> Dict[str, Any]:
        """
        Query the same endpoint on multiple nodes in parallel.

        This is used by the ConsensusManager to get responses from
        multiple nodes and find agreement.

        Args:
            node_ips: List of node IPs to query
            endpoint: API endpoint to query (e.g., "/apps/location/ch01")

        Returns:
            Dictionary mapping node IP to response:
                {
                    "1.2.3.4": {"ip": ["..."], "name": "..."},
                    "5.6.7.8": {"ip": ["..."], "name": "..."},
                    ...
                }
        """
        import asyncio

        tasks = []
        for ip in node_ips:
            task = self._query_single_node(ip, endpoint, return_errors=True)
            tasks.append((ip, task))

        # Execute all queries concurrently
        results: Dict[str, Any] = {}
        responses = await asyncio.gather(
            *[task for _, task in tasks], return_exceptions=True
        )

        for (ip, _), response in zip(tasks, responses):
            if isinstance(response, Exception):
                results[ip] = {"error": str(response)}
            elif response is not None:
                results[ip] = response
            else:
                results[ip] = {"error": "No response"}

        return results

    # ========================================================================
    # PRIVATE METHODS
    # ========================================================================

    async def _query_single_node(
        self,
        node_ip: str,
        endpoint: str,
        return_errors: bool = False,
        use_auth: bool = False,
        method: str = "GET",
        data: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Query a single node at a specific endpoint.

        Args:
            node_ip: Node IP address
            endpoint: API endpoint path (e.g., "/apps/location/ch01")
            return_errors: Whether to return error info instead of None
            use_auth: Whether to include authentication headers
            method: HTTP method ("GET" or "POST")
            data: Request body data for POST requests

        Returns:
            Response data dictionary or None/exception on failure
        """
        url = f"http://{node_ip}:{self.default_port}{endpoint}"

        # Prepare headers
        headers = {}
        if use_auth and self._zelidauth:
            headers["zelidauth"] = self._zelidauth
            logger.debug(f"Using authentication for node {node_ip}")

        for attempt in range(self.max_retries + 1):
            try:
                logger.debug(f"Querying node {node_ip}: {endpoint} (method={method})")

                # Make request based on method
                if method.upper() == "POST":
                    if data:
                        response = await self.client.post(
                            url, json=data, headers=headers
                        )
                    else:
                        response = await self.client.post(url, headers=headers)
                else:
                    response = await self.client.get(url, headers=headers)

                if response.status_code == 200:
                    data = response.json()

                    # Log successful query
                    logger.debug(f"Node {node_ip} returned: " f"{str(data)[:100]}...")

                    return data

                elif response.status_code == 404:
                    # App not found on this node - return empty result
                    logger.debug(f"App not found on node {node_ip}")
                    return {"name": None, "ip": [], "status": "not_found"}

                elif response.status_code == 401:
                    # Authentication required/failed
                    logger.warning(f"Authentication failed for node {node_ip}")
                    if attempt == self.max_retries:
                        if return_errors:
                            return {
                                "error": "authentication_failed",
                                "status_code": response.status_code,
                            }
                        return None

                else:
                    logger.warning(
                        f"Node {node_ip} returned status {response.status_code}"
                    )

                    if attempt == self.max_retries:
                        if return_errors:
                            return {
                                "error": f"HTTP {response.status_code}",
                                "status_code": response.status_code,
                            }
                        return None

            except httpx.TimeoutException as e:
                logger.debug(f"Timeout querying node {node_ip}: {e}")
                if attempt == self.max_retries:
                    if return_errors:
                        return {"error": "timeout"}
                    return None

            except httpx.ConnectError as e:
                logger.debug(f"Connection error to node {node_ip}: {e}")
                if attempt == self.max_retries:
                    if return_errors:
                        return {"error": "connection_failed"}
                    return None

            except Exception as e:
                logger.warning(f"Error querying node {node_ip}: {e}")
                if attempt == self.max_retries:
                    if return_errors:
                        return {"error": str(e)}
                    return None

            # Wait before retry (exponential backoff)
            if attempt < self.max_retries:
                import asyncio

                await asyncio.sleep(0.5 * (2**attempt))

        return None
