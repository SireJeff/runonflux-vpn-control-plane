"""Registered TLD model for multi-provider DNS management"""

from datetime import datetime
from typing import Optional

from sqlalchemy import TIMESTAMP, Boolean, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base

# Valid TLD purposes. admin_panel is new in the multi-TLD feature.
PURPOSES = ("fdm", "subscription", "dashboard", "admin_panel")


class RegisteredTld(Base):
    """Registered top-level domain with DNS provider assignment.

    Multi-active: many rows per purpose may have is_active=True (membership in
    the load-balancing pool). Soft-deleted via deleted_at (kept for analytics).
    """

    __tablename__ = "registered_tlds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    dns_provider: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # "cloudflare" or "arvancloud"
    zone_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )  # Cloudflare zone ID (null for ArvanCloud)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    server_ip: Mapped[Optional[str]] = mapped_column(
        String(45), nullable=True
    )  # Auto-detected for subscription/dashboard
    is_active: Mapped[Optional[bool]] = mapped_column(
        Boolean, default=False, index=True
    )  # pool membership (multi-active)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, nullable=True
    )  # soft-delete tombstone
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    # Convenience alias mirroring the module constant on the class.
    PURPOSES = PURPOSES

    __table_args__ = (
        UniqueConstraint("domain", "purpose", name="uq_registered_tlds_domain_purpose"),
    )

    def __repr__(self):
        return f"<RegisteredTld(id={self.id}, domain={self.domain}, purpose={self.purpose}, active={self.is_active})>"
