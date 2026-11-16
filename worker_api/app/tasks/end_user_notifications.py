"""Celery tasks for end-user subscription lifecycle notifications.

Tasks:
- subscription_expiring: Daily at 9 AM UTC, notify users whose sub expires in ~3 days
- subscription_expired: Daily at 10 AM UTC, notify + mark expired users who expired yesterday
- cleanup_pending_orders: Daily at 11 AM UTC, mark pending orders > 72h as expired
"""

import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.core.celery_config import celery_app
from app.core.database import SessionLocal
from app.models.admin_users import AdminUser
from app.models.user_orders import UserOrder
from app.services.bots.end_user_keyboards import _L
from app.services.notifications.router import NotificationRouter
from app.services.notifications.templates_fa import (
    format_user_subscription_expired,
    format_user_subscription_expiring,
    template_for,
)

logger = logging.getLogger(__name__)


@celery_app.task(name="notifications.subscription_expiring")
def subscription_expiring():
    """Daily: notify active users whose subscription expires in 3-4 days."""
    db: Session = SessionLocal()
    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        soon_start = now + timedelta(days=3)
        soon_end = now + timedelta(days=4)
        users = (
            db.query(AdminUser)
            .filter(
                AdminUser.status == "active",
                AdminUser.expires_at >= soon_start,
                AdminUser.expires_at < soon_end,
            )
            .all()
        )
        router = NotificationRouter(db)
        notified = 0
        for user in users:
            try:
                router.send_to_end_user(
                    user.id,
                    format_user_subscription_expiring(days_left=3),
                )
                notified += 1
            except Exception as exc:
                logger.warning(
                    f"Failed to notify user {user.id} of upcoming expiry: {exc}"
                )
        logger.info(f"Notified {notified} users of upcoming subscription expiry")
        return {"notified": notified}
    finally:
        db.close()


@celery_app.task(name="notifications.subscription_expired")
def subscription_expired():
    """Daily: notify users whose subscription expired yesterday, then mark them expired."""
    db: Session = SessionLocal()
    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        yesterday_start = now - timedelta(days=1)
        users = (
            db.query(AdminUser)
            .filter(
                AdminUser.expires_at >= yesterday_start,
                AdminUser.expires_at < now,
            )
            .all()
        )
        router = NotificationRouter(db)
        notified = 0
        for user in users:
            try:
                router.send_to_end_user(
                    user.id,
                    format_user_subscription_expired(),
                )
                notified += 1
            except Exception as exc:
                logger.warning(f"Failed to notify user {user.id} of expiry: {exc}")
            user.status = "expired"
        db.commit()
        logger.info(f"Processed {notified} expired users")
        return {"notified": notified}
    finally:
        db.close()


@celery_app.task(name="notifications.cleanup_pending_orders")
def cleanup_pending_orders():
    """Daily: mark orders pending > 72h as expired."""
    db: Session = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None)
        stale = (
            db.query(UserOrder)
            .filter(
                UserOrder.status == "pending",
                UserOrder.expires_at < cutoff,
            )
            .all()
        )
        for order in stale:
            order.status = "expired"
        db.commit()
        logger.info(f"Cleaned up {len(stale)} stale pending orders")
        return {"expired": len(stale)}
    finally:
        db.close()


# Telegram allows ~30 msg/sec per bot; pace per send to stay under the limit.
_TLD_SEND_PACE_SEC = 0.04


@celery_app.task(name="notifications.tld_changed")
def notify_end_users_tld_changed(
    admin_ids: list[int],
    purpose: str,
    new_domain: str,
    old_domain: str | None = None,
) -> dict:
    """Fan out a 'your address is now {new_domain}' notice to the active users
    of the AFFECTED admins only (not globally).

    admin_ids: owning admins whose effective TLD for `purpose` just changed.
    purpose:   one of fdm/subscription/dashboard/admin_panel.
    new_domain/old_domain: the moved-to / moved-from base domain (old_domain is
               accepted for logging/future use; only new_domain is rendered).

    Routed to each user's reseller bot via NotificationRouter.send_to_end_user
    (the router resolves the reseller's bot from the user). `subscription` keeps
    the shipped non-expired expires_at filter; other purposes message all active
    users of the affected admins. Per-user try/except + False-return check +
    _TLD_SEND_PACE_SEC pacing so one failure doesn't abort the batch and only
    real successes are counted.
    """
    if not admin_ids:
        return {"notified": 0}

    db: Session = SessionLocal()
    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        query = db.query(AdminUser).filter(
            AdminUser.status == "active",
            AdminUser.admin_id.in_(admin_ids),
        )
        if purpose == "subscription":
            query = query.filter(
                AdminUser.expires_at.isnot(None),
                AdminUser.expires_at > now,
            )

        users = query.all()
        router = NotificationRouter(db)
        notified = 0
        for user in users:
            lang = getattr(user, "language", "fa") or "fa"
            tpl = template_for(lang)
            purpose_label = tpl.TLD_PURPOSE_LABELS.get(purpose, purpose)
            message = tpl.format_tld_effective_changed(purpose_label, new_domain)
            button = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            _L(lang, "connections"), callback_data="connections"
                        ),
                    ]
                ]
            )
            try:
                if router.send_to_end_user(user.id, message, reply_markup=button):
                    notified += 1
            except Exception as exc:
                logger.warning(f"TLD-notice send failed for user {user.id}: {exc}")
            time.sleep(_TLD_SEND_PACE_SEC)
        logger.info(
            f"TLD change ({purpose} -> {new_domain}): notified {notified}/{len(users)} "
            f"users of admin(s) {admin_ids}"
        )
        return {"notified": notified}
    finally:
        db.close()
