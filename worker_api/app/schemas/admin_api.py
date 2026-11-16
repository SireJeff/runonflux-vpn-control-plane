"""
Admin API schemas for FluxVPN Reseller Platform
Request/response validation for end user CRUD, wallet, connections, regions, and analytics
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

# ============================================================================
# END USER SCHEMAS
# ============================================================================


class CreateUserRequest(BaseModel):
    """Request body for creating an end user"""

    username: Optional[str] = Field(
        None,
        min_length=3,
        max_length=50,
        pattern=r"^[a-zA-Z0-9_]+$",
        description="Username (3-50 chars, alphanumeric + underscore). Omit to auto-generate.",
    )
    display_name: Optional[str] = Field(None, max_length=100)
    remark: Optional[str] = Field(None, max_length=500)
    macro_region: Optional[str] = Field(
        None,
        max_length=5,
        description="Macro region code (eu, as, na, row). Auto-assigned if not provided.",
    )
    traffic_limit_gb: Optional[float] = Field(
        10.0, gt=0, description="Per-user traffic limit in GB. null = unlimited."
    )
    expires_at: Optional[datetime] = Field(
        None, description="Subscription expiry date. null = no expiry."
    )


class UpdateUserRequest(BaseModel):
    """Request body for updating an end user"""

    display_name: Optional[str] = Field(None, max_length=100)
    remark: Optional[str] = Field(None, max_length=500)
    new_password: Optional[str] = Field(
        None,
        min_length=8,
        max_length=100,
        description="New portal password (min 8 chars)",
    )
    traffic_limit_gb: Optional[float] = Field(
        None, gt=0, description="Per-user traffic limit in GB. null = unlimited."
    )
    expires_at: Optional[datetime] = Field(
        None, description="Subscription expiry date. null = no expiry."
    )


class RegionInfo(BaseModel):
    """Macro region info for user response"""

    macro_region: str
    assigned_at: Optional[datetime] = None


class UserResponse(BaseModel):
    """End user response"""

    id: int
    username: str
    display_name: Optional[str] = None
    remark: Optional[str] = None
    status: str
    traffic_used_gb: float = 0.0
    traffic_limit_gb: Optional[float] = None  # null = unlimited
    macro_region: Optional[str] = None
    subscription_url: Optional[str] = None
    expires_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class UserDetailResponse(UserResponse):
    """End user detail response with macro region info"""

    macro_region_info: Optional[RegionInfo] = None
    macro_regions: List[str] = []
    adjustments: List[Dict[str, Any]] = []
    telegram_id: Optional[int] = None
    telegram_chat_id: Optional[int] = None


class ProtocolConnections(BaseModel):
    """A primary connection string with optional fallbacks."""

    primary: str
    fallbacks: list[str] = []
    # SSH-only: parsed {host, port, username, password} for field-wise display.
    # None for all other protocols. Populated by end_user endpoints.
    parsed_fields: Optional[Dict[str, Any]] = None


class UserCreateResponse(UserResponse):
    """End user response after creation, includes generated password"""

    password: str
    connection_strings: Dict[str, Dict[str, ProtocolConnections]] = {}
    portal_url: Optional[str] = None


class UserListResponse(BaseModel):
    """Paginated list of end users"""

    items: List[UserResponse]
    total: int
    page: int
    per_page: int


class ConnectionStringsResponse(BaseModel):
    """Connection strings grouped by region and protocol"""

    connections: Dict[str, Dict[str, ProtocolConnections]] = {}
    telegram_proxies: Dict[str, str] = {}
    last_refreshed_at: Optional[datetime] = None


class CountryInfo(BaseModel):
    """Country within a macro region"""

    code: str
    name: str
    flag: str
    healthy_instances: int


class MacroRegionInfo(BaseModel):
    """Macro region with aggregated info"""

    code: str
    name: str
    flag: str
    healthy_instances: int
    countries: List[CountryInfo]


# ============================================================================
# WALLET & WIRE ORDER SCHEMAS
# ============================================================================


class WireOrderRequest(BaseModel):
    """Request body for submitting a wallet top-up order (wire OR crypto).

    payment_method 'wire' (default): amount_tomans required (min enforced in the
    endpoint against platform settings). 'crypto': amount_usd (source of truth)
    and crypto_txid required; amount_tomans is derived server-side for display.
    """

    payment_method: str = Field("wire", pattern="^(wire|crypto)$")
    amount_tomans: Optional[float] = Field(None, gt=0, description="Required for wire")
    amount_usd: Optional[float] = Field(None, gt=0, description="Required for crypto")
    contact_telegram: str = Field(..., min_length=1, max_length=50)
    contact_whatsapp: Optional[str] = Field(None, max_length=20)
    contact_phone: Optional[str] = Field(None, max_length=20)
    notes: Optional[str] = Field(None, max_length=1000)
    crypto_txid: Optional[str] = Field(None, max_length=255)
    crypto_link: Optional[str] = Field(None, max_length=500)

    @model_validator(mode="after")
    def _validate_by_method(self):
        if self.payment_method == "crypto":
            if self.amount_usd is None:
                raise ValueError("amount_usd is required for crypto payments")
            if not (self.crypto_txid and self.crypto_txid.strip()):
                raise ValueError("crypto_txid is required for crypto payments")
        else:  # wire
            if self.amount_tomans is None:
                raise ValueError("amount_tomans is required for wire payments")
        return self


class WireOrderResponse(BaseModel):
    """Wire order response"""

    id: int
    amount_tomans: float
    amount_usd: Optional[float] = None
    status: str
    created_at: Optional[datetime] = None


class TransactionResponse(BaseModel):
    """Wallet transaction response"""

    id: int
    amount_usd: float
    transaction_type: str
    description: Optional[str] = None
    balance_after: Optional[float] = None
    created_at: Optional[datetime] = None


class TransactionListResponse(BaseModel):
    """Paginated list of wallet transactions"""

    items: List[TransactionResponse]
    total: int
    page: int
    per_page: int


class WalletResponse(BaseModel):
    """Wallet balance and recent transactions"""

    balance: float
    recent_transactions: List[TransactionResponse] = []


class PaymentConfigResponse(BaseModel):
    """Reseller-facing payment config: platform crypto address + conversion inputs."""

    crypto_enabled: bool
    crypto_topup_address: Optional[str] = None
    crypto_topup_network: Optional[str] = None
    crypto_topup_memo: Optional[str] = None
    min_topup_usd: float
    toman_per_usd_rate: float


class PanelUrlResponse(BaseModel):
    """Reseller's effective admin-panel URL (per-reseller, self-healing)."""

    panel_url: str
    domain: Optional[str] = None
    is_fallback: bool


# ============================================================================
# ANALYTICS SCHEMAS
# ============================================================================


class TopUserTraffic(BaseModel):
    """Top user by traffic consumption"""

    username: str
    traffic_gb: float


class ProtocolBreakdownEntry(BaseModel):
    """Per-protocol traffic breakdown entry"""

    protocol: str
    traffic_gb: float
    user_count: int


class AdminAnalytics(BaseModel):
    """Per-admin analytics summary"""

    total_users: int
    active_users: int
    total_traffic_gb: float
    total_cost_usd: float = 0.0
    top_users_by_traffic: List[TopUserTraffic] = []
    protocol_breakdown: List[ProtocolBreakdownEntry] = []
