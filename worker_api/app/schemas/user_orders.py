"""Pydantic schemas for UserOrder endpoints."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class OrderResponse(BaseModel):
    id: int
    user_id: int
    admin_id: int
    package_id: Optional[int]
    package_snapshot: dict
    macro_region: str
    amount_tomans: Decimal
    wallet_credit_applied_tomans: Decimal
    status: str
    reviewer_admin_id: Optional[int]
    reviewed_at: Optional[datetime]
    rejection_reason: Optional[str]
    receipt_file_id: Optional[str]
    receipt_local_path: Optional[str]
    payment_method: str = "card"
    crypto_txid: Optional[str] = None
    crypto_link: Optional[str] = None
    amount_usd_snapshot: Optional[Decimal] = None
    created_at: datetime
    expires_at: Optional[datetime]


class OrderCreateRequest(BaseModel):
    """End-user submits this after uploading a receipt to their reseller bot."""

    package_id: int
    macro_region: str = Field(..., max_length=5)
    wallet_credit_to_apply_tomans: Decimal = Decimal("0")
    receipt_file_id: str
    receipt_file_unique_id: str


class OrderReceiptResponse(BaseModel):
    """Used by admin dashboard to render receipt photo URL."""

    order_id: int
    receipt_url: str
