"""
DNS configuration provider.
Reads Cloudflare DNS settings from platform_settings table (authoritative)
with fallback to environment variables.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.models.platform_settings import PlatformSetting

logger = logging.getLogger(__name__)


@dataclass
class DnsConfig:
    domain: str
    zone_id: str
    api_token: str


def get_dns_config(
    db: Session,
    fallback_domain: Optional[str],
    fallback_zone_id: Optional[str],
    fallback_api_token: Optional[str],
) -> Optional[DnsConfig]:
    """
    Get DNS configuration from platform_settings with env var fallback.

    Returns:
        DnsConfig if properly configured, None if missing required fields
    """
    rows = (
        db.query(PlatformSetting)
        .filter(PlatformSetting.key.in_(["cloudflare_domain", "cloudflare_zone_id"]))
        .all()
    )
    settings_map = {row.key: row.value for row in rows}

    domain = settings_map.get("cloudflare_domain") or fallback_domain
    zone_id = settings_map.get("cloudflare_zone_id") or fallback_zone_id
    api_token = fallback_api_token

    if not domain or not zone_id or not api_token:
        logger.error(
            f"Missing DNS config: domain={'SET' if domain else 'MISSING'}, "
            f"zone_id={'SET' if zone_id else 'MISSING'}, "
            f"api_token={'SET' if api_token else 'MISSING'}"
        )
        return None

    return DnsConfig(domain=domain, zone_id=zone_id, api_token=api_token)
