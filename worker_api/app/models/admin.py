"""
Admin & Monitoring models
Support tickets, messages, admin alerts, and referral earnings
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    DECIMAL,
    TIMESTAMP,
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym
from sqlalchemy.sql import func

from app.core.database import Base


class SupportTicket(Base):
    """Customer support ticket system"""

    __tablename__ = "support_tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ticket_number: Mapped[Optional[str]] = mapped_column(
        String(32), unique=True, index=True
    )
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[Optional[str]] = mapped_column(
        String(50), default="other", index=True
    )
    status: Mapped[Optional[str]] = mapped_column(
        String(50), default="open", index=True
    )  # open, pending, resolved, closed
    priority: Mapped[Optional[str]] = mapped_column(
        String(50), default="medium"
    )  # low, medium, high, urgent
    assigned_to: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    telegram_message_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)

    # Relationships
    user = relationship(
        "User", back_populates="support_tickets", foreign_keys=[user_id]
    )
    assignee = relationship("User", foreign_keys=[assigned_to])
    messages = relationship(
        "SupportMessage", back_populates="ticket", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<SupportTicket(id={self.id}, user_id={self.user_id}, status={self.status}, priority={self.priority})>"


class SupportMessage(Base):
    """Support ticket messages (user ↔ admin)"""

    __tablename__ = "support_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ticket_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False
    )
    sender_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_admin: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    is_internal: Mapped[Optional[bool]] = mapped_column(
        Boolean, default=False
    )  # Internal admin notes not visible to user
    telegram_message_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    read_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )

    # Backward-compatible aliases for legacy endpoint contracts.
    user_id = synonym("sender_id")
    is_staff = synonym("is_admin")

    # Relationships
    ticket = relationship("SupportTicket", back_populates="messages")

    __table_args__ = (
        Index(
            "idx_support_messages_unread",
            "ticket_id",
            "read_at",
            postgresql_where=read_at.is_(None),
        ),
    )

    def __repr__(self):
        return f"<SupportMessage(id={self.id}, ticket_id={self.ticket_id}, is_admin={self.is_admin})>"


class AdminAlert(Base):
    """System alerts for administrators"""

    __tablename__ = "admin_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    alert_type: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # system_down, payment_failure, database_issue, etc.
    priority: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # low, medium, high, critical
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    extra_data: Mapped[Optional[Any]] = mapped_column(
        JSONB
    )  # Additional context (renamed from 'metadata' - reserved by SQLAlchemy)
    sent_telegram: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    sent_email: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    acknowledged: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    acknowledged_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL")
    )
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )

    # Relationships
    acknowledger = relationship("User")

    __table_args__ = (
        Index(
            "idx_admin_alerts_unacknowledged",
            "acknowledged",
            postgresql_where=(acknowledged == False),
        ),
    )

    def __repr__(self):
        return f"<AdminAlert(id={self.id}, type={self.alert_type}, priority={self.priority}, acknowledged={self.acknowledged})>"


class ReferralEarning(Base):
    """Tiered referral commission tracking"""

    __tablename__ = "referral_earnings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    referrer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    referred_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payment_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("payments.id", ondelete="SET NULL")
    )
    commission_percent: Mapped[Decimal] = mapped_column(
        DECIMAL(5, 2), nullable=False
    )  # e.g., 10.00, 15.00, 20.00, 25.00
    amount_usd: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
    credited_to_wallet: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )

    # Relationships
    referrer = relationship("User", foreign_keys=[referrer_id])
    referred_user = relationship("User", foreign_keys=[referred_user_id])
    payment = relationship("Payment", back_populates="referral_earnings")

    def __repr__(self):
        return f"<ReferralEarning(id={self.id}, referrer_id={self.referrer_id}, amount={self.amount_usd})>"
