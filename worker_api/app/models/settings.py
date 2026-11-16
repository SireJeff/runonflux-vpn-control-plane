"""
System settings model
Persistent platform-wide configuration values.
"""

from decimal import Decimal

from sqlalchemy import Boolean, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SystemSettings(Base):
    """Singleton-style system settings table."""

    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    trial_days: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    referral_commission_bronze: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=5.00
    )
    referral_commission_silver: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=10.00
    )
    referral_commission_gold: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=15.00
    )
    referral_commission_platinum: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=20.00
    )
    maintenance_mode: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    max_ip_changes_per_month: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3
    )
