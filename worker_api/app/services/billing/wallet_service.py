import logging
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.admins import Admin
from app.models.wallet_transaction_v2 import WalletTransactionV2

logger = logging.getLogger(__name__)


class WalletService:
    """Handles wallet balance operations with atomic locking."""

    def __init__(self, db: Session):
        self.db = db

    def get_balance(self, admin_id: int) -> Decimal:
        admin = self.db.query(Admin).filter(Admin.id == admin_id).first()
        if admin is None:
            return Decimal("0.00")
        # NOTE: wallet_balance has no server_default (only an ORM-side
        # default=0.00 applied on insert), so a legacy/pre-column row could
        # theoretically be NULL. Fall back to the column's own default
        # rather than let None escape this Decimal-typed return.
        return (
            admin.wallet_balance
            if admin.wallet_balance is not None
            else Decimal("0.00")
        )

    def credit_wallet(
        self,
        admin_id: int,
        amount_usd: Decimal,
        transaction_type: str,
        description: str = "",
    ) -> WalletTransactionV2:
        """Add funds to admin wallet. Atomic with row lock."""
        # Lock the admin row for atomic update
        admin = (
            self.db.query(Admin).filter(Admin.id == admin_id).with_for_update().first()
        )
        if not admin:
            raise ValueError(f"Admin {admin_id} not found")

        # NOTE: wallet_balance has no server_default, so a legacy row could
        # theoretically be NULL; treat NULL as the column's own default
        # (0.00) rather than raise on None + Decimal.
        balance_before = admin.wallet_balance or Decimal("0.00")
        admin.wallet_balance = balance_before + amount_usd
        balance_after = admin.wallet_balance

        txn = WalletTransactionV2(
            admin_id=admin_id,
            amount_usd=amount_usd,
            transaction_type=transaction_type,
            status="completed",
            description=description,
            balance_before=balance_before,
            balance_after=balance_after,
        )
        self.db.add(txn)
        self.db.commit()
        self.db.refresh(txn)

        logger.info(
            f"Credited ${amount_usd} to admin {admin_id} ({transaction_type}): "
            f"balance {balance_before} -> {balance_after}"
        )
        return txn

    def debit_wallet(
        self,
        admin_id: int,
        amount_usd: Decimal,
        transaction_type: str,
        user_id: Optional[int] = None,
        description: str = "",
    ) -> Optional[WalletTransactionV2]:
        """Deduct funds from admin wallet. Returns None if insufficient balance."""
        admin = (
            self.db.query(Admin).filter(Admin.id == admin_id).with_for_update().first()
        )
        if not admin:
            raise ValueError(f"Admin {admin_id} not found")

        # NOTE: wallet_balance has no server_default, so a legacy row could
        # theoretically be NULL; treat NULL as the column's own default
        # (0.00) rather than raise on None comparisons/arithmetic.
        balance_before = admin.wallet_balance or Decimal("0.00")
        if balance_before < amount_usd:
            logger.warning(
                f"Insufficient balance for admin {admin_id}: "
                f"{balance_before} < {amount_usd}"
            )
            return None

        admin.wallet_balance = balance_before - amount_usd
        balance_after = admin.wallet_balance

        txn = WalletTransactionV2(
            admin_id=admin_id,
            amount_usd=-amount_usd,  # Negative for debit
            transaction_type=transaction_type,
            status="completed",
            description=description,
            reference_id=str(user_id) if user_id else None,
            balance_before=balance_before,
            balance_after=balance_after,
        )
        self.db.add(txn)
        self.db.commit()
        self.db.refresh(txn)

        logger.info(
            f"Debited ${amount_usd} from admin {admin_id} ({transaction_type}): "
            f"balance {balance_before} -> {balance_after}"
        )
        return txn

    def has_positive_balance(self, admin_id: int) -> bool:
        admin = self.db.query(Admin).filter(Admin.id == admin_id).first()
        # NOTE: wallet_balance has no server_default; treat NULL as 0.00
        # (see credit_wallet) rather than raise on a None comparison.
        return admin is not None and (
            admin.wallet_balance or Decimal("0.00")
        ) > Decimal("0.00")

    def get_transactions(
        self,
        admin_id: int,
        page: int = 1,
        per_page: int = 20,
        transaction_type: Optional[str] = None,
    ) -> dict:
        """Get paginated transaction history for an admin."""
        query = self.db.query(WalletTransactionV2).filter(
            WalletTransactionV2.admin_id == admin_id
        )
        if transaction_type:
            query = query.filter(
                WalletTransactionV2.transaction_type == transaction_type
            )

        total = query.count()
        items = (
            query.order_by(WalletTransactionV2.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        return {"items": items, "total": total, "page": page, "per_page": per_page}
