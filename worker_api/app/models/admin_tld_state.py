"""AdminTldState — per-admin resolved TLD assignment.

One row per (admin, purpose). Holds BOTH the operator's pin intent
(``pinned_tld_id``) and the resolved reality (``effective_tld_id``), so a
migrate can change reality while preserving intent. ``effective_tld_id`` is
the single source of truth every reader (url_resolver, connection strings,
analytics) derives from.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import TIMESTAMP, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class AdminTldState(Base):
    """Per-admin, per-purpose TLD assignment (pin intent + effective reality)."""

    __tablename__ = "admin_tld_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    admin_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("admins.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    purpose: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # fdm|subscription|dashboard|admin_panel
    pinned_tld_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("registered_tlds.id", ondelete="SET NULL"),
        nullable=True,
    )
    effective_tld_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("registered_tlds.id", ondelete="SET NULL"),
        nullable=True,
        index=True,  # hot read column: migrate_off filters, analytics groups by it
    )
    source: Mapped[str] = mapped_column(
        String(12), nullable=False, default="unassigned"
    )  # pin|lb|unassigned
    assigned_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )
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
            "admin_id", "purpose", name="uq_admin_tld_state_admin_purpose"
        ),
    )

    def __repr__(self):
        return (
            f"<AdminTldState(admin_id={self.admin_id}, purpose={self.purpose}, "
            f"effective={self.effective_tld_id}, source={self.source})>"
        )
