"""
Super Admin API schemas for FluxVPN Reseller Platform
Request/response validation for admin management, wire orders, platform settings, analytics
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Decimal fields in REQUEST schemas stay as Decimal for validation precision.
# Decimal fields in RESPONSE schemas use float for JSON number serialization.


# ============================================================================
# ADMIN SCHEMAS
# ============================================================================


class AdminListResponse(BaseModel):
    """Admin summary for list views"""

    id: int
    username: str
    display_name: str | None = None
    telegram_id: str | None = None
    wallet_balance: float
    status: str
    created_at: datetime | None = None
    user_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class AdminDetailResponse(BaseModel):
    """Full admin detail view"""

    id: int
    username: str
    display_name: str | None = None
    telegram_id: str | None = None
    whatsapp_number: str | None = None
    phone_number: str | None = None
    wallet_balance: float
    status: str
    notes: str | None = None
    approved_by: int | None = None
    approved_at: datetime | None = None
    created_at: datetime | None = None
    user_count: int = 0
    broadcasts_enabled: bool = True
    recent_transactions: list = []

    model_config = ConfigDict(from_attributes=True)


class ApproveAdminRequest(BaseModel):
    """Request body for approving a pending admin"""

    password: str = Field(..., min_length=8, max_length=100)


class CreditWalletRequest(BaseModel):
    """Request body for crediting an admin wallet"""

    amount_usd: Decimal = Field(..., gt=0, description="Amount in USD to credit")
    reason: str = Field(..., min_length=1, max_length=500)


class PendingAdminResponse(BaseModel):
    """Pending admin registration for bot approval list"""

    id: int
    username: str
    display_name: str | None = None
    telegram_id: str | None = None
    whatsapp_number: str | None = None
    phone_number: str | None = None
    notes: str | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# WIRE ORDER SCHEMAS
# ============================================================================


class WireOrderResponse(BaseModel):
    """Wire order response"""

    id: int
    admin_id: int
    admin_username: str | None = None
    amount_tomans: float
    amount_usd: float | None = None
    payment_method: str = "wire"
    crypto_txid: str | None = None
    crypto_link: str | None = None
    contact_telegram: str
    contact_whatsapp: str | None = None
    contact_phone: str | None = None
    notes: str | None = None
    status: str
    admin_notes: str | None = None
    reviewed_by: int | None = None
    reviewed_at: datetime | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ReviewOrderRequest(BaseModel):
    """Request body for approving/rejecting a wire order"""

    admin_notes: str | None = None
    exchange_rate: Decimal | None = Field(
        None, description="Toman to USD rate if approving"
    )


# ============================================================================
# PLATFORM SETTINGS SCHEMAS
# ============================================================================


class PlatformSettingsResponse(BaseModel):
    """Platform-wide settings"""

    price_per_gb: str
    price_per_region_monthly: str
    min_topup_tomans: str
    toman_to_usd_rate: str
    toman_per_usd_rate: str = "60000"
    crypto_topup_address: str = ""
    crypto_topup_network: str = ""
    crypto_topup_memo: str = ""
    min_topup_usd: str = "10"
    cloudflare_domain: str = ""
    cloudflare_zone_id: str = ""
    cloudflare_api_token: str = ""
    arvan_api_key: str = ""


class UpdateSettingsRequest(BaseModel):
    """Request body for updating platform settings"""

    price_per_gb: str | None = None
    price_per_region_monthly: str | None = None
    min_topup_tomans: str | None = None
    toman_to_usd_rate: str | None = None
    toman_per_usd_rate: str | None = None
    crypto_topup_address: str | None = None
    crypto_topup_network: str | None = None
    crypto_topup_memo: str | None = None
    min_topup_usd: str | None = None
    cloudflare_domain: str | None = None
    cloudflare_zone_id: str | None = None
    cloudflare_api_token: str | None = None
    arvan_api_key: str | None = None


class MigrateTldRequest(BaseModel):
    """Request body for TLD migration"""

    new_domain: str = Field(
        ...,
        min_length=3,
        max_length=255,
        description="New base domain (e.g., 'newdomain.com')",
    )
    new_zone_id: str = Field(
        ...,
        min_length=10,
        max_length=100,
        description="Cloudflare zone ID for the new domain",
    )
    confirm: bool = Field(
        ...,
        description="Must be true. Explicit safety confirmation for this destructive, superseded operation.",
    )


class MigrateTldResponse(BaseModel):
    """TLD migration result"""

    success: bool
    message: str
    old_domain: str
    new_domain: str
    deployments_updated: int
    domains_renamed: int
    dns_records_deleted: int
    dns_delete_errors: int
    sync_triggered: bool


# ============================================================================
# ANALYTICS SCHEMAS
# ============================================================================


class PlatformAnalytics(BaseModel):
    """Platform-wide analytics summary"""

    total_admins: int
    active_admins: int
    pending_admins: int
    total_end_users: int
    active_end_users: int
    total_revenue_usd: float
    total_traffic_gb: float
    total_wire_orders_pending: int


# ============================================================================
# FLUX APP REGISTRATION SCHEMAS
# ============================================================================


class RegisterAppRequest(BaseModel):
    """Request body for registering a new Flux app"""

    app_name: str = Field(
        ..., min_length=1, max_length=255, description="Flux app name (e.g., 'ch01')"
    )
    protocol_ports: dict = Field(
        ..., description="Per-protocol port mapping, e.g., {'ssh': 34568, 'ss': 37734}"
    )


class UpdateAppRequest(BaseModel):
    """Request body for updating a Flux app registration"""

    protocol_ports: dict | None = None
    is_active: bool | None = None


class AppRegistrationResponse(BaseModel):
    """Flux app registration response"""

    id: int
    app_name: str
    protocol_ports: dict
    is_active: bool
    registered_by: int | None = None
    last_discovery_at: datetime | None = None
    last_discovery_ips: list | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    regions: list[str] = []
    healthy_instances: int = Field(
        default=0,
        description="Healthy domains under ACTIVE deployments (excludes phantom-deactivated).",
    )
    serving: bool = Field(
        default=False,
        description="App is active AND has >=1 healthy domain under an active deployment.",
    )

    model_config = ConfigDict(from_attributes=True)


# --- TLD Management Schemas ---


class TldCreateRequest(BaseModel):
    domain: str = Field(
        ..., min_length=3, max_length=255, description="Full domain name"
    )
    dns_provider: str = Field(..., pattern=r"^(cloudflare|arvancloud)$")
    zone_id: Optional[str] = Field(
        None, description="Cloudflare zone ID or ArvanCloud zone domain"
    )
    purpose: str = Field(..., pattern=r"^(fdm|subscription|dashboard|admin_panel)$")

    @model_validator(mode="after")
    def validate_zone_id(self):
        if self.dns_provider == "cloudflare" and not self.zone_id:
            raise ValueError("zone_id is required for Cloudflare provider")
        return self


class TldResponse(BaseModel):
    id: int
    domain: str
    dns_provider: str
    zone_id: Optional[str] = None
    purpose: str
    server_ip: Optional[str] = None
    is_active: bool
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class TldListResponse(BaseModel):
    fdm: List[TldResponse] = []
    subscription: List[TldResponse] = []
    dashboard: List[TldResponse] = []
    admin_panel: List[TldResponse] = []


class TldActivateResponse(BaseModel):
    success: bool
    message: str
    purpose: str
    old_domain: Optional[str] = None
    new_domain: str
    details: Dict[str, Any] = {}


class TldPinRequest(BaseModel):
    """Pin (or clear) an admin's effective TLD for a purpose.

    tld_id set -> pin the admin to that TLD (effective becomes the pin);
    tld_id=None -> clear the pin (revert to least-active-user-count LB).
    """

    admin_id: int
    purpose: str = Field(..., pattern=r"^(fdm|subscription|dashboard|admin_panel)$")
    tld_id: Optional[int] = None


# --- TLD Analytics Schemas ---


class TldDnsHealth(BaseModel):
    """fdm-only DNS health for one TLD (spec §4.3). Live-snapshot only (the
    series endpoint is backed by TldUsageDaily and is intentionally excluded)."""

    healthy_domains: int
    total_domains: int
    all_dns_failed: bool
    last_error: Optional[str] = None


class TldAnalyticsTld(BaseModel):
    """One TLD in the live snapshot. active_user_count == the LB's view."""

    tld_id: int
    domain: str
    dns_provider: str
    is_active: bool
    active_user_count: int
    dns_health: Optional[TldDnsHealth] = None  # fdm-only; None for other purposes


class TldAnalyticsSnapshot(BaseModel):
    """Live per-purpose TLD usage. Counts come from active_user_counts —
    identical to what the load-balancer sees (drift-proof)."""

    fdm: list[TldAnalyticsTld] = []
    subscription: list[TldAnalyticsTld] = []
    dashboard: list[TldAnalyticsTld] = []
    admin_panel: list[TldAnalyticsTld] = []


class TldAnalyticsSeriesDay(BaseModel):
    """One day of the time-series, chart-ready: {domain: count}."""

    date: str
    values: dict[str, int]


class TldAnalyticsSeries(BaseModel):
    """Per-purpose daily series over `days` for stacked line charts."""

    purpose: str
    days: int
    domains: list[str]  # ordered domain list -> one <Line> each + Legend
    series: list[TldAnalyticsSeriesDay]


# --- TLD Assignment Schemas ---


class TldAssignmentCell(BaseModel):
    """One admin×purpose assignment: pin intent + resolved effective."""

    effective_tld_id: Optional[int] = None
    pinned_tld_id: Optional[int] = None
    source: Optional[str] = None  # pin|lb|unassigned|None(default)


class TldAdminAssignment(BaseModel):
    admin_id: int
    username: str
    assignments: Dict[str, TldAssignmentCell]  # purpose -> cell


class TldAssignmentsResponse(BaseModel):
    assignments: List[TldAdminAssignment]
