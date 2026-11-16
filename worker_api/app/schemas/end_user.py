"""
Pydantic schemas for End User and Internal API endpoints.
"""

from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel, Field

from app.schemas.admin_api import ProtocolConnections


class ConnectionStringsByCountry(BaseModel):
    """Connection strings grouped by country."""

    country_code: str
    country_name: str
    flag: str
    connections: Dict[str, ProtocolConnections]  # protocol -> primary + fallbacks


class UserConnectionsResponse(BaseModel):
    """All connection strings for the authenticated end user."""

    macro_region: Optional[str] = None
    countries: list[ConnectionStringsByCountry]
    last_refreshed_at: Optional[datetime] = None
    can_refresh: bool = True
    refresh_available_at: Optional[datetime] = None
    subscription_url: Optional[str] = None
    expires_at: Optional[str] = None
    # Hero-block fields (T15 redesign): let the page render sub link + dashboard
    # login + decrypted password in one call. password is plaintext decrypted
    # from admin_users.password_enc; '' for legacy users without enc storage.
    username: Optional[str] = None
    password: Optional[str] = None
    dashboard_url: Optional[str] = None


class ResetCredentialsResponse(BaseModel):
    """Result of POST /user/reset-credentials — fresh creds for the user to
    re-copy. Both password and subscription_token are rotated atomically."""

    username: str
    password: str
    subscription_url: str
    dashboard_url: str


class UsageProtocolBreakdown(BaseModel):
    """Traffic breakdown by protocol."""

    protocol: str
    bytes_total: int
    gb_total: float


class UsageRegionBreakdown(BaseModel):
    """Traffic breakdown by region."""

    region_code: str
    bytes_total: int
    gb_total: float


class UserUsageResponse(BaseModel):
    """Traffic consumption statistics for an end user."""

    total_bytes: int
    total_gb: float
    protocol_breakdown: list[UsageProtocolBreakdown]
    region_breakdown: list[UsageRegionBreakdown]


class UserProfileResponse(BaseModel):
    """End user profile information."""

    id: int
    username: str
    display_name: str | None = None
    remark: str | None = None
    status: str
    macro_region: Optional[str] = None
    subscription_url: Optional[str] = None
    expires_at: Optional[str] = None


class TrafficReportRequest(BaseModel):
    """Inbound traffic report from a VPN container.

    v1 (default): bytes_in/bytes_out are a per-cycle DELTA (Layer-1 guarded).
    v2: report_version=2 with cumulative_in/out (raw counter) + boot_id +
        instance_id; the backend computes the authoritative delta.
    """

    username: str = Field(..., min_length=1, max_length=50)
    protocol: str = Field(..., min_length=1)  # ssh/ss/vless/trojan/outline/http_proxy
    region: str = Field(..., min_length=1)
    bytes_in: int = Field(..., ge=0)
    bytes_out: int = Field(..., ge=0)
    session_duration_seconds: int = Field(default=0, ge=0)
    instance_ip: str = Field(..., min_length=1)
    # v2 authoritative-accounting fields (all optional for v1 back-compat)
    report_version: int = Field(default=1, ge=1)
    cumulative_in: Optional[int] = Field(default=None, ge=0)
    cumulative_out: Optional[int] = Field(default=None, ge=0)
    boot_id: Optional[str] = Field(default=None, max_length=64)
    instance_id: Optional[str] = Field(default=None, max_length=64)


class CredentialResponse(BaseModel):
    """Credential data returned to VPN containers for user auth validation."""

    protocol: str
    credential_data: dict


class SyncedUser(BaseModel):
    """Single user's credentials for bulk sync."""

    username: str
    credential_data: dict


class BulkSyncResponse(BaseModel):
    """All active users and their credentials for a protocol."""

    protocol: str
    users: list[SyncedUser]
    synced_at: datetime
