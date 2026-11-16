"""
Free-Config Celery Tasks

Background tasks for the per-user free-config feature:
- Daily quota reset (zero odometer + re-apply resolved daily limit) at 00:00 UTC
- Periodic membership re-check (revoke/restore free access) every 6h
"""

import asyncio
import logging
from datetime import datetime, timezone

from celery import shared_task
from sqlalchemy import or_

from app.core.database import SessionLocal
from app.models.admin_users import AdminUser
from app.models.free_config_enrollment import FreeConfigEnrollment
from app.models.free_config_global import FreeConfigGlobal  # noqa: F401
from app.services.free_config.membership_verifier import MembershipVerifier
from app.services.free_config.policy import MIB, resolve_free_config_policy
from app.services.notifications.router import NotificationRouter
from app.services.referral.bonus_service import ReferralBonusService

logger = logging.getLogger(__name__)


def _has_active_paid_subscription(user, now_naive: datetime) -> bool:
    """True if the user holds an active (future-dated) paid subscription.

    Free-config users never carry an ``expires_at`` (see enrollment provision),
    so a future expiry reliably marks a user who has graduated to a paid plan.
    Guards the free-config sweeps against clobbering such a user even if a stale
    enrollment row lingers.
    """
    exp = user.expires_at
    if exp is None:
        return False
    if exp.tzinfo is not None:
        exp = exp.replace(tzinfo=None)
    return exp > now_naive


def reset_daily_quotas_impl(db) -> dict:
    """Zero traffic_used_bytes and re-apply the resolved daily limit for all free users."""
    processed = limits_changed = errors = 0
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    enrollments = db.query(FreeConfigEnrollment).yield_per(500)
    for enr in enrollments:
        try:
            user = db.query(AdminUser).filter(AdminUser.id == enr.user_id).first()
            if user is None:
                continue
            # Never touch a user who has upgraded to a paid plan.
            if _has_active_paid_subscription(user, now_naive):
                continue
            policy = resolve_free_config_policy(db, enr.admin_id)
            bonus_bytes = ReferralBonusService(db).compute_bonus_mb(user) * MIB
            target = policy.daily_limit_bytes + bonus_bytes
            if user.traffic_limit_bytes != target:
                user.traffic_limit_bytes = target
                limits_changed += 1
            user.traffic_used_bytes = 0  # odometer only; never touch traffic_counters
            processed += 1
            if processed % 200 == 0:
                db.commit()
        except Exception:  # noqa: BLE001 - never let one row abort the sweep
            errors += 1
            logger.exception("reset_daily_quotas failed for enrollment %s", enr.id)
    db.commit()
    summary = {"processed": processed, "limits_changed": limits_changed, "errors": errors}
    logger.info("reset_daily_quotas: %s", summary)
    return summary


@shared_task(name="free_config.reset_daily_quotas")
def reset_daily_quotas():
    db = SessionLocal()
    try:
        return reset_daily_quotas_impl(db)
    finally:
        db.close()


async def _default_verify(db, policy, telegram_id):
    verifier = MembershipVerifier.from_global(db)
    if verifier is None:
        from app.services.free_config.membership_verifier import VerificationResult
        return VerificationResult(ok=False, unverifiable=list(policy.required_channels))
    return await verifier.check(telegram_id, policy.required_channels)


def recheck_memberships_impl(db, verify_fn=None) -> dict:
    verify_fn = verify_fn or _default_verify
    now = datetime.now(timezone.utc)
    now_naive = now.replace(tzinfo=None)
    processed = suspended = restored = unverifiable = errors = 0

    candidates = (
        db.query(FreeConfigEnrollment)
        .filter(
            or_(
                FreeConfigEnrollment.membership_ok.is_(True),
                FreeConfigEnrollment.suspended_reason == "membership",
            )
        )
        .yield_per(500)
    )
    router = NotificationRouter(db)
    bonus_svc = ReferralBonusService(db)
    for enr in candidates:
        try:
            user = db.query(AdminUser).filter(AdminUser.id == enr.user_id).first()
            if user is None or user.telegram_id is None:
                continue
            # Never touch a user who has upgraded to a paid plan.
            if _has_active_paid_subscription(user, now_naive):
                continue
            # Never touch a suspension we don't own.
            if user.status == "suspended" and enr.suspended_reason != "membership":
                continue
            policy = resolve_free_config_policy(db, enr.admin_id)
            result = asyncio.run(verify_fn(db, policy, user.telegram_id))
            enr.last_membership_check_at = now
            if result.unverifiable:
                unverifiable += 1
                processed += 1
                continue
            if result.ok:
                if enr.suspended_reason == "membership":
                    user.status = "active"
                    enr.suspended_reason = None
                    enr.membership_ok = True
                    restored += 1
                    _notify(router, user.id, "restored")
                    # restored referrer regains own bonus
                    bonus_svc.apply_effective_limit(user)
                    # and re-counts as a referee
                    _recompute_referrer(bonus_svc, db, user)
            else:  # definitively missing
                if enr.membership_ok or user.status == "active":
                    user.status = "suspended"
                    enr.membership_ok = False
                    enr.suspended_reason = "membership"
                    suspended += 1
                    _notify(router, user.id, "revoked")
                    # referee dropped out; shrink referrer
                    _recompute_referrer(bonus_svc, db, user)
            processed += 1
            if processed % 200 == 0:
                db.commit()
        except Exception:  # noqa: BLE001
            errors += 1
            logger.exception("recheck failed for enrollment %s", enr.id)
    db.commit()
    summary = {"processed": processed, "suspended": suspended, "restored": restored,
               "unverifiable": unverifiable, "errors": errors}
    logger.info("recheck_memberships: %s", summary)
    return summary


def _notify(router, user_id, kind):
    msg = ("عضویت شما در کانال‌ها تأیید نشد؛ برای فعال‌سازی مجدد کانفیگ رایگان دوباره عضو شوید."
           if kind == "revoked"
           else "کانفیگ رایگان شما دوباره فعال شد.")
    try:
        router.send_to_end_user(user_id, msg)
    except Exception:  # noqa: BLE001
        logger.warning("notify %s failed for user %s", kind, user_id)


def _recompute_referrer(bonus_svc, db, user) -> None:
    """A referee's qualification changed — refresh their referrer's derived limit."""
    if not user.referred_by_user_id:
        return
    # The caller just mutated `user`'s own status/membership_ok in-memory; the
    # session has autoflush disabled, so flush now or the qualifying-count
    # query below (a raw aggregate) would read stale pre-mutation rows.
    db.flush()
    referrer = (
        db.query(AdminUser).filter(AdminUser.id == user.referred_by_user_id).first()
    )
    if referrer is not None:
        bonus_svc.apply_effective_limit(referrer)


@shared_task(name="free_config.recheck_memberships")
def recheck_memberships():
    db = SessionLocal()
    try:
        return recheck_memberships_impl(db)
    finally:
        db.close()
