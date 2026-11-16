"""AdminRoutingConfig — one per-reseller routing rule set.

Holds ban/allow website lists + curated presets, injected into the reseller's
end-users' sing-box configs. Mirrors the admin_free_configs one-row-per-admin
pattern.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import TIMESTAMP, Boolean, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class AdminRoutingConfig(Base):
    __tablename__ = "admin_routing_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    admin_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("admins.id", ondelete="CASCADE"), nullable=False
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    rules: Mapped[Any] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    __table_args__ = (
        UniqueConstraint("admin_id", name="uq_admin_routing_configs_admin_id"),
    )
