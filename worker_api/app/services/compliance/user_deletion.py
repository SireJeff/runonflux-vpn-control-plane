"""
Soft-delete lifecycle helpers for compliance retention workflows.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, cast

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import User


def schedule_user_soft_delete(
    user: User,
    *,
    requested_at: Optional[datetime] = None,
    retention_days: Optional[int] = None,
) -> datetime:
    """
    Mark a user as soft-deleted and schedule retention-expiry cleanup.

    This function is idempotent: existing scheduled cleanup is preserved.
    """
    if user.is_deleted and user.deletion_scheduled_at is not None:
        return cast(datetime, user.deletion_scheduled_at)

    requested_at = requested_at or datetime.now(timezone.utc).replace(tzinfo=None)
    retention_days = retention_days or settings.USER_DELETION_RETENTION_DAYS
    scheduled_at = requested_at + timedelta(days=retention_days)

    user_obj = cast(Any, user)
    user_obj.is_deleted = True
    user_obj.deleted_at = requested_at
    user_obj.deletion_scheduled_at = scheduled_at

    # Revoke refresh tokens immediately.
    user_obj.refresh_token_jti = None
    user_obj.refresh_token_expires_at = None

    # Disable current paid access while retention window is active.
    for subscription in user.subscriptions:
        if subscription.is_active:
            subscription.is_active = False
            subscription.auto_renew = False
            subscription.status = "cancelled"

    return scheduled_at


def purge_expired_soft_deleted_users(
    db: Session,
    *,
    now: Optional[datetime] = None,
    batch_size: int = 500,
) -> Dict[str, List[int] | int]:
    """
    Hard-delete users whose soft-delete retention window has expired.
    """
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    candidates = (
        db.query(User)
        .filter(
            User.is_deleted == True,
            User.deletion_scheduled_at.isnot(None),
            User.deletion_scheduled_at <= now,
        )
        .limit(batch_size)
        .all()
    )

    deleted_ids: List[int] = []
    for user in candidates:
        deleted_ids.append(cast(int, user.id))
        db.delete(user)

    return {"deleted": len(deleted_ids), "user_ids": deleted_ids}


def get_pending_soft_deleted_users(
    db: Session,
    *,
    now: Optional[datetime] = None,
    limit: int = 100,
) -> List[User]:
    """
    Fetch users pending scheduled cleanup in the retention window.
    """
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    return (
        db.query(User)
        .filter(
            User.is_deleted == True,
            User.deletion_scheduled_at.isnot(None),
            User.deletion_scheduled_at > now,
        )
        .order_by(User.deletion_scheduled_at.asc())
        .limit(limit)
        .all()
    )
