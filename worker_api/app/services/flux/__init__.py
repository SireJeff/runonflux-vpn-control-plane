"""
FluxCloud integration services

This module provides a hybrid client for Flux operations:
- Read operations use node-first queries with consensus
- Write operations use the centralized API
- Automatic fallback when nodes fail

Main Classes:
- FluxHybridClient: Primary client for all Flux operations
- FluxCloudClient: Centralized API client (legacy, for writes only)
- NodeDiscoveryService: Node list fetching and caching
- ConsensusManager: Multi-node consensus algorithm

Migration Guide:
- Replace `FluxCloudClient` with `FluxHybridClient` for all operations
- The hybrid client automatically handles read vs write routing
- Feature flag: Set FLUX_NODE_DISCOVERY_ENABLED=false to disable node queries
"""

# Legacy API client (for write operations and fallback)
from app.services.flux.client import FluxCloudAPIException, FluxCloudClient

# Consensus manager (for multi-node queries)
from app.services.flux.consensus_manager import (
    ConsensusManager,
    ConsensusResult,
    find_ip_consensus,
    find_status_consensus,
)
from app.services.flux.health_monitor import FluxHealthMonitor

# Hybrid client (recommended - uses nodes for reads, API for writes)
from app.services.flux.hybrid_client import FluxHybridClient

# Direct node client (for low-level node access)
from app.services.flux.node_client import FluxNodeClient, FluxNodeClientException

# Node discovery (for direct node access)
from app.services.flux.node_discovery import (
    FluxNode,
    NodeDiscoveryService,
    get_node_discovery_service,
)

# Service layer (uses hybrid client internally)
from app.services.flux.node_manager import FluxNodeManager

# Resilience features
from app.services.flux.resilience import (
    CircuitBreakerConfig,
    CircuitBreakerStatus,
    CircuitState,
    FluxAPICircuitOpenError,
    FluxAPITransientError,
    RetryConfig,
)

__all__ = [
    # Primary client (use this for all operations)
    "FluxHybridClient",
    "FluxClient",  # Alias for FluxHybridClient
    # Legacy API client (for direct API access)
    "FluxCloudClient",
    "FluxCloudAPIException",
    # Node discovery
    "NodeDiscoveryService",
    "FluxNode",
    "get_node_discovery_service",
    # Direct node client
    "FluxNodeClient",
    "FluxNodeClientException",
    # Consensus
    "ConsensusManager",
    "ConsensusResult",
    "find_ip_consensus",
    "find_status_consensus",
    # Service layer
    "FluxNodeManager",
    "FluxHealthMonitor",
    # Resilience
    "FluxAPITransientError",
    "FluxAPICircuitOpenError",
    "CircuitState",
    "CircuitBreakerStatus",
    "RetryConfig",
    "CircuitBreakerConfig",
]
