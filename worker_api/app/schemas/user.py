"""
User Pydantic schemas for request/response validation
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# Base schema with common fields
class UserBase(BaseModel):
    """Base user schema"""

    telegram_username: Optional[str] = None
    email: Optional[str] = None
    flux_wallet_address: Optional[str] = None
    language: str = Field(default="en", pattern="^(en|fa|ar|ru|zh)$")


# Schema for creating a new user
class UserCreate(UserBase):
    """Schema for user creation"""

    telegram_user_id: int = Field(..., gt=0)


# Schema for updating user
class UserUpdate(BaseModel):
    """Schema for user updates (all fields optional)"""

    telegram_username: Optional[str] = None
    email: Optional[str] = None
    flux_wallet_address: Optional[str] = None
    language: Optional[str] = Field(None, pattern="^(en|fa|ar|ru|zh)$")


# Schema for user response
class UserResponse(UserBase):
    """Schema for user in responses"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_user_id: int
    referral_code: Optional[str] = None
    referred_by: Optional[int] = None
    referral_tier: str
    total_referrals: int
    referral_earnings_usd: Decimal
    wallet_balance: Decimal
    trial_used: bool
    trial_started_at: Optional[datetime] = None
    trial_expires_at: Optional[datetime] = None
    is_admin: bool
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    deletion_scheduled_at: Optional[datetime] = None
    created_at: datetime


# Schema for user with wallet info
class UserWithWallet(UserResponse):
    """User response with detailed wallet information"""

    pass


# Schema for user profile (public info)
class UserProfile(BaseModel):
    """Public user profile"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_username: Optional[str] = None
    referral_tier: str
    total_referrals: int
    language: str
    created_at: datetime


# Schema for referral statistics
class ReferralStats(BaseModel):
    """User referral statistics"""

    model_config = ConfigDict(from_attributes=True)

    referral_code: Optional[str]
    referral_tier: str
    total_referrals: int
    referral_earnings_usd: Decimal
    commission_rate: Decimal = Field(
        ..., description="Current commission rate based on tier"
    )


# Schema for wallet balance
class WalletBalance(BaseModel):
    """User wallet balance"""

    model_config = ConfigDict(from_attributes=True)

    user_id: int
    balance: Decimal = Field(..., alias="wallet_balance")
    currency: str = "USD"


# Token response schemas
class AuthResponse(BaseModel):
    """Authentication response with access token only (legacy)"""

    access_token: str
    token_type: str = "bearer"
    user: "UserResponse"


class TokenPairResponse(BaseModel):
    """Token pair response with access and refresh tokens"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: "UserResponse"
