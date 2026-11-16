"""Reconcile a user's UserRegion rows to a desired macro-region set.

The first region in the desired list is the primary (free, no billing clock).
Every additional region is non-primary and gets a 30-day billing clock so the
per-region monthly charge (RegionBillingService) starts after the first month.
"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.admin_users import AdminUser
from app.models.user_regions import UserRegion


def set_user_regions(
    db: Session, user: AdminUser, macro_regions: list[str], now: datetime
) -> None:
    """Make the user hold exactly ``macro_regions`` (order = priority; [0] is primary).

    Adds missing rows, removes rows not in the set, and re-points primary. Does
    not commit — the caller owns the transaction.
    """
    desired = list(dict.fromkeys(macro_regions))  # de-dupe, preserve order
    if not desired:
        return

    existing = {
        r.macro_region: r
        for r in db.query(UserRegion).filter(UserRegion.user_id == user.id).all()
    }

    # Remove regions no longer wanted
    for macro, del_row in existing.items():
        if macro not in desired:
            db.delete(del_row)

    for idx, macro in enumerate(desired):
        is_primary = idx == 0
        row = existing.get(macro)
        if row is None:
            db.add(
                UserRegion(
                    user_id=user.id,
                    macro_region=macro,
                    is_primary=is_primary,
                    status="active",
                    region_expires_at=None if is_primary else now + timedelta(days=30),
                )
            )
        else:
            row.is_primary = is_primary
            if is_primary:
                # Primary is always active + free (invariant).
                row.status = "active"
                row.region_expires_at = None
            elif row.region_expires_at is None:
                # Newly-non-primary (e.g. demoted former primary) gets a billing clock;
                # a suspended non-primary keeps its status — do NOT reactivate it for free.
                row.region_expires_at = now + timedelta(days=30)
