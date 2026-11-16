"""AdminUserWalletTxn — end-user wallet ledger (Tomans).

One row per movement of admin_users.wallet_credit_tomans. type is one of
topup | spend | referral | refund. amount_tomans is signed (positive =
credit, negative = debit); balance_after snapshots the resulting balance.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import TIMESTAMP, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class AdminUserWalletTxn(Base):
    __tablename__ = "admin_user_wallet_txns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("admin_users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    admin_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("admins.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    amount_tomans: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    order_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user_orders.id", ondelete="SET NULL"), nullable=True
    )
    balance_after: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )

    def __repr__(self) -> str:
        return (
            f"<AdminUserWalletTxn(id={self.id}, user_id={self.user_id}, "
            f"type={self.type}, amount={self.amount_tomans})>"
        )
