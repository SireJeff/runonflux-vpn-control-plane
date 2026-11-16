import secrets

from app.models.admin_free_config import AdminFreeConfig
from app.models.admin_referral import AdminReferralConfig
from app.models.admin_users import AdminUser
from app.models.admins import Admin
from app.models.free_config_enrollment import FreeConfigEnrollment
from app.models.free_config_global import FreeConfigGlobal
from app.services.free_config.enrollment_service import FreeConfigEnrollmentService
from app.services.free_config.policy import MIB, resolve_free_config_policy


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


def _user(db, admin_id, username, referred_by=None, enrolled=False):
    u = AdminUser(
        admin_id=admin_id,
        username=username,
        status="active" if enrolled else "lead",
        telegram_id=int(secrets.token_hex(4), 16),
        language="fa",
        subscription_token=secrets.token_hex(16),
        traffic_limit_bytes=200 * MIB,
        referred_by_user_id=referred_by,
    )
    db.add(u)
    db.commit()
    if enrolled:
        db.add(
            FreeConfigEnrollment(user_id=u.id, admin_id=admin_id, membership_ok=True)
        )
        db.commit()
    return u


def test_provision_mints_referral_code(db_session):
    a = _admin(db_session)
    u = _user(db_session, a.id, "carol")
    policy = resolve_free_config_policy(db_session, a.id)
    FreeConfigEnrollmentService(db_session).provision(u, policy)
    db_session.refresh(u)
    assert u.referral_code and u.referral_code.startswith("CAROL-")


def test_provision_bumps_referrer_limit(db_session):
    a = _admin(db_session)
    ref = _user(
        db_session, a.id, "referrer", enrolled=True
    )  # already a free user, base 200
    friend = _user(db_session, a.id, "friend", referred_by=ref.id)
    policy = resolve_free_config_policy(db_session, a.id)
    FreeConfigEnrollmentService(db_session).provision(friend, policy)
    db_session.refresh(ref)
    assert ref.traffic_limit_bytes == (200 + 10) * MIB
