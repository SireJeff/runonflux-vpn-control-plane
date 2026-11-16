"""AdminFreeConfig — one shared free public config per reseller.

kind='shared' (built now) means shared_credential_ref points at a hidden
system admin_user's subscription_token. kind='per_user' is reserved for a
later free-tier extension.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    TIMESTAMP, Boolean, ForeignKey, Integer, Numeric, String, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class AdminFreeConfig(Base):
    __tablename__ = "admin_free_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    admin_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("admins.id", ondelete="CASCADE"), nullable=False
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    kind: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="shared"
    )
    label: Mapped[Optional[str]] = mapped_column(String(100))
    region: Mapped[Optional[str]] = mapped_column(String(5))
    traffic_limit_gb: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    duration_days: Mapped[Optional[int]] = mapped_column(Integer)
    daily_limit_mb: Mapped[Optional[int]] = mapped_column(Integer)
    max_free_users: Mapped[Optional[int]] = mapped_column(Integer)
    shared_credential_ref: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    __table_args__ = (
        UniqueConstraint("admin_id", name="uq_admin_free_configs_admin_id"),
    )
