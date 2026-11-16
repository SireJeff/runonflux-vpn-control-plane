from datetime import datetime
from typing import Optional

from sqlalchemy import TIMESTAMP, Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class FreeConfigEnrollment(Base):
    """Per-user free-tier bookkeeping (identity/credentials live on AdminUser)."""

    __tablename__ = "free_config_enrollments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("admin_users.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )
    admin_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("admins.id", ondelete="CASCADE"), nullable=False, index=True
    )
    claimed_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )
    last_membership_check_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    membership_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    suspended_reason: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )
