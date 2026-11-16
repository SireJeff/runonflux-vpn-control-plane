"""Single write path for the end-user wallet (admin_users.wallet_credit_tomans).

Every mutation of an end-user's Toman balance should go through
record_wallet_txn so the admin_user_wallet_txns ledger stays complete.
"""

from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.admin_user_wallet_txn import AdminUserWalletTxn
from app.models.admin_users import AdminUser


def record_wallet_txn(
    db: Session,
    user: AdminUser,
    amount_tomans: Decimal,
    txn_type: str,
    order_id: Optional[int] = None,
) -> AdminUserWalletTxn:
    """Apply a signed balance change and append a ledger row (no commit).

    amount_tomans > 0 credits, < 0 debits. Raises ValueError if a debit
    would push the balance below zero.
    """
    # Re-fetch the row under a row lock so concurrent balance changes
    # serialize at the DB level (mirrors wallet_service.credit/debit_wallet).
    # Within one Session, querying by PK returns the same identity-mapped
    # instance, so the caller's `user` reflects the new balance after flush.
    # On SQLite (unit suite) with_for_update() is a no-op; that's expected.
    locked = (
        db.query(AdminUser)
        .filter(AdminUser.id == user.id)
        .with_for_update()
        .first()
    )
    if locked is None:
        raise ValueError("Wallet user not found")

    current = locked.wallet_credit_tomans or Decimal("0")
    new_balance = current + amount_tomans
    if new_balance < 0:
        raise ValueError("Insufficient wallet balance")

    locked.wallet_credit_tomans = new_balance
    txn = AdminUserWalletTxn(
        user_id=locked.id,
        admin_id=locked.admin_id,
        amount_tomans=amount_tomans,
        type=txn_type,
        order_id=order_id,
        balance_after=new_balance,
    )
    db.add(txn)
    db.flush()
    return txn
