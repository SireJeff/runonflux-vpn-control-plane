import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.admins import Admin
from app.models.platform_settings import PlatformSetting
from app.models.wire_orders import WireOrder

from .wallet_service import WalletService

logger = logging.getLogger(__name__)


class WireOrderService:
    """Handles wire transfer order lifecycle."""

    def __init__(self, db: Session):
        self.db = db
        self.wallet_service = WalletService(db)

    def _get_exchange_rate(self) -> Decimal:
        """Toman-per-USD rate (Tomans per 1 USD). See services.billing.conversion."""
        from app.services.billing.conversion import get_toman_per_usd_rate

        return get_toman_per_usd_rate(self.db)

    def create_order(
        self,
        admin_id: int,
        amount_tomans: Decimal,
        contact_telegram: str,
        contact_whatsapp: Optional[str] = None,
        contact_phone: Optional[str] = None,
        notes: Optional[str] = None,
        payment_method: str = "wire",
        amount_usd: Optional[Decimal] = None,
        crypto_txid: Optional[str] = None,
        crypto_link: Optional[str] = None,
        usd_rate_snapshot: Optional[Decimal] = None,
    ) -> WireOrder:
        """Create a new wallet top-up order (wire or crypto).

        For crypto, amount_usd is the snapshotted source of truth for the credit;
        amount_tomans is the computed display value. For wire, amount_usd is left
        None and filled at approval (unchanged).
        """
        order = WireOrder(
            admin_id=admin_id,
            amount_tomans=amount_tomans,
            amount_usd=amount_usd if payment_method == "crypto" else None,
            contact_telegram=contact_telegram,
            contact_whatsapp=contact_whatsapp,
            contact_phone=contact_phone,
            notes=notes,
            status="pending",
            payment_method=payment_method,
            crypto_txid=crypto_txid,
            crypto_link=crypto_link,
            usd_rate_snapshot=usd_rate_snapshot,
        )
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)

        logger.info(
            f"Wire order {order.id} created by admin {admin_id}: "
            f"{amount_tomans} Tomans ({payment_method})"
        )
        return order

    def approve_order(
        self, order_id: int, reviewed_by: int, exchange_rate: Optional[Decimal] = None
    ) -> WireOrder:
        """Approve a wire order and credit the admin's wallet."""
        order = self.db.query(WireOrder).filter(WireOrder.id == order_id).first()
        if not order:
            raise ValueError(f"Order {order_id} not found")
        if order.status != "pending":
            raise ValueError(f"Order {order_id} is {order.status}, not pending")

        rate = exchange_rate or self._get_exchange_rate()
        amount_usd = (order.amount_tomans / rate).quantize(Decimal("0.01"))

        order.status = "approved"
        order.amount_usd = amount_usd
        order.reviewed_by = reviewed_by
        order.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)

        # Credit wallet
        self.wallet_service.credit_wallet(
            admin_id=order.admin_id,
            amount_usd=amount_usd,
            transaction_type="credit_wire",
            description=f"Wire transfer: {order.amount_tomans} Tomans (order #{order.id})",
        )

        self.db.commit()
        self.db.refresh(order)

        logger.info(
            f"Wire order {order.id} approved: {order.amount_tomans} T = ${amount_usd}"
        )
        return order

    def reject_order(
        self, order_id: int, reviewed_by: int, admin_notes: Optional[str] = None
    ) -> WireOrder:
        """Reject a wire order."""
        order = self.db.query(WireOrder).filter(WireOrder.id == order_id).first()
        if not order:
            raise ValueError(f"Order {order_id} not found")
        if order.status != "pending":
            raise ValueError(f"Order {order_id} is {order.status}, not pending")

        order.status = "rejected"
        order.admin_notes = admin_notes
        order.reviewed_by = reviewed_by
        order.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)

        self.db.commit()
        self.db.refresh(order)

        logger.info(f"Wire order {order.id} rejected")
        return order
