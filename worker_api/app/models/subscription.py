"""
Subscription models
Protocols, subscription plans, and user subscriptions
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    DECIMAL,
    TIMESTAMP,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Protocol(Base):
    """VPN protocols available on the platform"""

    __tablename__ = "protocols"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    slug: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False
    )  # URL-friendly protocol identifier
    display_name: Mapped[Optional[str]] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(Text)
    flux_app_name: Mapped[Optional[str]] = mapped_column(
        String(255)
    )  # e.g., 'fluxvpn-shadowsocks'
    default_port: Mapped[Optional[int]] = mapped_column(
        Integer
    )  # Internal container port
    exposed_port: Mapped[Optional[int]] = mapped_column(
        Integer
    )  # External FluxCloud port
    is_active: Mapped[Optional[bool]] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )

    # Relationships
    instances = relationship(
        "ProtocolInstance", back_populates="protocol", cascade="all, delete-orphan"
    )
    credentials = relationship("UserCredential", back_populates="protocol")
    protocol_assignments = relationship(
        "UserProtocolAssignment", back_populates="protocol"
    )

    def __repr__(self):
        return f"<Protocol(id={self.id}, name={self.name}, active={self.is_active})>"


class SubscriptionPlan(Base):
    """Subscription plans (16 plans: 4 tiers × 4 durations + 1 trial)"""

    __tablename__ = "subscription_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    tier: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # bronze, silver, gold, platinum
    duration_months: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True
    )  # 1, 3, 6, 12 (0 for trial)
    price_usd: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
    max_protocols: Mapped[Optional[int]] = mapped_column(Integer, default=1)
    max_connections: Mapped[Optional[int]] = mapped_column(Integer, default=1)
    data_limit_gb: Mapped[Optional[int]] = mapped_column(Integer)  # NULL = unlimited
    daily_ip_changes: Mapped[Optional[int]] = mapped_column(Integer, default=1)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )

    # Relationships
    subscriptions = relationship("Subscription", back_populates="plan")

    def __repr__(self):
        return f"<SubscriptionPlan(id={self.id}, name={self.name}, tier={self.tier}, duration={self.duration_months})>"


class Subscription(Base):
    """User subscriptions with auto-renewal support"""

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subscription_plans.id"), nullable=False
    )
    status: Mapped[Optional[str]] = mapped_column(
        String(50), default="active", index=True
    )  # active, expired, cancelled, pending
    is_active: Mapped[Optional[bool]] = mapped_column(
        Boolean, default=True, index=True
    )  # Quick lookup for active subscriptions
    is_trial: Mapped[Optional[bool]] = mapped_column(
        Boolean, default=False, index=True
    )  # Trial subscription flag
    started_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, index=True)
    auto_renew: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )

    # Relationships
    user = relationship("User", back_populates="subscriptions")
    plan = relationship("SubscriptionPlan", back_populates="subscriptions")
    payments = relationship("Payment", back_populates="subscription")
    credentials = relationship(
        "UserCredential", back_populates="subscription", cascade="all, delete-orphan"
    )
    protocol_assignments = relationship(
        "UserProtocolAssignment",
        back_populates="subscription",
        cascade="all, delete-orphan",
    )
    renewal_warnings = relationship(
        "RenewalWarning", back_populates="subscription", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index(
            "idx_subscriptions_active_user",
            "user_id",
            "status",
            postgresql_where=(status == "active"),
        ),
    )

    def __repr__(self):
        return f"<Subscription(id={self.id}, user_id={self.user_id}, plan_id={self.plan_id}, status={self.status})>"
