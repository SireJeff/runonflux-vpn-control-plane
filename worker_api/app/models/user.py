"""
User model
Core user table with wallet, referrals, and trial tracking
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    DECIMAL,
    TIMESTAMP,
    BigInteger,
    Boolean,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class User(Base):
    """User model with comprehensive features"""

    __tablename__ = "users"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Telegram identification
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False, index=True
    )
    telegram_username: Mapped[Optional[str]] = mapped_column(String(255))

    # Contact information
    email: Mapped[Optional[str]] = mapped_column(String(255))
    flux_wallet_address: Mapped[Optional[str]] = mapped_column(String(255))

    # Referral system
    referral_code: Mapped[Optional[str]] = mapped_column(
        String(50), unique=True, index=True
    )
    referred_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    referral_tier: Mapped[Optional[str]] = mapped_column(
        String(50), default="bronze"
    )  # bronze, silver, gold, platinum
    total_referrals: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    referral_earnings_usd: Mapped[Optional[Decimal]] = mapped_column(
        DECIMAL(10, 2), default=0.00
    )

    # Wallet system
    wallet_balance: Mapped[Optional[Decimal]] = mapped_column(
        DECIMAL(10, 2), default=0.00
    )

    # Trial system
    trial_used: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    trial_started_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    trial_expires_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)

    # Multi-language support
    language: Mapped[Optional[str]] = mapped_column(
        String(5), default="en", index=True
    )  # en, fa, ar, ru, zh

    # Notification preferences
    notification_enabled: Mapped[Optional[bool]] = mapped_column(Boolean, default=True)

    # Permissions
    is_admin: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)

    # Compliance lifecycle (soft-delete retention flow)
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, nullable=True, index=True
    )
    deletion_scheduled_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, nullable=True, index=True
    )

    # Refresh token storage (for JWT refresh token rotation)
    refresh_token_jti: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, unique=True
    )
    refresh_token_expires_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, nullable=True
    )

    # Timestamps
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )

    # Relationships
    referrer = relationship("User", remote_side=[id], backref="referred_users")
    subscriptions = relationship(
        "Subscription", back_populates="user", cascade="all, delete-orphan"
    )
    payments = relationship(
        "Payment", back_populates="user", cascade="all, delete-orphan"
    )
    wallet_transactions = relationship(
        "WalletTransaction", back_populates="user", cascade="all, delete-orphan"
    )
    withdrawal_requests = relationship(
        "WithdrawalRequest",
        back_populates="user",
        foreign_keys="WithdrawalRequest.user_id",
        cascade="all, delete-orphan",
    )
    credentials = relationship(
        "UserCredential", back_populates="user", cascade="all, delete-orphan"
    )
    protocol_assignments = relationship(
        "UserProtocolAssignment", back_populates="user", cascade="all, delete-orphan"
    )
    ip_change_requests = relationship(
        "IPChangeRequest", back_populates="user", cascade="all, delete-orphan"
    )
    ip_change_quotas = relationship(
        "IPChangeQuota", back_populates="user", cascade="all, delete-orphan"
    )
    trial_activation = relationship(
        "TrialActivation",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    support_tickets = relationship(
        "SupportTicket",
        back_populates="user",
        foreign_keys="SupportTicket.user_id",
        cascade="all, delete-orphan",
    )
    connection_logs = relationship(
        "ConnectionLog", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return (
            f"<User(id={self.id}, telegram_user_id={self.telegram_user_id}, "
            f"username={self.telegram_username}, is_deleted={self.is_deleted})>"
        )
