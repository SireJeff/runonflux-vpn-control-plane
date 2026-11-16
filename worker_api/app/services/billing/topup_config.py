"""Resolve the effective minimum top-up amount for a reseller."""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.admin_bots import AdminBot
from app.models.platform_settings import PlatformSetting

_DEFAULT_MIN_TOPUP = Decimal("500000")


def effective_min_topup_tomans(db: Session, admin_id: int) -> Decimal:
    bot = db.query(AdminBot).filter(AdminBot.admin_id == admin_id).first()
    if bot and bot.min_topup_tomans:
        return Decimal(bot.min_topup_tomans)
    row = (
        db.query(PlatformSetting)
        .filter(PlatformSetting.key == "min_topup_tomans")
        .first()
    )
    if row and row.value:
        try:
            return Decimal(str(row.value))
        except Exception:
            pass
    return _DEFAULT_MIN_TOPUP
