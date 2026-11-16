"""FDM per-IP liveness state (Problem B endpoint-liveness gating).

Tracks any-port-alive liveness with N-cycle hysteresis per
(flux_app_name, ip_address). See
docs/superpowers/specs/2026-08-01-fdm-endpoint-liveness-design.md.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import TIMESTAMP, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class FdmIpLiveness(Base):
    """Per-(app, IP) liveness hysteresis for FDM endpoint gating."""

    __tablename__ = "fdm_ip_liveness"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    flux_app_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    ip_address: Mapped[str] = mapped_column(INET, nullable=False, index=True)
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    last_live_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    demoted_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    __table_args__ = (
        UniqueConstraint(
            "flux_app_name", "ip_address", name="uq_fdm_ip_liveness_app_ip"
        ),
    )
