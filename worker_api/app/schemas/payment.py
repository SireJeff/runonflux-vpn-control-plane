"""
Payment Pydantic schemas for payments, wallet transactions, and withdrawals
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field

# ============================================================================
# PAYMENT SCHEMAS
# ============================================================================


class PaymentBase(BaseModel):
    """Base payment schema"""

    amount_usd: Decimal = Field(..., gt=0)
    payment_method: str = Field(
        ..., pattern="^(zarinpal|nowpayments|stripe|flux|wallet)$"
    )
    deposit_to_wallet: bool = False


class PaymentCreate(PaymentBase):
    """Schema for payment creation"""

    user_id: int
    subscription_id: Optional[int] = None


class PaymentUpdate(BaseModel):
    """Schema for payment updates"""

    status: str = Field(..., pattern="^(pending|completed|failed|cancelled)$")
    transaction_id: Optional[str] = None
    completed_at: Optional[datetime] = None


class PaymentResponse(PaymentBase):
    """Schema for payment in responses"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    subscription_id: Optional[int] = None
    status: str
    transaction_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class PaymentInitiate(BaseModel):
    """Request to initiate a payment"""

    amount_usd: Decimal = Field(..., gt=0)
    payment_method: str = Field(
        ..., pattern="^(zarinpal|nowpayments|stripe|flux|wallet)$"
    )
    deposit_to_wallet: bool = False
    subscription_id: Optional[int] = None


class PaymentInitiateResponse(BaseModel):
    """Response for payment initiation"""

    payment_id: int
    payment_url: Optional[str] = None  # Redirect URL for external payment
    qr_code: Optional[str] = None  # For cryptocurrency payments
    status: str
    message: str


# ============================================================================
# WALLET TRANSACTION SCHEMAS
# ============================================================================


class WalletTransactionBase(BaseModel):
    """Base wallet transaction schema"""

    amount_usd: Decimal = Field(...)  # Can be positive or negative
    transaction_type: str = Field(
        ..., pattern="^(deposit|purchase|withdrawal|refund|referral_commission)$"
    )
    description: Optional[str] = None


class WalletTransactionCreate(WalletTransactionBase):
    """Schema for wallet transaction creation"""

    user_id: int
    payment_id: Optional[int] = None
    subscription_id: Optional[int] = None
    balance_before: Decimal
    balance_after: Decimal


class WalletTransactionResponse(WalletTransactionBase):
    """Schema for wallet transaction in responses"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    payment_id: Optional[int] = None
    subscription_id: Optional[int] = None
    balance_before: Decimal
    balance_after: Decimal
    created_at: datetime


class WalletHistory(BaseModel):
    """Wallet transaction history"""

    current_balance: Decimal
    total_deposits: Decimal
    total_withdrawals: Decimal
    total_spent: Decimal
    transactions: list[WalletTransactionResponse]


# ============================================================================
# WITHDRAWAL REQUEST SCHEMAS
# ============================================================================


class WithdrawalRequestBase(BaseModel):
    """Base withdrawal request schema"""

    amount_usd: Decimal = Field(..., gt=0)
    withdrawal_method: str = Field(
        ..., pattern="^(zarinpal|bitcoin|ethereum|bank_transfer)$"
    )
    withdrawal_details: Dict[str, Any] = Field(
        ..., description="Card number, crypto address, bank account details, etc."
    )


class WithdrawalRequestCreate(WithdrawalRequestBase):
    """Schema for withdrawal request creation"""

    user_id: int


class WithdrawalRequestUpdate(BaseModel):
    """Schema for withdrawal request updates (admin only)"""

    status: str = Field(
        ..., pattern="^(pending|approved|processing|completed|rejected)$"
    )
    admin_notes: Optional[str] = None
    processed_by: Optional[int] = None


class WithdrawalRequestResponse(WithdrawalRequestBase):
    """Schema for withdrawal request in responses"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    status: str
    admin_notes: Optional[str] = None
    processed_by: Optional[int] = None
    created_at: datetime
    processed_at: Optional[datetime] = None


class WithdrawalRequestSubmit(BaseModel):
    """Request to submit a withdrawal"""

    amount_usd: Decimal = Field(..., gt=0)
    withdrawal_method: str = Field(
        ..., pattern="^(zarinpal|bitcoin|ethereum|bank_transfer)$"
    )
    # Method-specific details
    card_number: Optional[str] = Field(None, description="For Zarinpal/bank transfer")
    crypto_address: Optional[str] = Field(None, description="For crypto withdrawals")
    bank_account: Optional[str] = Field(None, description="For bank transfers")
    bank_name: Optional[str] = Field(None, description="For bank transfers")


class WithdrawalRequestSubmitResponse(BaseModel):
    """Response for withdrawal submission"""

    withdrawal_id: int
    status: str
    amount_usd: Decimal
    message: str
    estimated_processing_time: str = "1-3 business days"
