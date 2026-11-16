"""Pydantic schemas for AdminPackage CRUD endpoints."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class PackageCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    traffic_limit_gb: Decimal = Field(..., gt=0, le=10000)
    duration_days: int = Field(..., gt=0, le=3650)
    price_tomans: Decimal = Field(..., gt=0, le=100000000)
    region_count: int = Field(1, ge=1, le=4)
    all_regions: bool = False
    display_order: int = 0


class PackageUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    traffic_limit_gb: Optional[Decimal] = Field(None, gt=0, le=10000)
    duration_days: Optional[int] = Field(None, gt=0, le=3650)
    price_tomans: Optional[Decimal] = Field(None, gt=0, le=100000000)
    region_count: Optional[int] = Field(None, ge=1, le=4)
    all_regions: Optional[bool] = None
    is_active: Optional[bool] = None
    display_order: Optional[int] = None


class PackageResponse(BaseModel):
    id: int
    admin_id: int
    name: str
    traffic_limit_gb: Decimal
    duration_days: int
    price_tomans: Decimal
    region_count: int
    all_regions: bool
    is_active: bool
    display_order: int
    created_at: datetime
    updated_at: datetime
