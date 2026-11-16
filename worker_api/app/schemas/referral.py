"""Pydantic schemas for admin referral endpoints."""

from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ReferralConfigUpdate(BaseModel):
    is_enabled: Optional[bool] = None
    reward_percentage: Optional[Decimal] = Field(None, ge=0, le=100)
    reward_type: Optional[Literal["cashback", "traffic", "both"]] = None
    traffic_per_referral_mb: Optional[int] = Field(None, ge=0)
    traffic_max_bonus_mb: Optional[int] = Field(None, ge=0)


class ReferralConfigResponse(BaseModel):
    admin_id: int
    is_enabled: bool
    reward_percentage: Decimal
    reward_type: str
    traffic_per_referral_mb: int
    traffic_max_bonus_mb: int
    updated_at: datetime


class ReferralStatsResponse(BaseModel):
    my_referral_code: Optional[str]
    total_referrals: int
    total_earned_tomans: Decimal
    wallet_credit_tomans: Decimal


class ReferralEarningResponse(BaseModel):
    id: int
    order_id: int
    commission_percent: Decimal
    amount_tomans: Decimal
    created_at: datetime
