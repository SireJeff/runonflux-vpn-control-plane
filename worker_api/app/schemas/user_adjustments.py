"""Schemas for the manual renewal / region-edit endpoints."""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class RenewUserRequest(BaseModel):
    """Exactly one of the action fields should be set."""

    extend_days: Optional[int] = Field(None, gt=0, le=3650)
    topup_gb: Optional[Decimal] = Field(None, gt=0, le=10000)
    set_expiry: Optional[datetime] = None
    reapply_package_id: Optional[int] = None
    reason: Optional[str] = Field(None, max_length=500)
    # Positivity is enforced in the endpoint so a 0/negative value returns a
    # clear 400 with guidance instead of a raw 422 validation error.
    set_traffic_limit_gb: Optional[Decimal] = Field(None, le=100000)
    set_unlimited: bool = False


class SetUsernameRequest(BaseModel):
    new_username: str = Field(
        ..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$"
    )
    reason: Optional[str] = Field(None, max_length=500)


class SetTelegramRequest(BaseModel):
    telegram_id: Optional[int] = Field(None, ge=1)
    telegram_chat_id: Optional[int] = None
    reason: Optional[str] = Field(None, max_length=500)


class ResetTrafficRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=500)


class SetUserRegionsRequest(BaseModel):
    macro_regions: List[str] = Field(..., min_length=1, max_length=4)
    reason: Optional[str] = Field(None, max_length=500)


class UserAdjustmentResponse(BaseModel):
    id: int
    user_id: int
    admin_id: int
    action: str
    details: dict
    reason: Optional[str]
    created_at: datetime
