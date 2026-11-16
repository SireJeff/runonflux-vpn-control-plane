"""Default starter plan catalog, structured after the PVC pricing card.

Seeded ONLY at region_count=1 plus one all_regions variant per period
(spec §8.2 — no 2-region variants, no multiplier). Applied idempotently on
reseller activation when the reseller has zero packages.

WARNING: the Toman prices here are UNVERIFIED PLACEHOLDERS following the card's
shape, not confirmed real figures. `PRICES_ARE_PLACEHOLDERS` is True and
`seed_default_packages` logs a warning on insert. Resellers MUST review/edit
prices before selling.
"""
import logging
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.admin_packages import AdminPackage

logger = logging.getLogger(__name__)

# The seeded prices are placeholders, not confirmed PVC-card values. See module docstring.
PRICES_ARE_PLACEHOLDERS = True

# (period_days, tier_name, traffic_gb, price_tomans_single_region)
# NOTE: price_tomans values are PLACEHOLDERS (unverified) — see PRICES_ARE_PLACEHOLDERS.
_PVC_CELLS = [
    (30, "Light", 50, 150000),
    (30, "Plus", 100, 250000),
    (30, "Pro", 200, 400000),
    (30, "Unlimited", 500, 600000),
    (90, "Light", 150, 400000),
    (90, "Plus", 300, 700000),
    (90, "Pro", 600, 1100000),
    (90, "Unlimited", 1500, 1600000),
    (180, "Light", 300, 750000),
    (180, "Plus", 600, 1300000),
    (180, "Pro", 1200, 2000000),
    (180, "Unlimited", 3000, 3000000),
    (365, "Light", 600, 1400000),
    (365, "Plus", 1200, 2400000),
    (365, "Pro", 2400, 3800000),
    (365, "Unlimited", 6000, 5500000),
]

# All-regions variant per period (price = a reseller-editable premium; PLACEHOLDER).
_ALL_REGION_PERIODS = [
    (30, "All Regions Monthly", 200, 700000),
    (90, "All Regions Quarterly", 600, 1900000),
    (180, "All Regions Semiannual", 1200, 3500000),
    (365, "All Regions Annual", 2400, 6500000),
]


def _build_templates() -> list[dict]:
    out = []
    order = 0
    for days, tier, gb, price in _PVC_CELLS:
        label = {30: "1mo", 90: "3mo", 180: "6mo", 365: "12mo"}[days]
        out.append(
            {
                "name": f"{tier} · {label}",
                "traffic_limit_gb": Decimal(gb),
                "duration_days": days,
                "price_tomans": Decimal(price),
                "region_count": 1,
                "all_regions": False,
                "display_order": order,
            }
        )
        order += 1
    for days, name, gb, price in _ALL_REGION_PERIODS:
        out.append(
            {
                "name": name,
                "traffic_limit_gb": Decimal(gb),
                "duration_days": days,
                "price_tomans": Decimal(price),
                "region_count": 1,
                "all_regions": True,
                "display_order": order,
            }
        )
        order += 1
    return out


DEFAULT_PACKAGE_TEMPLATES = _build_templates()


def seed_default_packages(db: Session, admin_id: int) -> int:
    """Insert the default catalog if this admin has no packages yet. Idempotent.
    Does not commit — the caller owns the transaction. Returns rows inserted."""
    existing = db.query(AdminPackage).filter(AdminPackage.admin_id == admin_id).count()
    if existing:
        return 0
    for t in DEFAULT_PACKAGE_TEMPLATES:
        db.add(AdminPackage(admin_id=admin_id, **t))
    logger.warning(
        "Seeded %d default packages for admin %s with PLACEHOLDER prices; "
        "reseller must review/edit prices before selling.",
        len(DEFAULT_PACKAGE_TEMPLATES),
        admin_id,
    )
    return len(DEFAULT_PACKAGE_TEMPLATES)
