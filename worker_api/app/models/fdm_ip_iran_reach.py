"""FDM per-IP Iran reachability state (check-host.net Iranian probe nodes).

Kept in its own table, not as columns on fdm_ip_liveness, so a missing or
failed migration can only disable this feature: the liveness gate's model is
untouched. See app/services/fdm/iran_reach.py.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import TIMESTAMP, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class FdmIpIranReach(Base):
    """Per-(app, IP) Iran reachability with blocked-verdict hysteresis."""

    __tablename__ = "fdm_ip_iran_reach"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    flux_app_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    ip_address: Mapped[str] = mapped_column(INET, nullable=False, index=True)
    # Port the last check targeted (the app's VLESS port, else Trojan, else any).
    port: Mapped[Optional[int]] = mapped_column(Integer)
    # check-host request submitted on one task run, collected on the next.
    pending_request_id: Mapped[Optional[str]] = mapped_column(String(64))
    submitted_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    # Last time a check reached a verdict (any verdict, incl. inconclusive).
    checked_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    blocked_streak: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # Set once blocked_streak reaches FDM_IRAN_REACH_BLOCKED_CHECKS; cleared by
    # the first REACHABLE verdict. Non-NULL = excluded from FDM serving.
    blocked_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    last_verdict: Mapped[Optional[str]] = mapped_column(String(16))
    last_summary: Mapped[Optional[str]] = mapped_column(String(255))
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
            "flux_app_name", "ip_address", name="uq_fdm_ip_iran_reach_app_ip"
        ),
    )
