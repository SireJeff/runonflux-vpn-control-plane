import secrets
from datetime import datetime, timedelta
from types import SimpleNamespace
from app.tasks.free_config_tasks import recheck_memberships_impl
from app.services.free_config.membership_verifier import VerificationResult
from app.models.admins import Admin
from app.models.admin_free_config import AdminFreeConfig
from app.models.free_config_global import FreeConfigGlobal
from app.models.admin_users import AdminUser
from app.models.free_config_enrollment import FreeConfigEnrollment


def _enrolled(db, status="active", membership_ok=True, reason=None):
    a = Admin(username="r"+secrets.token_hex(3), password_hash="x", status="active", default_macro_region="eu")
    db.add(a); db.commit()
    db.add(FreeConfigGlobal(is_enabled=True, default_daily_limit_mb=200, verification_bot_token_enc=b"t"))
    db.add(AdminFreeConfig(admin_id=a.id, is_enabled=True, kind="per_user"))
    u = AdminUser(admin_id=a.id, username="u"+secrets.token_hex(3), status=status,
                  telegram_id=int(secrets.token_hex(3),16), telegram_chat_id=1, language="fa",
                  subscription_token=secrets.token_hex(16))
    db.add(u); db.commit()
    db.add(FreeConfigEnrollment(user_id=u.id, admin_id=a.id, membership_ok=membership_ok, suspended_reason=reason))
    db.commit()
    return a, u


def _verify_returns(result):
    async def _fn(db, policy, telegram_id):
        return result
    return _fn


def test_compliant_to_noncompliant_suspends(db_session):
    a, u = _enrolled(db_session)
    recheck_memberships_impl(db_session, _verify_returns(VerificationResult(ok=False, missing=[SimpleNamespace()])))
    db_session.refresh(u)
    enr = db_session.query(FreeConfigEnrollment).filter_by(user_id=u.id).first()
    assert u.status == "suspended" and enr.suspended_reason == "membership" and enr.membership_ok is False


def test_membership_suspended_to_compliant_restores(db_session):
    a, u = _enrolled(db_session, status="suspended", membership_ok=False, reason="membership")
    recheck_memberships_impl(db_session, _verify_returns(VerificationResult(ok=True)))
    db_session.refresh(u)
    enr = db_session.query(FreeConfigEnrollment).filter_by(user_id=u.id).first()
    assert u.status == "active" and enr.suspended_reason is None and enr.membership_ok is True


def test_unverifiable_makes_no_state_change(db_session):
    a, u = _enrolled(db_session)
    recheck_memberships_impl(db_session, _verify_returns(VerificationResult(ok=False, unverifiable=[SimpleNamespace()])))
    db_session.refresh(u)
    assert u.status == "active"


def test_never_touches_wallet_suspended_user(db_session):
    a, u = _enrolled(db_session, status="suspended", membership_ok=True, reason=None)  # wallet suspend
    recheck_memberships_impl(db_session, _verify_returns(VerificationResult(ok=True)))
    db_session.refresh(u)
    assert u.status == "suspended"   # not restored: not our suspension


def test_recheck_skips_user_with_active_paid_subscription(db_session):
    # A user who upgraded to a paid plan (future expiry) must not be
    # membership-suspended by the free-config recheck, even if a stale
    # enrollment lingers.
    a, u = _enrolled(db_session)  # active, membership_ok, enrollment present
    u.expires_at = datetime.utcnow() + timedelta(days=30)
    db_session.commit()
    recheck_memberships_impl(
        db_session,
        _verify_returns(VerificationResult(ok=False, missing=[SimpleNamespace()])),
    )
    db_session.refresh(u)
    assert u.status == "active"   # paid user untouched by free-config recheck
