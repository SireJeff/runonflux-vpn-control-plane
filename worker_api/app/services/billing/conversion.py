"""Toman<->USD conversion + platform-setting reads for crypto payments.

Single source of the crypto conversion rate. The rate key is
`toman_per_usd_rate` (Tomans per 1 USD), matching WireOrderService's original
convention. Kept distinct from the legacy `toman_to_usd_rate` settings row.
"""

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.models.platform_settings import PlatformSetting

DEFAULT_TOMAN_PER_USD = Decimal("60000")
DEFAULT_MIN_TOPUP_USD = Decimal("10")


def get_platform_setting(db: Session, key: str) -> str | None:
    row = db.query(PlatformSetting).filter(PlatformSetting.key == key).first()
    return row.value if row and row.value else None


def get_toman_per_usd_rate(db: Session) -> Decimal:
    value = get_platform_setting(db, "toman_per_usd_rate")
    try:
        return Decimal(value) if value else DEFAULT_TOMAN_PER_USD
    except (ArithmeticError, ValueError):
        return DEFAULT_TOMAN_PER_USD


def get_min_topup_usd(db: Session) -> Decimal:
    value = get_platform_setting(db, "min_topup_usd")
    try:
        return Decimal(value) if value else DEFAULT_MIN_TOPUP_USD
    except (ArithmeticError, ValueError):
        return DEFAULT_MIN_TOPUP_USD


def usd_to_tomans(amount_usd: Decimal, rate: Decimal) -> Decimal:
    """USD -> whole Tomans (display/record value for crypto top-ups)."""
    return (amount_usd * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def tomans_to_usd(amount_tomans: Decimal, rate: Decimal) -> Decimal:
    """Tomans -> USD, 2 dp."""
    return (amount_tomans / rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
