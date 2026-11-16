import secrets
import pytest
from app.services.free_config.enrollment_service import (
    FreeConfigEnrollmentService, FreeSlotsFullError,
)
from app.services.free_config.policy import EffectivePolicy, MIB
from app.models.admin_users import AdminUser
from app.models.admins import Admin


def _admin(db):
    a = Admin(username="r"+secrets.token_hex(3), password_hash="x", status="active", default_macro_region="eu")
    db.add(a); db.commit(); return a


def _user(db, admin_id, tg):
    u = AdminUser(admin_id=admin_id, username="u"+secrets.token_hex(3), status="lead",
                  telegram_id=tg, language="fa", subscription_token=secrets.token_hex(16))
    db.add(u); db.commit(); return u


def _policy(limit_mb=200, cap=None, region="eu"):
    return EffectivePolicy(enabled=True, required_channels=[], daily_limit_mb=limit_mb,
                           daily_limit_bytes=limit_mb*MIB, max_free_users=cap, region=region)


def test_provision_sets_limit_status_and_enrollment(db_session):
    a = _admin(db_session); u = _user(db_session, a.id, 1001)
    enr = FreeConfigEnrollmentService(db_session).provision(u, _policy(200))
    db_session.refresh(u)
    assert u.traffic_limit_bytes == 200 * MIB
    assert u.traffic_used_bytes == 0
    assert u.status == "active"
    assert enr.user_id == u.id and enr.membership_ok is True


def test_provision_is_idempotent(db_session):
    a = _admin(db_session); u = _user(db_session, a.id, 1002)
    svc = FreeConfigEnrollmentService(db_session)
    e1 = svc.provision(u, _policy())
    e2 = svc.provision(u, _policy())
    assert e1.id == e2.id
    assert svc.count_for_admin(a.id) == 1


def test_cap_refuses_new_claim(db_session):
    a = _admin(db_session)
    svc = FreeConfigEnrollmentService(db_session)
    svc.provision(_user(db_session, a.id, 1), _policy(cap=1))
    with pytest.raises(FreeSlotsFullError):
        svc.provision(_user(db_session, a.id, 2), _policy(cap=1))


def test_reactivates_membership_suspended_user(db_session):
    a = _admin(db_session); u = _user(db_session, a.id, 3)
    svc = FreeConfigEnrollmentService(db_session)
    enr = svc.provision(u, _policy())
    u.status = "suspended"; enr.membership_ok = False; enr.suspended_reason = "membership"
    db_session.commit()
    svc.provision(u, _policy())  # user rejoined & re-tapped
    db_session.refresh(u); db_session.refresh(enr)
    assert u.status == "active" and enr.membership_ok is True and enr.suspended_reason is None


from app.models.user_credentials_v2 import UserCredentialV2


def _sync_usernames(db, protocol="ssh"):
    # Mirror internal_v2.py /sync-users filter exactly.
    rows = (
        db.query(AdminUser.username)
        .join(UserCredentialV2, UserCredentialV2.user_id == AdminUser.id)
        .filter(
            AdminUser.status == "active",
            UserCredentialV2.protocol == protocol,
            ((AdminUser.traffic_limit_bytes.is_(None))
             | (AdminUser.traffic_used_bytes < AdminUser.traffic_limit_bytes)),
        ).all()
    )
    return {r[0] for r in rows}


def test_over_limit_free_user_excluded_then_included_after_reset(db_session):
    a = _admin(db_session); u = _user(db_session, a.id, 4)
    FreeConfigEnrollmentService(db_session).provision(u, _policy(200))
    u.traffic_used_bytes = u.traffic_limit_bytes  # exhausted
    db_session.commit()
    assert u.username not in _sync_usernames(db_session)
    u.traffic_used_bytes = 0  # simulate daily reset
    db_session.commit()
    assert u.username in _sync_usernames(db_session)
