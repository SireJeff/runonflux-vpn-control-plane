"""
UserAdjustment — audit trail for reseller-driven manual subscription changes.
One row per manual action (extend_days, topup_gb, set_expiry, reapply_plan, edit_regions).
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import TIMESTAMP, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class UserAdjustment(Base):
    __tablename__ = "user_adjustments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("admin_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    admin_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("admins.id"), nullable=False
    )
    action: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # extend_days, topup_gb, set_expiry, reapply_plan, edit_regions
    details: Mapped[Any] = mapped_column(
        JSONB, nullable=False
    )  # e.g. {"days": 30, "from": "...", "to": "..."}
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), index=True
    )

    user = relationship("AdminUser", foreign_keys=[user_id])

    def __repr__(self):
        return f"<UserAdjustment(id={self.id}, user_id={self.user_id}, action={self.action})>"
