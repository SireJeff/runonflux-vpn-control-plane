"""
Payment processing endpoints
"""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, List, Optional, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models import User, WalletTransaction
from app.schemas import SuccessResponse, WalletTransactionResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["Payments"])


def _as_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


# ============================================================================
# REQUEST/RESPONSE SCHEMAS
# ============================================================================


class DepositRequest(BaseModel):
    """Request to deposit funds via cryptocurrency"""

    amount_usd: Decimal = Field(..., gt=0, description="Amount in USD to deposit")
    crypto_currency: str = Field(
        ..., description="Cryptocurrency type (FLUX, BTC, ETH, USDT)"
    )
    tx_hash: Optional[str] = Field(
        None, description="Transaction hash (for verification)"
    )

    @field_validator("crypto_currency")
    @classmethod
    def validate_crypto_currency(cls, v):
        allowed = ["FLUX", "BTC", "ETH", "USDT"]
        if v.upper() not in allowed:
            raise ValueError(f"Cryptocurrency must be one of: {', '.join(allowed)}")
        return v.upper()


class WithdrawalRequest(BaseModel):
    """Request to withdraw funds"""

    amount_usd: Decimal = Field(..., gt=0, description="Amount in USD to withdraw")
    crypto_currency: str = Field(..., description="Cryptocurrency type for withdrawal")
    wallet_address: str = Field(
        ..., min_length=10, description="Destination wallet address"
    )

    @field_validator("crypto_currency")
    @classmethod
    def validate_crypto_currency(cls, v):
        allowed = ["FLUX", "BTC", "ETH", "USDT"]
        if v.upper() not in allowed:
            raise ValueError(f"Cryptocurrency must be one of: {', '.join(allowed)}")
        return v.upper()


class DepositResponse(BaseModel):
    """Response for deposit initiation"""

    payment_address: str
    amount_usd: Decimal
    crypto_currency: str
    crypto_amount: Decimal
    exchange_rate: Decimal
    qr_code_url: Optional[str] = None
    expires_at: datetime
    payment_id: str


class WithdrawalResponse(BaseModel):
    """Response for withdrawal request"""

    withdrawal_id: str
    amount_usd: Decimal
    crypto_currency: str
    crypto_amount: Decimal
    wallet_address: str
    status: str  # pending, processing, completed, failed
    estimated_completion: Optional[datetime] = None


class PaymentMethodResponse(BaseModel):
    """Payment method information"""

    method_id: str
    name: str
    type: str  # crypto, card, bank
    is_available: bool
    min_amount_usd: Decimal
    max_amount_usd: Optional[Decimal] = None
    processing_time: str
    fees_percentage: Decimal


# ============================================================================
# DEPOSIT ENDPOINTS
# ============================================================================


@router.post("/deposit/initiate", response_model=DepositResponse)
async def initiate_deposit(
    request: DepositRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Initiate a cryptocurrency deposit

    **Flow:**
    1. Generate unique payment address for this deposit
    2. Calculate crypto amount based on current exchange rate
    3. Create pending transaction record
    4. Return payment details with QR code

    **Supported Cryptocurrencies:**
    - FLUX (Flux)
    - BTC (Bitcoin)
    - ETH (Ethereum)
    - USDT (Tether)

    **Note:** This is a placeholder implementation.
    In production, integrate with payment processor (e.g., CoinPayments, NOWPayments).
    """
    logger.info(
        f"User {current_user.id} initiating ${request.amount_usd} deposit via {request.crypto_currency}"
    )

    # Mock exchange rates (in production, fetch from API)
    exchange_rates = {
        "FLUX": Decimal("0.50"),  # 1 FLUX = $0.50
        "BTC": Decimal("45000.00"),  # 1 BTC = $45,000
        "ETH": Decimal("2500.00"),  # 1 ETH = $2,500
        "USDT": Decimal("1.00"),  # 1 USDT = $1.00
    }

    rate = exchange_rates.get(request.crypto_currency, Decimal("1.00"))
    crypto_amount = request.amount_usd / rate

    # Generate unique payment ID
    payment_id = f"dep_{current_user.id}_{int(datetime.now(timezone.utc).replace(tzinfo=None).timestamp())}"

    # Generate payment address (mock)
    # In production, generate actual address via payment processor
    mock_addresses = {
        "FLUX": f"t1{payment_id[:40]}",
        "BTC": f"bc1{payment_id[:39]}",
        "ETH": f"0x{payment_id[:40]}",
        "USDT": f"0x{payment_id[:40]}",
    }

    payment_address = mock_addresses.get(request.crypto_currency, f"addr_{payment_id}")

    # Create pending transaction
    transaction = WalletTransaction(
        user_id=current_user.id,
        amount_usd=request.amount_usd,
        transaction_type="deposit",
        status="pending",
        description=f"Deposit via {request.crypto_currency}",
        reference_id=payment_id,
        metadata={
            "crypto_currency": request.crypto_currency,
            "crypto_amount": str(crypto_amount),
            "exchange_rate": str(rate),
            "payment_address": payment_address,
        },
    )

    db.add(transaction)
    db.commit()
    db.refresh(transaction)

    logger.info(f"Deposit initiated: {payment_id}")

    # Payment expires in 1 hour
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)

    return DepositResponse(
        payment_address=payment_address,
        amount_usd=request.amount_usd,
        crypto_currency=request.crypto_currency,
        crypto_amount=crypto_amount,
        exchange_rate=rate,
        qr_code_url=f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={payment_address}",
        expires_at=expires_at,
        payment_id=payment_id,
    )


@router.post("/deposit/confirm", response_model=SuccessResponse)
async def confirm_deposit(
    payment_id: str,
    tx_hash: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Confirm cryptocurrency deposit with transaction hash

    **Flow:**
    1. Find pending deposit transaction
    2. Verify transaction on blockchain (mock)
    3. Credit user's wallet
    4. Update transaction status to completed

    **Note:** In production, implement blockchain verification.
    """
    logger.info(
        f"User {current_user.id} confirming deposit {payment_id} with tx_hash {tx_hash}"
    )

    # Find transaction
    transaction = (
        db.query(WalletTransaction)
        .filter_by(
            user_id=current_user.id,
            reference_id=payment_id,
            transaction_type="deposit",
            status="pending",
        )
        .first()
    )

    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deposit transaction not found or already processed",
        )

    # In production: verify tx_hash on blockchain
    # For now, auto-approve

    # Credit wallet
    current_user.wallet_balance = _as_decimal(
        current_user.wallet_balance
    ) + _as_decimal(transaction.amount_usd)

    # Update transaction
    transaction_obj = cast(Any, transaction)
    transaction_obj.status = "completed"
    transaction_obj.extra_data["tx_hash"] = tx_hash
    transaction_obj.extra_data["confirmed_at"] = (
        datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    )

    db.commit()

    logger.info(
        f"Deposit {payment_id} confirmed and credited ${transaction.amount_usd} to user {current_user.id}"
    )

    return SuccessResponse(
        message=f"Deposit of ${transaction.amount_usd} confirmed and added to your wallet",
        data={
            "payment_id": payment_id,
            "amount_usd": str(transaction.amount_usd),
            "new_balance": str(current_user.wallet_balance),
        },
    )


@router.get("/deposit/{payment_id}/status")
async def check_deposit_status(
    payment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Check status of a deposit transaction

    Returns current status: pending, completed, expired, or failed.
    """
    transaction = (
        db.query(WalletTransaction)
        .filter_by(
            user_id=current_user.id, reference_id=payment_id, transaction_type="deposit"
        )
        .first()
    )

    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deposit transaction not found",
        )

    return {
        "payment_id": payment_id,
        "status": transaction.status,
        "amount_usd": transaction.amount_usd,
        "created_at": transaction.created_at,
        "metadata": transaction.extra_data,
    }


# ============================================================================
# WITHDRAWAL ENDPOINTS
# ============================================================================


@router.post("/withdraw", response_model=WithdrawalResponse)
async def request_withdrawal(
    request: WithdrawalRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Request withdrawal to cryptocurrency wallet

    **Requirements:**
    - Minimum withdrawal: $10 USD
    - User must have sufficient balance
    - Wallet address must be valid

    **Processing Time:**
    - USDT/ETH: 1-24 hours
    - BTC: 1-48 hours
    - FLUX: 1-6 hours

    **Fees:** 2% + network fee
    """
    logger.info(
        f"User {current_user.id} requesting ${request.amount_usd} withdrawal to {request.wallet_address}"
    )

    # Validate minimum amount
    min_withdrawal = Decimal("10.00")
    if request.amount_usd < min_withdrawal:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Minimum withdrawal amount is ${min_withdrawal}",
        )

    # Calculate fee (2% + network fee)
    fee_percentage = Decimal("0.02")  # 2%
    network_fees = {
        "FLUX": Decimal("0.10"),
        "BTC": Decimal("5.00"),
        "ETH": Decimal("3.00"),
        "USDT": Decimal("2.00"),
    }

    fee = (request.amount_usd * fee_percentage) + network_fees.get(
        request.crypto_currency, Decimal("1.00")
    )
    total_deduction = request.amount_usd + fee

    # Check balance
    wallet_balance = _as_decimal(current_user.wallet_balance)
    if wallet_balance < total_deduction:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Insufficient balance. Required: ${total_deduction} "
                f"(${request.amount_usd} + ${fee} fee), Available: ${wallet_balance}"
            ),
        )

    # Mock exchange rates
    exchange_rates = {
        "FLUX": Decimal("0.50"),
        "BTC": Decimal("45000.00"),
        "ETH": Decimal("2500.00"),
        "USDT": Decimal("1.00"),
    }

    rate = exchange_rates.get(request.crypto_currency, Decimal("1.00"))
    crypto_amount = request.amount_usd / rate

    # Generate withdrawal ID
    withdrawal_id = f"wd_{current_user.id}_{int(datetime.now(timezone.utc).replace(tzinfo=None).timestamp())}"

    # Deduct from wallet
    current_user.wallet_balance = wallet_balance - total_deduction

    # Create withdrawal transaction
    transaction = WalletTransaction(
        user_id=current_user.id,
        amount_usd=-request.amount_usd,  # Negative for withdrawal
        transaction_type="withdrawal",
        status="pending",
        description=f"Withdrawal to {request.crypto_currency} wallet",
        reference_id=withdrawal_id,
        metadata={
            "crypto_currency": request.crypto_currency,
            "crypto_amount": str(crypto_amount),
            "wallet_address": request.wallet_address,
            "exchange_rate": str(rate),
            "fee_usd": str(fee),
        },
    )

    db.add(transaction)

    # Create fee transaction
    fee_transaction = WalletTransaction(
        user_id=current_user.id,
        amount_usd=-fee,
        transaction_type="fee",
        status="completed",
        description=f"Withdrawal fee ({fee_percentage*100}% + network)",
        reference_id=f"fee_{withdrawal_id}",
    )

    db.add(fee_transaction)
    db.commit()
    db.refresh(transaction)

    logger.info(f"Withdrawal {withdrawal_id} initiated for user {current_user.id}")

    # Estimated completion
    processing_hours = {"FLUX": 6, "BTC": 48, "ETH": 24, "USDT": 24}

    estimated_completion = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
        hours=processing_hours.get(request.crypto_currency, 24)
    )

    return WithdrawalResponse(
        withdrawal_id=withdrawal_id,
        amount_usd=request.amount_usd,
        crypto_currency=request.crypto_currency,
        crypto_amount=crypto_amount,
        wallet_address=request.wallet_address,
        status="pending",
        estimated_completion=estimated_completion,
    )


@router.get("/withdraw/{withdrawal_id}/status")
async def check_withdrawal_status(
    withdrawal_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Check status of a withdrawal request
    """
    transaction = (
        db.query(WalletTransaction)
        .filter_by(
            user_id=current_user.id,
            reference_id=withdrawal_id,
            transaction_type="withdrawal",
        )
        .first()
    )

    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Withdrawal transaction not found",
        )

    return {
        "withdrawal_id": withdrawal_id,
        "status": transaction.status,
        "amount_usd": _as_decimal(transaction.amount_usd).copy_abs(),
        "created_at": transaction.created_at,
        "metadata": transaction.extra_data,
    }


# ============================================================================
# PAYMENT METHODS
# ============================================================================


@router.get("/methods", response_model=List[PaymentMethodResponse])
async def list_payment_methods():
    """
    List available payment methods

    Returns all supported payment methods with their limits and fees.
    """
    methods = [
        PaymentMethodResponse(
            method_id="flux",
            name="Flux (FLUX)",
            type="crypto",
            is_available=True,
            min_amount_usd=Decimal("5.00"),
            max_amount_usd=Decimal("10000.00"),
            processing_time="1-6 hours",
            fees_percentage=Decimal("0.00"),
        ),
        PaymentMethodResponse(
            method_id="btc",
            name="Bitcoin (BTC)",
            type="crypto",
            is_available=True,
            min_amount_usd=Decimal("10.00"),
            max_amount_usd=Decimal("50000.00"),
            processing_time="30-120 minutes",
            fees_percentage=Decimal("0.00"),
        ),
        PaymentMethodResponse(
            method_id="eth",
            name="Ethereum (ETH)",
            type="crypto",
            is_available=True,
            min_amount_usd=Decimal("10.00"),
            max_amount_usd=Decimal("50000.00"),
            processing_time="5-30 minutes",
            fees_percentage=Decimal("0.00"),
        ),
        PaymentMethodResponse(
            method_id="usdt",
            name="Tether (USDT)",
            type="crypto",
            is_available=True,
            min_amount_usd=Decimal("5.00"),
            max_amount_usd=Decimal("50000.00"),
            processing_time="5-30 minutes",
            fees_percentage=Decimal("0.00"),
        ),
    ]

    return methods


# ============================================================================
# TRANSACTION HISTORY
# ============================================================================


@router.get("/transactions", response_model=List[WalletTransactionResponse])
async def list_payment_transactions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    transaction_type: Optional[str] = Query(
        None, description="Filter by type: deposit, withdrawal, fee"
    ),
    status: Optional[str] = Query(
        None, description="Filter by status: pending, completed, failed"
    ),
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
):
    """
    List payment transactions (deposits, withdrawals, fees)

    **Filter Options:**
    - transaction_type: deposit, withdrawal, fee
    - status: pending, completed, failed

    Returns paginated transaction history.
    """
    query = db.query(WalletTransaction).filter(
        WalletTransaction.user_id == current_user.id
    )

    # Filter by transaction type
    if transaction_type:
        query = query.filter(WalletTransaction.transaction_type == transaction_type)

    # Filter by status
    if status:
        query = query.filter(WalletTransaction.status == status)

    transactions = (
        query.order_by(WalletTransaction.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [WalletTransactionResponse.model_validate(t) for t in transactions]
