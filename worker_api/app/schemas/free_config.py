"""Pydantic schemas for the /admin/free-config API (Task 13).

FreeConfigResponse mirrors the public-facing view of AdminFreeConfig.
FreeConfigUpdate is an all-optional patch body; `region`, when provided,
must be a valid macro-region code (guards against a bad region later
causing a KeyError in connection-string generation).
"""

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, field_validator

from app.core.constants import MACRO_REGIONS


class ChannelOut(BaseModel):
    id: int
    chat_id: Optional[int] = None
    username: Optional[str] = None
    title: str
    invite_url: Optional[str] = None

    class Config:
        from_attributes = True


class ChannelCreate(BaseModel):
    identifier: str  # @handle or numeric chat id
    invite_url: Optional[str] = None


class FreeConfigResponse(BaseModel):
    is_enabled: bool
    kind: str
    label: Optional[str] = None
    region: Optional[str] = None
    traffic_limit_gb: Optional[Decimal] = None
    duration_days: Optional[int] = None
    has_credential: bool
    daily_limit_mb: Optional[int] = None
    max_free_users: Optional[int] = None
    global_ceiling_mb: Optional[int] = None
    global_channels: list[ChannelOut] = []

    class Config:
        from_attributes = True


class FreeConfigUpdate(BaseModel):
    is_enabled: Optional[bool] = None
    kind: Optional[str] = None
    label: Optional[str] = None
    region: Optional[str] = None
    traffic_limit_gb: Optional[Decimal] = None
    duration_days: Optional[int] = None
    daily_limit_mb: Optional[int] = None
    max_free_users: Optional[int] = None

    @field_validator("region")
    @classmethod
    def _validate_region(cls, v: Optional[str]) -> Optional[str]:
        """Reject region codes that are not canonical macro-regions."""
        if v is None:
            return v
        if v not in MACRO_REGIONS:
            valid = ", ".join(sorted(MACRO_REGIONS.keys()))
            raise ValueError(f"Invalid region '{v}'. Must be one of: {valid}")
        return v
