"""
UserOrder model — end-user purchase and receipt tracking.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import TIMESTAMP, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class UserOrder(Base):
    """End-user's order for a package, with receipt and approval state."""

    __tablename__ = "user_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("admin_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    admin_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("admins.id"), nullable=False
    )
    package_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("admin_packages.id", ondelete="SET NULL"),
    )
    package_snapshot: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    kind: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="subscription"
    )
    macro_region: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    macro_regions: Mapped[Optional[Any]] = mapped_column(
        JSONB, nullable=True
    )  # full picked set, e.g. ["eu","as"]; macro_region = macro_regions[0]
    amount_tomans: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    wallet_credit_applied_tomans: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        server_default="0",
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="pending"
    )
    receipt_file_id: Mapped[Optional[str]] = mapped_column(String(255))
    receipt_file_unique_id: Mapped[Optional[str]] = mapped_column(String(255))
    receipt_local_path: Mapped[Optional[str]] = mapped_column(String(500))
    reviewer_admin_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("admins.id")
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    admin_notes: Mapped[Optional[str]] = mapped_column(Text)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    # Crypto payment (MVP) — payment_method 'card' (default, receipt photo) | 'crypto'.
    # For crypto, crypto_txid replaces the receipt; amount_usd_snapshot records the
    # converted USD at submission (display/audit; activation stays Toman-based).
    payment_method: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="card"
    )
    crypto_txid: Mapped[Optional[str]] = mapped_column(String(255))
    crypto_link: Mapped[Optional[str]] = mapped_column(Text)
    amount_usd_snapshot: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))

    # Relationships — disambiguate two FKs pointing to admins.id
    user = relationship("AdminUser", foreign_keys=[user_id])
    admin = relationship("Admin", back_populates="orders", foreign_keys=[admin_id])
    package = relationship("AdminPackage", foreign_keys=[package_id])
    reviewer = relationship("Admin", foreign_keys=[reviewer_admin_id])

    def __repr__(self):
        return (
            f"<UserOrder(id={self.id}, user_id={self.user_id}, status={self.status})>"
        )
