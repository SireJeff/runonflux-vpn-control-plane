import secrets

from app.models.admin_users import AdminUser
from app.models.admins import Admin
from app.services.referral.codes import ensure_referral_code


def _user(db, username="alice"):
    a = Admin(
        username="r" + secrets.token_hex(3),
        password_hash="x",
        status="active",
        default_macro_region="eu",
    )
    db.add(a)
    db.commit()
    u = AdminUser(admin_id=a.id, username=username, status="active", language="fa")
    db.add(u)
    db.commit()
    return u


def test_mints_code_when_absent(db_session):
    u = _user(db_session, "alice")
    code = ensure_referral_code(u)
    assert code == u.referral_code
    assert code.startswith("ALICE-")
    assert len(code) > len("ALICE-")


def test_is_idempotent_when_present(db_session):
    u = _user(db_session, "bob")
    u.referral_code = "FIXED-CODE"
    assert ensure_referral_code(u) == "FIXED-CODE"
    assert u.referral_code == "FIXED-CODE"
