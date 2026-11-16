"""
WireOrder model for FluxVPN Reseller Platform
Wire transfer payment orders from admin resellers
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import TIMESTAMP, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class WireOrder(Base):
    """Wire transfer payment order submitted by an admin reseller"""

    __tablename__ = "wire_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    admin_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("admins.id"), nullable=False, index=True
    )
    amount_tomans: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    amount_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    contact_telegram: Mapped[str] = mapped_column(String(50), nullable=False)
    contact_whatsapp: Mapped[Optional[str]] = mapped_column(String(20))
    contact_phone: Mapped[Optional[str]] = mapped_column(String(20))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[Optional[str]] = mapped_column(
        String(20), default="pending"
    )  # pending/approved/rejected/cancelled
    admin_notes: Mapped[Optional[str]] = mapped_column(Text)
    reviewed_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("admins.id"))
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )
    # Crypto payment (MVP) — payment_method 'wire' (default) | 'crypto'.
    # For crypto, amount_usd is set at submission (source of truth); amount_tomans
    # is a computed display value using usd_rate_snapshot (Tomans per 1 USD).
    payment_method: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="wire"
    )
    crypto_txid: Mapped[Optional[str]] = mapped_column(String(255))
    crypto_link: Mapped[Optional[str]] = mapped_column(Text)
    usd_rate_snapshot: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))

    # Relationships
    admin = relationship("Admin", back_populates="wire_orders", foreign_keys=[admin_id])
    reviewer = relationship("Admin", foreign_keys=[reviewed_by])

    def __repr__(self):
        return f"<WireOrder(id={self.id}, admin_id={self.admin_id}, amount_tomans={self.amount_tomans}, status={self.status})>"
