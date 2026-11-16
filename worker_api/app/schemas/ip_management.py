"""
IP Management Pydantic schemas for protocol instances, IP changes, and quotas
"""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

# ============================================================================
# PROTOCOL INSTANCE SCHEMAS
# ============================================================================


class ProtocolInstanceBase(BaseModel):
    """Base protocol instance schema"""

    flux_app_name: str = Field(..., max_length=255)
    instance_number: int = Field(..., ge=1, le=40)
    flux_node_name: Optional[str] = Field(None, max_length=255)
    ip_address: str
    country_code: str = Field(..., min_length=2, max_length=2)
    country_name: str = Field(..., max_length=100)
    city: Optional[str] = Field(None, max_length=100)
    is_active: bool = True


class ProtocolInstanceCreate(ProtocolInstanceBase):
    """Schema for protocol instance creation"""

    protocol_id: int


class ProtocolInstanceUpdate(BaseModel):
    """Schema for protocol instance updates"""

    flux_node_name: Optional[str] = Field(None, max_length=255)
    ip_address: Optional[str] = None
    city: Optional[str] = Field(None, max_length=100)
    is_active: Optional[bool] = None
    last_health_check: Optional[datetime] = None


class ProtocolInstanceResponse(ProtocolInstanceBase):
    """Schema for protocol instance in responses"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    protocol_id: int
    last_health_check: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class AvailableLocation(BaseModel):
    """Available server location for users"""

    country_code: str
    country_name: str
    available_instances: int = Field(..., description="Number of available instances")
    flag_emoji: Optional[str] = None


# ============================================================================
# IP CHANGE REQUEST SCHEMAS
# ============================================================================


class IPChangeRequestBase(BaseModel):
    """Base IP change request schema"""

    protocol_id: int
    requested_country_code: Optional[str] = Field(None, min_length=2, max_length=2)


class IPChangeRequestCreate(IPChangeRequestBase):
    """Schema for IP change request creation"""

    user_id: int
    subscription_id: int
    old_instance_id: Optional[int] = None


class IPChangeRequestUpdate(BaseModel):
    """Schema for IP change request updates"""

    status: str = Field(..., pattern="^(pending|completed|failed|denied)$")
    new_instance_id: Optional[int] = None
    denial_reason: Optional[str] = None
    processed_at: Optional[datetime] = None


class IPChangeRequestResponse(IPChangeRequestBase):
    """Schema for IP change request in responses"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    subscription_id: int
    old_instance_id: Optional[int] = None
    new_instance_id: Optional[int] = None
    status: str
    denial_reason: Optional[str] = None
    created_at: datetime
    processed_at: Optional[datetime] = None


class IPChangeRequest(BaseModel):
    """Request to change server location"""

    protocol_id: int
    country_code: Optional[str] = Field(
        None,
        min_length=2,
        max_length=2,
        description="Target country code (leave empty for random)",
    )


class IPChangeResponse(BaseModel):
    """Response for IP change request"""

    request_id: int
    status: str
    new_location: Optional[str] = None
    new_ip: Optional[str] = None
    quota_remaining: int = Field(..., description="Remaining IP changes for today")
    message: str


# ============================================================================
# IP CHANGE QUOTA SCHEMAS
# ============================================================================


class IPChangeQuotaBase(BaseModel):
    """Base IP change quota schema"""

    date: date
    changes_used: int = 0
    daily_limit: int


class IPChangeQuotaCreate(IPChangeQuotaBase):
    """Schema for IP change quota creation"""

    user_id: int


class IPChangeQuotaResponse(IPChangeQuotaBase):
    """Schema for IP change quota in responses"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    remaining: int = Field(..., description="Remaining changes for the day")


class QuotaStatus(BaseModel):
    """Current quota status for user"""

    daily_limit: int
    used_today: int
    remaining_today: int
    resets_at: datetime = Field(..., description="When the quota resets")
