"""
Subscription Pydantic schemas for protocols, plans, and subscriptions
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

# ============================================================================
# PROTOCOL SCHEMAS
# ============================================================================


class ProtocolBase(BaseModel):
    """Base protocol schema"""

    name: str = Field(..., max_length=100)
    display_name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    flux_app_name: Optional[str] = Field(None, max_length=255)
    default_port: Optional[int] = Field(None, gt=0, lt=65536)
    is_active: bool = True


class ProtocolCreate(ProtocolBase):
    """Schema for protocol creation"""

    pass


class ProtocolUpdate(BaseModel):
    """Schema for protocol updates"""

    display_name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    default_port: Optional[int] = Field(None, gt=0, lt=65536)
    is_active: Optional[bool] = None


class ProtocolResponse(ProtocolBase):
    """Schema for protocol in responses"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


# ============================================================================
# SUBSCRIPTION PLAN SCHEMAS
# ============================================================================


class SubscriptionPlanBase(BaseModel):
    """Base subscription plan schema"""

    name: str = Field(..., max_length=100)
    tier: str = Field(..., pattern="^(bronze|silver|gold|platinum)$")
    duration_months: int = Field(..., ge=0, le=12)  # 0 for trial
    price_usd: Decimal = Field(..., ge=0)
    max_protocols: int = Field(default=1, ge=1)
    max_connections: int = Field(default=1, ge=1)
    data_limit_gb: Optional[int] = Field(None, ge=1)  # NULL = unlimited
    daily_ip_changes: int = Field(default=1, ge=0)


class SubscriptionPlanCreate(SubscriptionPlanBase):
    """Schema for subscription plan creation"""

    pass


class SubscriptionPlanUpdate(BaseModel):
    """Schema for subscription plan updates"""

    name: Optional[str] = Field(None, max_length=100)
    price_usd: Optional[Decimal] = Field(None, ge=0)
    max_protocols: Optional[int] = Field(None, ge=1)
    max_connections: Optional[int] = Field(None, ge=1)
    data_limit_gb: Optional[int] = Field(None, ge=1)
    daily_ip_changes: Optional[int] = Field(None, ge=0)


class SubscriptionPlanResponse(SubscriptionPlanBase):
    """Schema for subscription plan in responses"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


# ============================================================================
# SUBSCRIPTION SCHEMAS
# ============================================================================


class SubscriptionBase(BaseModel):
    """Base subscription schema"""

    plan_id: int
    expires_at: datetime
    auto_renew: bool = False


class SubscriptionCreate(SubscriptionBase):
    """Schema for subscription creation"""

    user_id: int


class SubscriptionUpdate(BaseModel):
    """Schema for subscription updates"""

    status: Optional[str] = Field(None, pattern="^(active|expired|cancelled|pending)$")
    expires_at: Optional[datetime] = None
    auto_renew: Optional[bool] = None


class SubscriptionResponse(SubscriptionBase):
    """Schema for subscription in responses"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    status: str
    started_at: datetime
    created_at: datetime


class SubscriptionWithPlan(SubscriptionResponse):
    """Subscription response with plan details"""

    plan: SubscriptionPlanResponse


class SubscriptionWithDetails(SubscriptionWithPlan):
    """Subscription with complete details including protocols"""

    active_protocols: int = Field(..., description="Number of active protocols")
    data_used_gb: Optional[Decimal] = Field(None, description="Data used in GB")
    data_limit_gb: Optional[int] = Field(
        None, description="Data limit in GB (NULL = unlimited)"
    )


# ============================================================================
# SUBSCRIPTION PURCHASE SCHEMAS
# ============================================================================


class SubscriptionPurchaseRequest(BaseModel):
    """Request to purchase a subscription"""

    plan_id: int
    payment_method: str = Field(
        ..., pattern="^(zarinpal|nowpayments|stripe|flux|wallet)$"
    )
    auto_renew: bool = False


class SubscriptionPurchaseResponse(BaseModel):
    """Response for subscription purchase"""

    subscription_id: int
    payment_id: int
    payment_url: Optional[str] = None  # URL to redirect user for payment
    status: str
    amount_usd: Decimal
    message: str
