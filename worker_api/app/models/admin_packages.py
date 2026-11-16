"""
AdminPackage model — subscription plans defined by each reseller.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class AdminPackage(Base):
    """Reseller-defined subscription plan (traffic/duration/price)."""

    __tablename__ = "admin_packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    admin_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("admins.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    traffic_limit_gb: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    price_tomans: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    region_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="1"
    )  # 1..4; ignored when all_regions
    all_regions: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )  # grants every currently-available region
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    display_order: Mapped[Optional[int]] = mapped_column(Integer, server_default="0")
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    # Relationships
    admin = relationship("Admin", back_populates="packages")
    orders = relationship("UserOrder", back_populates="package")

    __table_args__ = (
        UniqueConstraint("admin_id", "name", name="uq_admin_packages_admin_name"),
    )

    def __repr__(self):
        return (
            f"<AdminPackage(id={self.id}, admin_id={self.admin_id}, name={self.name})>"
        )
