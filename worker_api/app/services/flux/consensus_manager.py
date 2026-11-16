"""
Flux Consensus Manager

Aggregates responses from multiple Flux nodes to find consensus.
This addresses the issue where individual nodes may have stale or inconsistent data.

Consensus Algorithm:
1. Query multiple nodes in parallel
2. Aggregate responses
3. Apply consensus rules:
   - IP consensus: Most frequently returned IP wins
   - Status consensus: "active" present in any response = active
   - Owner consensus: Match across responses
4. Return null if insufficient consensus (triggers fallback)

Usage:
    consensus = ConsensusManager()
    result = await consensus.get_app_consensus("ch01", nodes[:5])
"""

import asyncio
import logging
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.services.flux.node_client import FluxNodeClient, FluxNodeClientException
from app.services.flux.node_discovery import FluxNode

logger = logging.getLogger(__name__)


class ConsensusResult:
    """
    Result of a consensus query.

    Attributes:
        app_name: Application name
        ips: List of IP addresses where app is running
        status: App status (active, inactive, unknown)
        owner: App owner address
        instance_count: Number of running instances
        consensus_level: How many nodes agreed (e.g., "3/5")
        node_responses: Raw responses from each node
        confidence: Confidence score (0-1)
    """

    def __init__(
        self,
        app_name: str,
        ips: List[str],
        status: str = "unknown",
        owner: Optional[str] = None,
        instance_count: int = 0,
        consensus_level: str = "0/0",
        node_responses: Optional[Dict[str, Any]] = None,
        confidence: float = 0.0,
    ):
        self.app_name = app_name
        self.ips = ips
        self.status = status
        self.owner = owner
        self.instance_count = instance_count
        self.consensus_level = consensus_level
        self.node_responses = node_responses or {}
        self.confidence = confidence

    @property
    def is_active(self) -> bool:
        """Check if app is active."""
        return self.status == "active"

    @property
    def has_consensus(self) -> bool:
        """Check if consensus was achieved."""
        return self.confidence >= 0.5  # At least 50% agreement

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.app_name,
            "ip": self.ips,
            "status": self.status,
            "owner": self.owner,
            "instance_count": self.instance_count,
            "consensus_level": self.consensus_level,
            "confidence": self.confidence,
        }


class ConsensusManager:
    """
    Manages consensus queries across multiple Flux nodes.

    This class implements the consensus algorithm for determining the
    true state of an app across the Flux network.

    Algorithm:
    1. Query N nodes in parallel
    2. Collect all responses
    3. Apply consensus rules:
       - For IPs: Count occurrences, use most common
       - For status: Any "active" = active
       - For owner: Must match across responses
    4. Calculate confidence score
    5. Return ConsensusResult

    Configuration:
    - min_nodes: Minimum nodes required for consensus (default: 3)
    - quorum_ratio: Ratio of nodes that must agree (default: 0.5)
    """

    def __init__(
        self,
        min_nodes: Optional[int] = None,
        quorum_ratio: float = 0.5,
        node_client: Optional[FluxNodeClient] = None,
    ):
        """
        Initialize the Consensus Manager.

        Args:
            min_nodes: Minimum nodes required for consensus
            quorum_ratio: Ratio of nodes that must agree (0.0-1.0)
            node_client: FluxNodeClient instance (creates new if None)
        """
        configured_min_nodes_raw = getattr(settings, "FLUX_NODE_MIN_CONSENSUS", 3)
        configured_min_nodes = (
            int(configured_min_nodes_raw) if configured_min_nodes_raw else 3
        )
        self.min_nodes: int = min_nodes or configured_min_nodes
        self.quorum_ratio = max(0.0, min(1.0, quorum_ratio))
        self.node_client = node_client or FluxNodeClient()

    async def close(self):
        """Close the node client."""
        await self.node_client.close()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    # ========================================================================
    # PUBLIC API
    # ========================================================================

    async def get_app_consensus(
        self,
        app_name: str,
        nodes: List[FluxNode],
    ) -> Optional[ConsensusResult]:
        """
        Get consensus state for an app across multiple nodes.

        Args:
            app_name: Application name to query
            nodes: List of FluxNode objects to query

        Returns:
            ConsensusResult with app state, or None if insufficient consensus
        """
        if len(nodes) < self.min_nodes:
            logger.warning(
                f"Insufficient nodes for consensus: {len(nodes)} < {self.min_nodes}"
            )
            return None

        logger.info(f"Querying {len(nodes)} nodes for app {app_name}...")

        # Query all nodes in parallel
        endpoint = f"/apps/location/{app_name}"
        node_ips = [node.ip for node in nodes]

        responses = await self.node_client.query_multiple_nodes(node_ips, endpoint)

        # Process responses
        return self._analyze_app_responses(app_name, responses, len(nodes))

    async def list_apps_consensus(
        self,
        nodes: List[FluxNode],
    ) -> List[Dict[str, Any]]:
        """
        Get consensus list of all apps across multiple nodes.

        This aggregates app lists from multiple nodes and finds
        the union of all apps with their consensus states.

        Args:
            nodes: List of FluxNode objects to query

        Returns:
            List of app dictionaries with consensus data
        """
        if len(nodes) < self.min_nodes:
            logger.warning(
                f"Insufficient nodes for consensus: {len(nodes)} < {self.min_nodes}"
            )
            return []

        logger.info(f"Querying {len(nodes)} nodes for app list...")

        # Query all nodes for their app lists
        endpoint = "/apps/installedapps/"
        node_ips = [node.ip for node in nodes]

        responses = await self.node_client.query_multiple_nodes(node_ips, endpoint)

        # Aggregate and find consensus
        return self._aggregate_app_lists(responses, len(nodes))

    async def get_app_info_consensus(
        self,
        app_name: str,
        nodes: List[FluxNode],
    ) -> Optional[Dict[str, Any]]:
        """
        Get consensus detailed info for an app.

        Args:
            app_name: Application name
            nodes: List of FluxNode objects to query

        Returns:
            App info dictionary or None
        """
        if len(nodes) < self.min_nodes:
            return None

        endpoint = f"/apps/installedapps/{app_name}"
        node_ips = [node.ip for node in nodes]

        responses = await self.node_client.query_multiple_nodes(node_ips, endpoint)

        # Find the most complete response
        best_response = None
        best_score = -1

        for node_ip, response in responses.items():
            if "error" in response:
                continue

            # Score by completeness
            score = self._score_response_completeness(response)
            if score > best_score:
                best_score = score
                best_response = response

        if best_response:
            best_response["consensus_nodes"] = len(
                [r for r in responses.values() if "error" not in r]
            )

        return best_response

    # ========================================================================
    # CONSENSUS ANALYSIS
    # ========================================================================

    def _analyze_app_responses(
        self,
        app_name: str,
        responses: Dict[str, Any],
        total_nodes: int,
    ) -> Optional[ConsensusResult]:
        """
        Analyze app location responses to find consensus.

        Args:
            app_name: Application name
            responses: Dictionary mapping node IP to response
            total_nodes: Total number of nodes queried

        Returns:
            ConsensusResult or None if insufficient data
        """
        # Extract IPs from all valid responses
        all_ips = []
        node_count = 0
        status_votes = []
        owners = []

        for node_ip, response in responses.items():
            if "error" in response:
                continue

            node_count += 1

            # Extract IPs
            ips = response.get("ip", [])
            if isinstance(ips, list):
                all_ips.extend(ips)

            # Extract status
            status = response.get("status", "unknown")
            if status:
                status_votes.append(status)

            # Extract owner
            owner = response.get("owner") or response.get("zelid")
            if owner:
                owners.append(owner)

        if node_count < self.min_nodes:
            logger.warning(
                f"Insufficient valid responses: {node_count} < {self.min_nodes}"
            )
            return None

        # Find IP consensus (most common IPs)
        ip_counter = Counter(all_ips)
        consensus_ips = [ip for ip, count in ip_counter.most_common() if count >= 2]

        # If no IP has multiple votes, take unique IPs
        if not consensus_ips and all_ips:
            consensus_ips = list(set(all_ips))

        # Find status consensus
        if "active" in status_votes:
            consensus_status = "active"
        elif status_votes:
            # Use most common status
            status_counter = Counter(status_votes)
            consensus_status = status_counter.most_common(1)[0][0]
        else:
            consensus_status = "unknown"

        # Find owner consensus
        if owners:
            owner_counter = Counter(owners)
            consensus_owner = owner_counter.most_common(1)[0][0]
        else:
            consensus_owner = None

        # Calculate confidence
        # Confidence = (valid responses / total responses) * agreement ratio
        valid_ratio = node_count / total_nodes if total_nodes > 0 else 0
        ip_agreement = ip_counter.most_common(1)[0][1] / len(all_ips) if all_ips else 0
        confidence = valid_ratio * ip_agreement

        consensus_level = f"{node_count}/{total_nodes}"

        result = ConsensusResult(
            app_name=app_name,
            ips=consensus_ips,
            status=consensus_status,
            owner=consensus_owner,
            instance_count=len(consensus_ips),
            consensus_level=consensus_level,
            node_responses=responses,
            confidence=round(confidence, 2),
        )

        logger.info(
            f"Consensus for {app_name}: {len(consensus_ips)} IPs, "
            f"status={consensus_status}, confidence={confidence:.2f}"
        )

        return result

    def _aggregate_app_lists(
        self,
        responses: Dict[str, Any],
        total_nodes: int,
    ) -> List[Dict[str, Any]]:
        """
        Aggregate app lists from multiple nodes.

        Args:
            responses: Dictionary mapping node IP to response
            total_nodes: Total number of nodes queried

        Returns:
            List of unique apps with consensus data
        """
        app_data = {}  # app_name -> {ips: [], status: "", count: 0}

        for node_ip, response in responses.items():
            if "error" in response:
                continue

            # Extract apps list
            apps = response.get("data", [])
            if isinstance(apps, dict) and "apps" in apps:
                apps = apps["apps"]
            elif not isinstance(apps, list):
                apps = []

            for app in apps:
                if not isinstance(app, dict):
                    continue

                app_name = app.get("name")
                if not app_name:
                    continue

                if app_name not in app_data:
                    app_data[app_name] = {
                        "name": app_name,
                        "ips": [],
                        "status": app.get("status", "unknown"),
                        "owner": app.get("owner"),
                        "count": 0,
                    }

                # Merge IPs
                app_ips = app.get("ip", [])
                if isinstance(app_ips, list):
                    app_data[app_name]["ips"].extend(app_ips)

                # Update status if more definitive
                if app.get("status") == "active":
                    app_data[app_name]["status"] = "active"

                app_data[app_name]["count"] += 1

        # Convert to list and clean up
        result = []
        for app_name, data in app_data.items():
            # Deduplicate IPs
            data["ips"] = list(set(data["ips"]))
            # Add consensus level
            data["consensus_level"] = f"{data['count']}/{total_nodes}"
            result.append(data)

        # Sort by consensus count (most agreed apps first)
        result.sort(key=lambda x: x["count"], reverse=True)

        logger.info(f"Aggregated {len(result)} unique apps from {total_nodes} nodes")

        return result

    def _score_response_completeness(self, response: Dict[str, Any]) -> int:
        """
        Score a response by its completeness.

        Args:
            response: Response dictionary

        Returns:
            Completeness score (higher is better)
        """
        score = 0

        # Check for key fields
        if response.get("name"):
            score += 1
        if response.get("ip"):
            score += 2
        if response.get("status"):
            score += 1
        if response.get("owner"):
            score += 1
        if response.get("description"):
            score += 1
        if response.get("repotag"):
            score += 1
        if response.get("ports"):
            score += 1
        if response.get("cpu") is not None:
            score += 1
        if response.get("ram") is not None:
            score += 1
        if response.get("hdd") is not None:
            score += 1

        return score

    def is_consensus_sufficient(self, result: ConsensusResult) -> bool:
        """
        Check if a consensus result is sufficient to be trusted.

        Args:
            result: ConsensusResult to check

        Returns:
            True if consensus is sufficient
        """
        if not result:
            return False

        # Check confidence threshold
        if result.confidence < self.quorum_ratio:
            return False

        # Check minimum instance count
        if result.instance_count == 0:
            return False

        return True


def find_ip_consensus(responses: List[Dict[str, Any]]) -> List[str]:
    """
    Find consensus IPs from a list of responses.

    Utility function for simple IP consensus without full ConsensusManager.

    Args:
        responses: List of response dictionaries

    Returns:
        List of consensus IPs (most frequently appearing)
    """
    all_ips = []

    for response in responses:
        ips = response.get("ip", [])
        if isinstance(ips, list):
            all_ips.extend(ips)

    if not all_ips:
        return []

    # Count occurrences
    counter = Counter(all_ips)

    # Return IPs that appear in at least 2 responses
    return [ip for ip, count in counter.items() if count >= 2]


def find_status_consensus(responses: List[Dict[str, Any]]) -> str:
    """
    Find consensus status from a list of responses.

    Args:
        responses: List of response dictionaries

    Returns:
        Consensus status string
    """
    statuses: List[str] = [
        status
        for r in responses
        for status in [r.get("status")]
        if isinstance(status, str)
    ]

    if not statuses:
        return "unknown"

    # Any "active" means active
    if "active" in statuses:
        return "active"

    # Most common status
    counter = Counter(statuses)
    return counter.most_common(1)[0][0]
