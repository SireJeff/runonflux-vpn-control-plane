"""DNS provider abstraction — Cloudflare and ArvanCloud interchangeable"""

from abc import ABC, abstractmethod
from typing import Dict, Optional

from app.core.config import settings
from app.core.exceptions import ConfigurationError


class DnsProviderClient(ABC):
    """Abstract base class for DNS provider clients."""

    @abstractmethod
    async def list_dns_records(
        self,
        record_type: Optional[str] = None,
        name: Optional[str] = None,
        per_page: int = 100,
    ) -> Dict:
        ...

    @abstractmethod
    async def get_dns_record(self, record_id: str) -> Dict:
        ...

    @abstractmethod
    async def create_dns_record(self, name: str, ip: str, ttl: int = 120) -> Dict:
        ...

    @abstractmethod
    async def update_dns_record(
        self, record_id: str, name: str, ip: str, ttl: int = 120
    ) -> Dict:
        ...

    @abstractmethod
    async def delete_dns_record(self, record_id: str) -> None:
        ...

    @abstractmethod
    async def ensure_record_exists(
        self,
        name: str,
        ip: str,
        existing_record_id: Optional[str] = None,
        ttl: int = 120,
    ) -> Dict:
        ...

    @abstractmethod
    async def find_a_record_by_name(self, name: str) -> Optional[Dict]:
        ...

    async def close(self) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()


def _get_api_key(db_key: str, env_fallback: Optional[str]) -> Optional[str]:
    """Read API key from platform_settings first, fall back to env var."""
    from app.core.database import SessionLocal
    from app.models.platform_settings import PlatformSetting

    db = SessionLocal()
    try:
        row = db.query(PlatformSetting).filter(PlatformSetting.key == db_key).first()
        if row and row.value:
            return row.value
    finally:
        db.close()
    return env_fallback


def create_dns_client(
    provider: str,
    domain: str,
    zone_id: Optional[str] = None,
) -> DnsProviderClient:
    """Factory: create the right DNS client based on provider name."""
    if provider == "cloudflare":
        from .cloudflare_client import CloudflareDnsClient

        api_token = _get_api_key("cloudflare_api_token", settings.CLOUDFLARE_API_TOKEN)
        if not api_token:
            raise ConfigurationError("CLOUDFLARE_API_TOKEN not configured")
        if not zone_id:
            raise ConfigurationError("zone_id not configured for cloudflare provider")
        return CloudflareDnsClient(
            api_token=api_token,
            zone_id=zone_id,
            domain=domain,
        )
    elif provider == "arvancloud":
        from .arvancloud_client import ArvanCloudDnsClient

        api_key = _get_api_key("arvan_api_key", settings.ARVAN_API_KEY)
        if not api_key:
            raise ConfigurationError("ARVAN_API_KEY not configured")
        # For ArvanCloud, zone_id stores the zone domain (e.g., "operator4.example.invalid")
        # If zone_id not provided, fall back to domain itself
        zone_domain = zone_id or domain
        return ArvanCloudDnsClient(
            api_key=api_key,
            domain=zone_domain,
        )
    raise ConfigurationError(f"Unknown DNS provider: {provider}")
