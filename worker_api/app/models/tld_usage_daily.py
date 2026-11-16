"""TldUsageDaily — daily snapshot of per-TLD active-user counts (analytics).

Frozen ``domain_snapshot`` so history survives a TLD soft-delete (spec D7).
Populated by the ``analytics.tld_snapshot`` beat task from the SAME
``active_user_counts`` query the load-balancer uses — the analytics history
can never disagree with live routing (drift-proof).
"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import TIMESTAMP, Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class TldUsageDaily(Base):
    """One row per (day, purpose, tld): the active-user count on that day."""

    __tablename__ = "tld_usage_daily"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # fdm|subscription|dashboard|admin_panel
    tld_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("registered_tlds.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    domain_snapshot: Mapped[str] = mapped_column(
        String(255), nullable=False
    )  # frozen; survives soft-delete
    active_user_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )

    __table_args__ = (
        UniqueConstraint(
            "snapshot_date",
            "purpose",
            "tld_id",
            name="uq_tld_usage_daily_date_purpose_tld",
        ),
    )

    def __repr__(self):
        return (
            f"<TldUsageDaily(date={self.snapshot_date}, purpose={self.purpose}, "
            f"tld_id={self.tld_id}, count={self.active_user_count})>"
        )
