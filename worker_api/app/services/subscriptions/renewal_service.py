"""Centralized subscription expiry math.

Single source of truth for how a duration extends a user's expiry. Used by
order approval (paid orders) and manual renewal. Policy: ADDITIVE — a renewal
while still active extends from the current expiry and never burns remaining days.
"""
from datetime import datetime, timedelta


def compute_new_expiry(
    current_expires_at: datetime | None, duration_days: int, now: datetime
) -> datetime:
    """Return the new expiry after applying ``duration_days``.

    Additive when the user is still active (``current_expires_at > now``),
    otherwise counted from ``now``.
    """
    if current_expires_at is not None and current_expires_at > now:
        start = current_expires_at
    else:
        start = now
    return start + timedelta(days=duration_days)
