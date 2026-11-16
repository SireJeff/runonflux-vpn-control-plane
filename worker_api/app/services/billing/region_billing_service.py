import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.admin_users import AdminUser
from app.models.platform_settings import PlatformSetting
from app.models.user_regions import UserRegion

from .wallet_service import WalletService

logger = logging.getLogger(__name__)


class RegionBillingService:
    """Handles monthly region subscription charges."""

    def __init__(self, db: Session):
        self.db = db
        self.wallet_service = WalletService(db)

    def _get_region_price(self) -> Decimal:
        setting = (
            self.db.query(PlatformSetting)
            .filter(PlatformSetting.key == "price_per_region_monthly")
            .first()
        )
        return Decimal(setting.value) if setting else Decimal("2.00")

    def charge_monthly_regions(self) -> dict:
        """Charge the monthly fee for every active non-primary region whose
        per-region clock has elapsed. Primary regions are free (never charged).

        Called daily by Celery beat. Additive: a successful charge pushes the
        region's clock 30 days forward; an insufficient balance suspends the
        non-primary region (primary access is unaffected).
        """
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        price = self._get_region_price()

        due_regions = (
            self.db.query(UserRegion)
            .filter(
                UserRegion.is_primary == False,  # noqa: E712
                UserRegion.status == "active",
                UserRegion.region_expires_at != None,  # noqa: E711
                UserRegion.region_expires_at < now,
            )
            .all()
        )

        charged = 0
        suspended = 0
        errors = 0

        for region in due_regions:
            user = (
                self.db.query(AdminUser).filter(AdminUser.id == region.user_id).first()
            )
            if not user or user.status != "active":
                continue

            txn = self.wallet_service.debit_wallet(
                admin_id=user.admin_id,
                amount_usd=price,
                transaction_type="debit_region",
                user_id=user.id,
                description=f"Monthly region charge: {region.macro_region} for user {user.username}",
            )

            if txn:
                region.region_expires_at = now + timedelta(days=30)
                charged += 1
            else:
                region.status = "suspended"
                suspended += 1
                logger.info(
                    f"Suspended region {region.macro_region} for user {user.username} "
                    f"(insufficient balance)"
                )

        self.db.commit()
        return {"charged": charged, "suspended": suspended, "errors": errors}
