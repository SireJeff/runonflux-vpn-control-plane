"""
Subscription Management Celery Tasks

Background tasks for:
- Auto-renewal processing
- Renewal warnings
- Subscription expiration
- Trial expiration
"""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from celery import shared_task

from app.core.database import SessionLocal
from app.models import (
    AdminAlert,
    Credential,
    RenewalWarning,
    Subscription,
    User,
    WalletTransaction,
)

logger = logging.getLogger(__name__)


def _renewal_delta(subscription: Subscription) -> timedelta:
    plan = subscription.plan
    months = (
        int(plan.duration_months) if plan and plan.duration_months is not None else 1
    )
    return timedelta(days=30 * max(months, 1))


def _plan_price(subscription: Subscription) -> Decimal:
    plan = subscription.plan
    if not plan or plan.price_usd is None:
        return Decimal("0.00")
    return Decimal(plan.price_usd)


def _deactivate_subscription_credentials(db, subscription_id: int) -> int:
    credentials = db.query(Credential).filter_by(subscription_id=subscription_id).all()
    updated = 0
    for credential in credentials:
        raw_data = credential.credential_data or {}
        data = dict(raw_data) if isinstance(raw_data, dict) else {}
        if not isinstance(data, dict):
            data = {}
        if data.get("is_active", True):
            data["is_active"] = False
            credential.credential_data = data
            updated += 1
    return updated


# ============================================================================
# AUTO-RENEWAL TASKS
# ============================================================================


@shared_task(name="subscriptions.process_auto_renewals")
def process_auto_renewals():
    """Process auto-renewals for subscriptions expiring in next 24 hours."""
    logger.info("Starting auto-renewal processing")
    db = SessionLocal()

    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        tomorrow = now + timedelta(days=1)

        expiring_subscriptions = (
            db.query(Subscription)
            .filter(
                Subscription.is_active == True,
                Subscription.auto_renew == True,
                Subscription.expires_at.between(now, tomorrow),
            )
            .all()
        )

        renewed_count = 0
        failed_count = 0

        for subscription in expiring_subscriptions:
            try:
                user = db.query(User).filter_by(id=subscription.user_id).first()
                if not user:
                    failed_count += 1
                    continue

                price = _plan_price(subscription)
                if user.wallet_balance < price:
                    failed_count += 1
                    from app.services.notifications.client import send_notification_sync

                    send_notification_sync(
                        user.id,
                        (
                            "*Low Balance Warning*\n\n"
                            "Your wallet balance is insufficient for auto-renewal.\n\n"
                            f"Current: ${user.wallet_balance:.2f}\n"
                            f"Required: ${price:.2f}\n\n"
                            "Please top up to avoid service interruption."
                        ),
                    )
                    continue

                user.wallet_balance -= price

                extension = _renewal_delta(subscription)
                base_time = max(subscription.expires_at, now)
                subscription.expires_at = base_time + extension
                subscription.status = "active"
                subscription.is_active = True

                db.add(
                    WalletTransaction(
                        user_id=user.id,
                        amount_usd=-price,
                        transaction_type="purchase",
                        subscription_id=subscription.id,
                        status="completed",
                        description=f"Auto-renewal: {subscription.plan.name if subscription.plan else 'plan'}",
                        reference_id=f"auto_renew_{subscription.id}_{int(now.timestamp())}",
                    )
                )

                db.commit()
                renewed_count += 1

                from app.services.notifications.client import send_notification_sync

                send_notification_sync(
                    user.id,
                    (
                        "*Subscription Renewed*\n\n"
                        f"Your subscription has been auto-renewed.\n\n"
                        f"New expiry: {subscription.expires_at.strftime('%Y-%m-%d %H:%M UTC')}\n"
                        f"Amount charged: ${price:.2f}"
                    ),
                )

            except Exception as exc:
                logger.error("Error renewing subscription %s: %s", subscription.id, exc)
                db.rollback()
                failed_count += 1

        return {
            "renewed": renewed_count,
            "failed": failed_count,
            "total": len(expiring_subscriptions),
        }

    except Exception as exc:
        logger.error("Auto-renewal processing failed: %s", exc)
        return {"error": str(exc)}
    finally:
        db.close()


@shared_task(name="subscriptions.send_renewal_warnings")
def send_renewal_warnings():
    """Send renewal warnings for subscriptions expiring soon.

    Sends warnings at 7, 3, and 1 days before expiry. Uses the RenewalWarning
    model to ensure each warning type is sent at most once per subscription.
    Respects the user's ``notification_enabled`` preference.
    """
    logger.info("Starting renewal warning notifications")
    db = SessionLocal()

    try:
        from app.services.notifications.client import send_notification_sync

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        warnings_sent = {"7_days": 0, "3_days": 0, "1_day": 0}

        # (days_before, warning_label, message_builder)
        warning_schedule = [
            (
                7,
                "7_days",
                lambda sub: (
                    "*Subscription Expiring Soon*\n\n"
                    "Your subscription expires in *7 days*.\n"
                    f"Expiry: {sub.expires_at.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
                    f"{'Auto-renewal is enabled.' if sub.auto_renew else 'Please renew manually to keep your service active.'}"
                ),
            ),
            (
                3,
                "3_days",
                lambda sub: (
                    "*Renewal Reminder*\n\n"
                    "Your subscription expires in *3 days*.\n"
                    f"Expiry: {sub.expires_at.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
                    f"{'Auto-renewal is enabled.' if sub.auto_renew else 'Please renew manually to keep your service active.'}"
                ),
            ),
            (
                1,
                "1_day",
                lambda sub: (
                    "*Urgent: Subscription Expiring*\n\n"
                    "Your subscription expires *tomorrow*.\n"
                    f"Expiry: {sub.expires_at.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
                    f"{'Auto-renewal is enabled.' if sub.auto_renew else 'Please renew now to avoid service interruption.'}"
                ),
            ),
        ]

        for days_before, label, message_builder in warning_schedule:
            target_date = now + timedelta(days=days_before)

            # Use a 12-hour window to catch subscriptions whose expiry falls
            # within a range around the target date, reducing the risk of
            # missing a subscription due to timing skew.
            window_start = target_date - timedelta(hours=12)
            window_end = target_date + timedelta(hours=12)

            expiring = (
                db.query(Subscription)
                .filter(
                    Subscription.is_active == True,
                    Subscription.expires_at.between(window_start, window_end),
                )
                .all()
            )

            for sub in expiring:
                user = db.query(User).filter_by(id=sub.user_id).first()
                if not user:
                    continue

                # Respect the user's notification preference.
                if not getattr(user, "notification_enabled", True):
                    continue

                # Check whether we already sent this exact warning for this
                # subscription. The unique constraint on
                # (subscription_id, days_before_expiration) guarantees at most
                # one row per warning type, so ``first()`` is sufficient.
                existing = (
                    db.query(RenewalWarning)
                    .filter(
                        RenewalWarning.subscription_id == sub.id,
                        RenewalWarning.days_before_expiration == days_before,
                    )
                    .first()
                )

                if existing:
                    continue

                # Record the warning before sending the notification so that a
                # failure in the notification service does not cause duplicates.
                warning_record = RenewalWarning(
                    subscription_id=sub.id,
                    user_id=user.id,
                    days_before_expiration=days_before,
                    sent_at=now,
                )
                db.add(warning_record)

                try:
                    send_notification_sync(user.id, message_builder(sub))
                    db.commit()
                    warnings_sent[label] += 1
                    logger.info(
                        "Expiration warning (%d days) sent to user %s for subscription %s",
                        days_before,
                        user.id,
                        sub.id,
                    )
                except Exception as exc:
                    db.rollback()
                    logger.error(
                        "Failed to send %s warning to user %s for subscription %s: %s",
                        label,
                        user.id,
                        sub.id,
                        exc,
                    )

        return {
            "warnings_sent": sum(warnings_sent.values()),
            "breakdown": warnings_sent,
        }

    except Exception as exc:
        logger.error("Renewal warning failed: %s", exc)
        return {"error": str(exc)}
    finally:
        db.close()


# ============================================================================
# SUBSCRIPTION EXPIRATION TASKS
# ============================================================================


@shared_task(name="subscriptions.expire_subscriptions")
def expire_subscriptions():
    """Mark expired subscriptions as inactive and deactivate credentials."""
    logger.info("Checking for expired subscriptions")
    db = SessionLocal()

    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        expired_subscriptions = (
            db.query(Subscription)
            .filter(Subscription.is_active == True, Subscription.expires_at < now)
            .all()
        )

        expired_count = 0
        for subscription in expired_subscriptions:
            try:
                subscription.is_active = False
                subscription.status = "expired"

                deactivated = _deactivate_subscription_credentials(db, subscription.id)
                db.commit()
                expired_count += 1

                from app.services.notifications.client import send_notification_sync

                send_notification_sync(
                    subscription.user_id,
                    (
                        "*Subscription Expired*\n\n"
                        "Your subscription has expired and your credentials have been deactivated.\n\n"
                        "To restore access, please renew your subscription."
                    ),
                )

                logger.info(
                    "Expired subscription %s, deactivated %s credentials",
                    subscription.id,
                    deactivated,
                )

            except Exception as exc:
                logger.error("Error expiring subscription %s: %s", subscription.id, exc)
                db.rollback()

        return {"expired": expired_count, "total": len(expired_subscriptions)}

    except Exception as exc:
        logger.error("Subscription expiration check failed: %s", exc)
        return {"error": str(exc)}
    finally:
        db.close()


@shared_task(name="subscriptions.expire_trials")
def expire_trials():
    """Expire trial subscriptions and deactivate credentials."""
    logger.info("Checking for expired trials")
    db = SessionLocal()

    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        expired_trials = (
            db.query(Subscription)
            .filter(
                Subscription.is_active == True,
                Subscription.is_trial == True,
                Subscription.expires_at < now,
            )
            .all()
        )

        expired_count = 0
        for trial in expired_trials:
            try:
                trial.is_active = False
                trial.status = "expired"
                _deactivate_subscription_credentials(db, trial.id)
                db.commit()
                expired_count += 1

                from app.services.notifications.client import send_notification_sync

                send_notification_sync(
                    trial.user_id,
                    (
                        "*Trial Expired*\n\n"
                        "Your free trial has ended.\n\n"
                        "Upgrade to a paid plan to continue using our VPN service."
                    ),
                )
            except Exception as exc:
                logger.error("Error expiring trial %s: %s", trial.id, exc)
                db.rollback()

        return {"expired_trials": expired_count, "total": len(expired_trials)}

    except Exception as exc:
        logger.error("Trial expiration check failed: %s", exc)
        return {"error": str(exc)}
    finally:
        db.close()


# ============================================================================
# SUBSCRIPTION ANALYTICS
# ============================================================================


@shared_task(name="subscriptions.calculate_churn_rate")
def calculate_churn_rate():
    """Calculate a simple 30-day churn rate."""
    logger.info("Calculating churn rate")
    db = SessionLocal()

    try:
        thirty_days_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            days=30
        )

        active_start = (
            db.query(Subscription)
            .filter(
                Subscription.created_at < thirty_days_ago,
                Subscription.expires_at >= thirty_days_ago,
            )
            .count()
        )

        cancelled = (
            db.query(Subscription)
            .filter(
                Subscription.is_active == False,
                Subscription.expires_at >= thirty_days_ago,
            )
            .count()
        )

        churn_rate = (cancelled / active_start * 100) if active_start > 0 else 0

        if churn_rate > 10:
            db.add(
                AdminAlert(
                    alert_type="churn_alert",
                    priority="high" if churn_rate > 15 else "medium",
                    title=f"High Churn Rate: {churn_rate:.2f}%",
                    message=(
                        f"Churn rate is {churn_rate:.2f}% "
                        f"({cancelled} churned subscriptions in last 30 days)"
                    ),
                    acknowledged=False,
                )
            )
            db.commit()

        return {
            "churn_rate": churn_rate,
            "cancelled": cancelled,
            "active_start": active_start,
        }

    except Exception as exc:
        logger.error("Churn rate calculation failed: %s", exc)
        return {"error": str(exc)}
    finally:
        db.close()


@shared_task(name="subscriptions.cleanup_old_subscriptions")
def cleanup_old_subscriptions():
    """Cleanup inactive subscriptions expired more than one year ago."""
    logger.info("Cleaning up old subscriptions")
    db = SessionLocal()

    try:
        one_year_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            days=365
        )
        old_subscriptions = (
            db.query(Subscription)
            .filter(
                Subscription.is_active == False,
                Subscription.expires_at < one_year_ago,
            )
            .all()
        )

        deleted_count = 0
        for subscription in old_subscriptions:
            try:
                db.query(Credential).filter_by(subscription_id=subscription.id).delete()
                db.delete(subscription)
                db.commit()
                deleted_count += 1
            except Exception as exc:
                logger.error("Error deleting subscription %s: %s", subscription.id, exc)
                db.rollback()

        return {"deleted": deleted_count, "total": len(old_subscriptions)}

    except Exception as exc:
        logger.error("Subscription cleanup failed: %s", exc)
        return {"error": str(exc)}
    finally:
        db.close()
