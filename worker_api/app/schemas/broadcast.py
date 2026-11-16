"""Request/response schemas for reseller broadcast endpoints."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AudienceCountRequest(BaseModel):
    segment: str


class AudienceCountResponse(BaseModel):
    count: int


class BroadcastCreateRequest(BaseModel):
    message_text: str = Field(..., min_length=1, max_length=4096)
    button_label: Optional[str] = Field(None, max_length=64)
    button_url: Optional[str] = Field(None, max_length=2048)
    segment: str


class BroadcastResponse(BaseModel):
    id: int
    admin_id: int
    segment: str
    message_text: str
    button_label: Optional[str]
    button_url: Optional[str]
    status: str
    audience_count: int
    sent_count: int
    failed_count: int
    blocked_count: int
    error: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class BroadcastEnabledRequest(BaseModel):
    enabled: bool


class BroadcastEnabledResponse(BaseModel):
    admin_id: int
    broadcasts_enabled: bool
