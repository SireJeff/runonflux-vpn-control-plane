import importlib

from app.core.auth.role_dependencies import RoleChecker
from app.core.database import get_db


def _patch_auth(monkeypatch, admin_id):
    """Bypass require_admin (= RoleChecker instance) to act as this admin id.
    Zero-param staticmethod — the proven pattern from test_admin_packages_api.py."""
    monkeypatch.setattr(
        RoleChecker,
        "__call__",
        staticmethod(lambda: {"id": admin_id, "role": "admin"}),
    )


def _client(db_session, monkeypatch, admin_id):
    _mod = importlib.import_module("app.api.v1.endpoints.admin_api")
    _patch_auth(monkeypatch, admin_id)
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(_mod.router, prefix="/api/v1")

    def _override():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override
    return TestClient(app)


def _seed(db_session, admin_id, admin_username, user_username):
    from app.models.admin_users import AdminUser
    from app.models.admins import Admin

    admin = Admin(
        id=admin_id, username=admin_username, password_hash="x", status="active"
    )
    db_session.add(admin)
    db_session.commit()
    user = AdminUser(admin_id=admin.id, username=user_username)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_renew_extend_days_writes_audit(db_session, monkeypatch):
    admin_id = 5001
    user = _seed(db_session, admin_id, "renew_adm", "renew_u")
    c = _client(db_session, monkeypatch, admin_id)

    resp = c.post(
        f"/api/v1/admin/users/{user.id}/renew",
        json={"extend_days": 30, "reason": "loyalty"},
        headers={"Authorization": "Bearer t"},
    )
    assert resp.status_code == 200, resp.text

    # Audit row landed in the DB.
    from app.models.user_adjustments import UserAdjustment

    rows = (
        db_session.query(UserAdjustment).filter(UserAdjustment.user_id == user.id).all()
    )
    assert any(r.action == "extend_days" for r in rows)

    # User-detail response surfaces the adjustment history.
    hist = c.get(
        f"/api/v1/admin/users/{user.id}", headers={"Authorization": "Bearer t"}
    ).json()
    assert any(a["action"] == "extend_days" for a in hist.get("adjustments", []))


def test_set_regions_rejects_unavailable_region(db_session, monkeypatch):
    admin_id = 5002
    user = _seed(db_session, admin_id, "regions_adm", "regions_u")
    c = _client(db_session, monkeypatch, admin_id)

    from app.services.regions import availability

    monkeypatch.setattr(availability, "healthy_macro_codes", lambda db: {"eu"})

    resp = c.put(
        f"/api/v1/admin/users/{user.id}/regions",
        json={"macro_regions": ["eu", "na"]},  # na unavailable
        headers={"Authorization": "Bearer t"},
    )
    assert resp.status_code == 400
