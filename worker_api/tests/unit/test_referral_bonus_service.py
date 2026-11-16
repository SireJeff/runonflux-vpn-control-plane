import secrets
from datetime import datetime, timedelta

from app.models.admin_free_config import AdminFreeConfig
from app.models.admin_referral import AdminReferralConfig
from app.models.admin_users import AdminUser
from app.models.admins import Admin
from app.models.free_config_enrollment import FreeConfigEnrollment
from app.models.free_config_global import FreeConfigGlobal
from app.services.free_config.policy import MIB
from app.services.referral.bonus_service import ReferralBonusService


def _admin(db):
    a = Admin(
        username="r" + secrets.token_hex(3),
        password_hash="x",
        status="active",
        default_macro_region="eu",
    )
    db.add(a)
    db.commit()
    return a


def test_referral_config_has_traffic_columns_with_defaults(db_session):
    a = _admin(db_session)
    cfg = AdminReferralConfig(admin_id=a.id)
    db_session.add(cfg)
    db_session.commit()
    db_session.refresh(cfg)
    assert cfg.reward_type == "cashback"
    assert cfg.traffic_per_referral_mb == 0
    assert cfg.traffic_max_bonus_mb == 0


def test_free_config_global_has_max_referral_bonus_mb(db_session):
    g = FreeConfigGlobal(is_enabled=True, default_daily_limit_mb=200)
    db_session.add(g)
    db_session.commit()
    db_session.refresh(g)
    assert g.max_referral_bonus_mb == 1000


def _setup(
    db,
    reward_type="traffic",
    per=10,
    max_bonus=500,
    global_ceiling=1000,
    reseller_daily=200,
):
    a = _admin(db)
    db.add(
        FreeConfigGlobal(
            is_enabled=True,
            default_daily_limit_mb=200,
            max_referral_bonus_mb=global_ceiling,
            verification_bot_token_enc=b"t",
        )
    )
    db.add(
        AdminFreeConfig(
            admin_id=a.id,
            is_enabled=True,
            kind="per_user",
            daily_limit_mb=reseller_daily,
        )
    )
    db.add(
        AdminReferralConfig(
            admin_id=a.id,
            is_enabled=True,
            reward_type=reward_type,
            traffic_per_referral_mb=per,
            traffic_max_bonus_mb=max_bonus,
        )
    )
    db.commit()
    return a


def _mk_user(
    db,
    admin_id,
    status="active",
    referred_by=None,
    enrolled=False,
    membership_ok=True,
    expires_in_days=None,
):
    u = AdminUser(
        admin_id=admin_id,
        username="u" + secrets.token_hex(3),
        status=status,
        telegram_id=int(secrets.token_hex(4), 16),
        language="fa",
        subscription_token=secrets.token_hex(16),
        referred_by_user_id=referred_by,
    )
    if expires_in_days is not None:
        u.expires_at = datetime.utcnow() + timedelta(days=expires_in_days)
    db.add(u)
    db.commit()
    if enrolled:
        db.add(
            FreeConfigEnrollment(
                user_id=u.id,
                admin_id=admin_id,
                membership_ok=membership_ok,
                suspended_reason=None if membership_ok else "membership",
            )
        )
        db.commit()
    return u


def test_count_qualifying_counts_free_and_paid_excludes_suspended(db_session):
    a = _setup(db_session)
    ref = _mk_user(db_session, a.id, enrolled=True)
    _mk_user(db_session, a.id, referred_by=ref.id, enrolled=True)  # free ok
    _mk_user(db_session, a.id, referred_by=ref.id, expires_in_days=30)  # paid ok
    _mk_user(
        db_session,
        a.id,
        referred_by=ref.id,
        status="suspended",
        enrolled=True,
        membership_ok=False,
    )  # left channels
    _mk_user(db_session, a.id, referred_by=ref.id)  # lead, not enrolled/paid
    svc = ReferralBonusService(db_session)
    assert svc.count_qualifying(ref.id, a.id) == 2


def test_compute_bonus_caps_at_reseller_max(db_session):
    a = _setup(db_session, per=10, max_bonus=50, global_ceiling=1000)
    ref = _mk_user(db_session, a.id, enrolled=True)
    for _ in range(20):
        _mk_user(
            db_session, a.id, referred_by=ref.id, enrolled=True
        )  # 20 × 10 = 200 > 50
    svc = ReferralBonusService(db_session)
    assert svc.compute_bonus_mb(ref) == 50


def test_compute_bonus_clamped_by_global_ceiling(db_session):
    a = _setup(db_session, per=10, max_bonus=500, global_ceiling=30)
    ref = _mk_user(db_session, a.id, enrolled=True)
    for _ in range(20):
        _mk_user(db_session, a.id, referred_by=ref.id, enrolled=True)
    svc = ReferralBonusService(db_session)
    assert svc.compute_bonus_mb(ref) == 30


def test_compute_bonus_zero_when_reward_type_cashback(db_session):
    a = _setup(db_session, reward_type="cashback")
    ref = _mk_user(db_session, a.id, enrolled=True)
    _mk_user(db_session, a.id, referred_by=ref.id, enrolled=True)
    svc = ReferralBonusService(db_session)
    assert svc.compute_bonus_mb(ref) == 0


def test_apply_effective_limit_sets_base_plus_bonus(db_session):
    a = _setup(db_session, per=10)
    ref = _mk_user(db_session, a.id, enrolled=True)
    _mk_user(db_session, a.id, referred_by=ref.id, enrolled=True)
    _mk_user(db_session, a.id, referred_by=ref.id, enrolled=True)
    svc = ReferralBonusService(db_session)
    svc.apply_effective_limit(ref)
    db_session.refresh(ref)
    assert ref.traffic_limit_bytes == (200 + 20) * MIB


def test_apply_effective_limit_skips_paid_referrer(db_session):
    a = _setup(db_session, per=10)
    ref = _mk_user(db_session, a.id, enrolled=True, expires_in_days=30)
    ref.traffic_limit_bytes = 30 * 1024**3
    db_session.commit()
    _mk_user(db_session, a.id, referred_by=ref.id, enrolled=True)
    svc = ReferralBonusService(db_session)
    svc.apply_effective_limit(ref)
    db_session.refresh(ref)
    assert ref.traffic_limit_bytes == 30 * 1024**3  # untouched
