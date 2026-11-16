import secrets

from app.models.admin_free_config import AdminFreeConfig
from app.models.admin_referral import AdminReferralConfig
from app.models.admin_users import AdminUser
from app.models.admins import Admin
from app.models.free_config_enrollment import FreeConfigEnrollment
from app.models.free_config_global import FreeConfigGlobal
from app.services.free_config.membership_verifier import VerificationResult
from app.services.free_config.policy import MIB
from app.tasks.free_config_tasks import recheck_memberships_impl


def _admin(db):
    a = Admin(
        username="r" + secrets.token_hex(3),
        password_hash="x",
        status="active",
        default_macro_region="eu",
    )
    db.add(a)
    db.commit()
    db.add(
        FreeConfigGlobal(
            is_enabled=True,
            default_daily_limit_mb=200,
            max_referral_bonus_mb=1000,
            verification_bot_token_enc=b"t",
        )
    )
    db.add(
        AdminFreeConfig(
            admin_id=a.id, is_enabled=True, kind="per_user", daily_limit_mb=200
        )
    )
    db.add(
        AdminReferralConfig(
            admin_id=a.id,
            is_enabled=True,
            reward_type="traffic",
            traffic_per_referral_mb=10,
            traffic_max_bonus_mb=500,
        )
    )
    db.commit()
    return a


def _enroll(
    db,
    admin_id,
    referred_by=None,
    status="active",
    membership_ok=True,
    reason=None,
    limit=200 * MIB,
):
    u = AdminUser(
        admin_id=admin_id,
        username="u" + secrets.token_hex(3),
        status=status,
        telegram_id=int(secrets.token_hex(4), 16),
        language="fa",
        subscription_token=secrets.token_hex(16),
        traffic_limit_bytes=limit,
        referred_by_user_id=referred_by,
    )
    db.add(u)
    db.commit()
    enr = FreeConfigEnrollment(
        user_id=u.id,
        admin_id=admin_id,
        membership_ok=membership_ok,
        suspended_reason=reason,
    )
    db.add(enr)
    db.commit()
    return u


async def _verify_missing(db, policy, telegram_id):
    return VerificationResult(ok=False, missing=list(policy.required_channels))


async def _verify_ok(db, policy, telegram_id):
    return VerificationResult(ok=True)


def test_friend_leaving_shrinks_referrer_bonus(db_session):
    a = _admin(db_session)
    ref = _enroll(
        db_session, a.id, limit=(200 + 10) * MIB
    )  # currently boosted by 1 friend
    _enroll(db_session, a.id, referred_by=ref.id)  # the friend, active in-channel
    # Friend fails verification -> suspended -> drops out; referrer recomputed to base.
    recheck_memberships_impl(db_session, verify_fn=_verify_missing)
    db_session.refresh(ref)
    assert ref.traffic_limit_bytes == 200 * MIB


def test_referrer_restored_regains_own_bonus(db_session):
    a = _admin(db_session)
    # Referrer was membership-suspended; their friend is active and should count.
    ref = _enroll(
        db_session,
        a.id,
        status="suspended",
        membership_ok=False,
        reason="membership",
        limit=200 * MIB,
    )
    _enroll(db_session, a.id, referred_by=ref.id)
    recheck_memberships_impl(db_session, verify_fn=_verify_ok)
    db_session.refresh(ref)
    assert ref.status == "active"
    assert ref.traffic_limit_bytes == (200 + 10) * MIB
