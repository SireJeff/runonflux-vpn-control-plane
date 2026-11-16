import secrets

from app.models.admin_free_config import AdminFreeConfig
from app.models.admin_referral import AdminReferralConfig
from app.models.admin_users import AdminUser
from app.models.admins import Admin
from app.models.free_config_enrollment import FreeConfigEnrollment
from app.models.free_config_global import FreeConfigGlobal
from app.services.free_config.policy import MIB
from app.tasks.free_config_tasks import reset_daily_quotas_impl


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


def _enroll(db, admin_id, referred_by=None):
    u = AdminUser(
        admin_id=admin_id,
        username="u" + secrets.token_hex(3),
        status="active",
        telegram_id=int(secrets.token_hex(4), 16),
        language="fa",
        subscription_token=secrets.token_hex(16),
        traffic_used_bytes=0,
        traffic_limit_bytes=200 * MIB,
        referred_by_user_id=referred_by,
    )
    db.add(u)
    db.commit()
    db.add(FreeConfigEnrollment(user_id=u.id, admin_id=admin_id, membership_ok=True))
    db.commit()
    return u


def test_reset_applies_base_plus_referral_bonus(db_session):
    a = _admin(db_session)
    ref = _enroll(db_session, a.id)
    _enroll(db_session, a.id, referred_by=ref.id)
    _enroll(db_session, a.id, referred_by=ref.id)
    _enroll(db_session, a.id, referred_by=ref.id)  # 3 friends × 10 = +30 MB
    reset_daily_quotas_impl(db_session)
    db_session.refresh(ref)
    assert ref.traffic_limit_bytes == (200 + 30) * MIB


def test_reset_no_bonus_leaves_base(db_session):
    a = _admin(db_session)
    solo = _enroll(db_session, a.id)
    reset_daily_quotas_impl(db_session)
    db_session.refresh(solo)
    assert solo.traffic_limit_bytes == 200 * MIB
