"""
WalletTransactionV2 model for FluxVPN Reseller Platform
Wallet transactions for admin reseller accounts (credit/debit tracking)
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import TIMESTAMP, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class WalletTransactionV2(Base):
    """Wallet transaction for admin reseller accounts"""

    __tablename__ = "wallet_transactions_v2"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    admin_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("admins.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    transaction_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # credit_manual, credit_wire, purchase, subscription, etc.
    status: Mapped[Optional[str]] = mapped_column(
        String(20), default="completed", index=True
    )  # pending, completed, failed
    description: Mapped[Optional[str]] = mapped_column(Text)
    reference_id: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    balance_before: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    balance_after: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))
    extra_data: Mapped[Optional[Any]] = mapped_column(JSONB)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )

    # Relationships
    admin = relationship("Admin", back_populates="wallet_transactions")

    def __repr__(self):
        return f"<WalletTransactionV2(id={self.id}, admin_id={self.admin_id}, type={self.transaction_type}, amount={self.amount_usd})>"
