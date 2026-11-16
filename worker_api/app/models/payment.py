"""
Payment models
Payments, wallet transactions, and withdrawal requests
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import DECIMAL, TIMESTAMP, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Payment(Base):
    """All payment transactions across all payment methods"""

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subscription_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("subscriptions.id", ondelete="SET NULL")
    )
    amount_usd: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
    payment_method: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # zarinpal, nowpayments, stripe, flux, wallet
    status: Mapped[Optional[str]] = mapped_column(
        String(50), default="pending", index=True
    )  # pending, completed, failed, cancelled
    transaction_id: Mapped[Optional[str]] = mapped_column(
        String(255), index=True
    )  # External transaction ID
    deposit_to_wallet: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    extra_data: Mapped[Optional[Any]] = mapped_column(
        JSONB
    )  # Store gateway-specific data (renamed from 'metadata' - reserved by SQLAlchemy)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), index=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)

    # Relationships
    user = relationship("User", back_populates="payments")
    subscription = relationship("Subscription", back_populates="payments")
    wallet_transactions = relationship("WalletTransaction", back_populates="payment")
    referral_earnings = relationship("ReferralEarning", back_populates="payment")

    def __repr__(self):
        return f"<Payment(id={self.id}, user_id={self.user_id}, amount={self.amount_usd}, status={self.status})>"


class WalletTransaction(Base):
    """Wallet credit/debit transactions"""

    __tablename__ = "wallet_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    amount_usd: Mapped[Decimal] = mapped_column(
        DECIMAL(10, 2), nullable=False
    )  # Positive for credits, negative for debits
    transaction_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # deposit, purchase, withdrawal, refund, referral_commission
    payment_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("payments.id", ondelete="SET NULL")
    )
    subscription_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("subscriptions.id", ondelete="SET NULL")
    )
    reference_id: Mapped[Optional[str]] = mapped_column(
        String(255), index=True
    )  # External reference (e.g., zarinpal authority)
    status: Mapped[Optional[str]] = mapped_column(
        String(50), default="completed", index=True
    )  # pending, completed, failed
    description: Mapped[Optional[str]] = mapped_column(Text)
    balance_before: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(10, 2))
    balance_after: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(10, 2))
    extra_data: Mapped[Optional[Any]] = mapped_column(
        JSONB
    )  # Store gateway-specific data
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )

    # Relationships
    user = relationship("User", back_populates="wallet_transactions")
    payment = relationship("Payment", back_populates="wallet_transactions")

    def __repr__(self):
        return f"<WalletTransaction(id={self.id}, user_id={self.user_id}, type={self.transaction_type}, amount={self.amount_usd})>"


class WithdrawalRequest(Base):
    """User withdrawal requests requiring admin approval"""

    __tablename__ = "withdrawal_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount_usd: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
    withdrawal_method: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # zarinpal, bitcoin, ethereum, bank_transfer
    withdrawal_details: Mapped[Any] = mapped_column(
        JSONB, nullable=False
    )  # Card number, crypto address, etc.
    status: Mapped[Optional[str]] = mapped_column(
        String(50), default="pending", index=True
    )  # pending, approved, processing, completed, rejected
    admin_notes: Mapped[Optional[str]] = mapped_column(Text)
    processed_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), index=True
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)

    # Relationships
    user = relationship(
        "User", back_populates="withdrawal_requests", foreign_keys=[user_id]
    )
    processor = relationship("User", foreign_keys=[processed_by])

    def __repr__(self):
        return f"<WithdrawalRequest(id={self.id}, user_id={self.user_id}, amount={self.amount_usd}, status={self.status})>"
