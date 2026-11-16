"""
UserRegion model for FluxVPN Reseller Platform
Multiple macro regions per user (eu, as, na, row). Exactly one row is primary.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import TIMESTAMP, Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class UserRegion(Base):
    __tablename__ = "user_regions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("admin_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    macro_region: Mapped[str] = mapped_column(
        String(5), nullable=False
    )  # eu, as, na, row
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )  # exactly one per user
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="active"
    )  # active, suspended
    region_expires_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, nullable=True
    )  # per-region monthly billing clock; NULL for primary (free)
    activated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )

    user = relationship("AdminUser", back_populates="regions")

    __table_args__ = (
        UniqueConstraint("user_id", "macro_region", name="uq_user_region_user_macro"),
    )

    def __repr__(self):
        return f"<UserRegion(id={self.id}, user_id={self.user_id}, macro={self.macro_region}, primary={self.is_primary})>"
