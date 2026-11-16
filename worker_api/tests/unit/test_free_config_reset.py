import secrets
from datetime import datetime, timedelta
from app.tasks.free_config_tasks import reset_daily_quotas_impl
from app.services.free_config.policy import MIB
from app.models.admins import Admin
from app.models.admin_free_config import AdminFreeConfig
from app.models.free_config_global import FreeConfigGlobal
from app.models.admin_users import AdminUser
from app.models.free_config_enrollment import FreeConfigEnrollment


def _enrolled(db, used, limit, status="active", reason=None, reseller_limit=200):
    a = Admin(username="r"+secrets.token_hex(3), password_hash="x", status="active", default_macro_region="eu")
    db.add(a); db.commit()
    db.add(FreeConfigGlobal(is_enabled=True, default_daily_limit_mb=200, verification_bot_token_enc=b"t"))
    db.add(AdminFreeConfig(admin_id=a.id, is_enabled=True, kind="per_user", daily_limit_mb=reseller_limit))
    u = AdminUser(admin_id=a.id, username="u"+secrets.token_hex(3), status=status,
                  telegram_id=int(secrets.token_hex(3), 16), language="fa",
                  subscription_token=secrets.token_hex(16),
                  traffic_used_bytes=used, traffic_limit_bytes=limit)
    db.add(u); db.commit()
    db.add(FreeConfigEnrollment(user_id=u.id, admin_id=a.id, membership_ok=(status=="active"), suspended_reason=reason))
    db.commit()
    return a, u


def test_reset_zeroes_usage_and_reapplies_limit(db_session):
    a, u = _enrolled(db_session, used=150*MIB, limit=100*MIB, reseller_limit=200)
    reset_daily_quotas_impl(db_session)
    db_session.refresh(u)
    assert u.traffic_used_bytes == 0
    assert u.traffic_limit_bytes == 200 * MIB   # re-applied from resolved policy


def test_reset_leaves_membership_suspended_user_suspended(db_session):
    a, u = _enrolled(db_session, used=10*MIB, limit=200*MIB, status="suspended", reason="membership")
    reset_daily_quotas_impl(db_session)
    db_session.refresh(u)
    assert u.status == "suspended"
    assert u.traffic_used_bytes == 0            # odometer still cleared


def test_reset_is_idempotent(db_session):
    a, u = _enrolled(db_session, used=200*MIB, limit=200*MIB)
    reset_daily_quotas_impl(db_session)
    reset_daily_quotas_impl(db_session)
    db_session.refresh(u)
    assert u.traffic_used_bytes == 0


def test_reset_skips_user_with_active_paid_subscription(db_session):
    # Defense-in-depth: even if a free-config enrollment lingers, the reset
    # must never touch a user who has an active (future-dated) paid plan.
    GIB = 1024 ** 3
    a, u = _enrolled(db_session, used=5 * GIB, limit=30 * GIB, reseller_limit=200)
    u.expires_at = datetime.utcnow() + timedelta(days=30)
    db_session.commit()

    reset_daily_quotas_impl(db_session)
    db_session.refresh(u)

    assert u.traffic_limit_bytes == 30 * GIB   # NOT clobbered to 200 MB
    assert u.traffic_used_bytes == 5 * GIB      # NOT zeroed
