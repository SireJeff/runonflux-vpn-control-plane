"""
AdminReferralConfig + AdminReferralEarning — per-reseller referral program.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import TIMESTAMP, Boolean, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class AdminReferralConfig(Base):
    """Per-reseller referral program configuration."""

    __tablename__ = "admin_referral_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    admin_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("admins.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reward_percentage: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        server_default="10.00",
    )
    reward_type: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="cashback"
    )  # cashback | traffic | both
    traffic_per_referral_mb: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    traffic_max_bonus_mb: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    # Relationships
    admin = relationship("Admin", back_populates="referral_config")

    def __repr__(self):
        return f"<AdminReferralConfig(id={self.id}, admin_id={self.admin_id}, enabled={self.is_enabled})>"


class AdminReferralEarning(Base):
    """Audit row for one referral commission credit."""

    __tablename__ = "admin_referral_earnings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    admin_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("admins.id", ondelete="CASCADE"),
        nullable=False,
    )
    referrer_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("admin_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    referred_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("admin_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    order_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("user_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    commission_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    amount_tomans: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )

    # Relationships — disambiguate two FKs pointing to admin_users.id
    referrer = relationship("AdminUser", foreign_keys=[referrer_user_id])
    referred = relationship("AdminUser", foreign_keys=[referred_user_id])
    order = relationship("UserOrder", foreign_keys=[order_id])

    def __repr__(self):
        return f"<AdminReferralEarning(id={self.id}, admin_id={self.admin_id}, amount={self.amount_tomans})>"
