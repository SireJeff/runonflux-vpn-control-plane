"""
Flux DNS Manager (FDM) Service Package

Provides DNS management services for FluxVPN instances:
- Cloudflare DNS API client
- Flux instance discovery
- Domain selection and load balancing
- DNS synchronization orchestration
"""

from .cloudflare_client import CloudflareDnsClient, CloudflareDnsClientError
from .dns_provider import DnsProviderClient, create_dns_client
from .fdm_domain_service import FdmDomainService
from .fdm_sync_service import FdmSyncService, FdmSyncServiceError, get_fdm_sync_service
from .flux_discovery import (
    FluxDiscoveryService,
    FluxDiscoveryServiceError,
    get_flux_discovery_service,
)

__all__ = [
    # Cloudflare DNS client
    "CloudflareDnsClient",
    "CloudflareDnsClientError",
    # DNS provider abstraction
    "DnsProviderClient",
    "create_dns_client",
    # Domain service
    "FdmDomainService",
    # Sync service
    "FdmSyncService",
    "FdmSyncServiceError",
    "get_fdm_sync_service",
    # Flux discovery
    "FluxDiscoveryService",
    "FluxDiscoveryServiceError",
    "get_flux_discovery_service",
]
