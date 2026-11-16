"""
UX Enhancement models
Trial activations, renewal warnings, connection violations, usage alerts, and translations
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
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class TrialActivation(Base):
    """3-day free trial tracking and conversion"""

    __tablename__ = "trial_activations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, index=True
    )
    telegram_username: Mapped[Optional[str]] = mapped_column(String(255))
    started_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, index=True)
    converted_to_paid: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    conversion_date: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)

    # Relationships
    user = relationship("User", back_populates="trial_activation")

    def __repr__(self):
        return f"<TrialActivation(id={self.id}, user_id={self.user_id}, converted={self.converted_to_paid})>"


class RenewalWarning(Base):
    """Track auto-renewal warnings sent to users"""

    __tablename__ = "renewal_warnings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    subscription_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    days_before_expiration: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # 3, 2, or 1
    sent_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), index=True
    )
    user_action: Mapped[Optional[str]] = mapped_column(
        String(50)
    )  # ignored, renewed, cancelled

    # Relationships
    subscription = relationship("Subscription", back_populates="renewal_warnings")

    __table_args__ = (
        UniqueConstraint(
            "subscription_id",
            "days_before_expiration",
            name="uq_subscription_warning_days",
        ),
    )

    def __repr__(self):
        return f"<RenewalWarning(id={self.id}, subscription_id={self.subscription_id}, days={self.days_before_expiration})>"


class ConnectionViolation(Base):
    """Connection limit violation tracking with grace period"""

    __tablename__ = "connection_violations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    subscription_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False
    )
    protocol_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("protocols.id", ondelete="CASCADE"), nullable=False
    )
    max_allowed: Mapped[int] = mapped_column(Integer, nullable=False)
    attempted_connections: Mapped[int] = mapped_column(Integer, nullable=False)
    violation_time: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )
    action_taken: Mapped[Optional[str]] = mapped_column(
        String(50)
    )  # warning, grace_period, blocked

    def __repr__(self):
        return f"<ConnectionViolation(id={self.id}, user_id={self.user_id}, max={self.max_allowed}, attempted={self.attempted_connections})>"


class UsageAlert(Base):
    """Data usage threshold alerts (50%, 80%, 90%)"""

    __tablename__ = "usage_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subscription_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False
    )
    threshold_percent: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # 50, 80, 90
    data_limit_gb: Mapped[int] = mapped_column(Integer, nullable=False)
    data_used_gb: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )

    __table_args__ = (
        UniqueConstraint(
            "subscription_id", "threshold_percent", name="uq_subscription_threshold"
        ),
    )

    def __repr__(self):
        return f"<UsageAlert(id={self.id}, user_id={self.user_id}, threshold={self.threshold_percent}%)>"


class Translation(Base):
    """Multi-language support (5 languages: en, fa, ar, ru, zh)"""

    __tablename__ = "translations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    language: Mapped[str] = mapped_column(
        String(5), nullable=False
    )  # en, fa, ar, ru, zh
    value: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[Optional[str]] = mapped_column(
        String(255)
    )  # Optional context for translators
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    __table_args__ = (
        UniqueConstraint("key", "language", name="uq_translation_key_language"),
    )

    def __repr__(self):
        return f"<Translation(id={self.id}, key={self.key}, language={self.language})>"
