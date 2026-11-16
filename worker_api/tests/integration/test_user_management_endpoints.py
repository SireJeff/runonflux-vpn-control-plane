import importlib

from app.core.auth.role_dependencies import RoleChecker
from app.core.database import get_db


def _client(db_session, monkeypatch, admin_id):
    _mod = importlib.import_module("app.api.v1.endpoints.admin_api")
    monkeypatch.setattr(
        RoleChecker, "__call__", staticmethod(lambda: {"id": admin_id, "role": "admin"})
    )
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(_mod.router, prefix="/api/v1")

    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    return TestClient(app)


def _seed_user(db_session, admin_id, admin_username, user_username, **kw):
    from app.models.admin_users import AdminUser
    from app.models.admins import Admin

    if not db_session.query(Admin).filter(Admin.id == admin_id).first():
        db_session.add(
            Admin(
                id=admin_id, username=admin_username, password_hash="x", status="active"
            )
        )
        db_session.commit()
    u = AdminUser(admin_id=admin_id, username=user_username, **kw)
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


def test_rename_rejects_global_collision(db_session, monkeypatch):
    admin_id = 6001
    _seed_user(
        db_session, 6000, "other_adm", "conflict_name"
    )  # different reseller holds it
    u = _seed_user(db_session, admin_id, "rn_adm", "rn_old")
    c = _client(db_session, monkeypatch, admin_id)
    resp = c.put(
        f"/api/v1/admin/users/{u.id}/username",
        json={"new_username": "conflict_name"},
        headers={"Authorization": "Bearer t"},
    )
    assert resp.status_code == 409, resp.text


def test_rename_success_audits(db_session, monkeypatch):
    admin_id = 6002
    u = _seed_user(db_session, admin_id, "rn2_adm", "rn2_old")
    c = _client(db_session, monkeypatch, admin_id)
    resp = c.put(
        f"/api/v1/admin/users/{u.id}/username",
        json={"new_username": "rn2_new"},
        headers={"Authorization": "Bearer t"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["username"] == "rn2_new"
    from app.models.user_adjustments import UserAdjustment

    assert (
        db_session.query(UserAdjustment)
        .filter(UserAdjustment.user_id == u.id, UserAdjustment.action == "set_username")
        .count()
        == 1
    )


def test_set_telegram_and_clear(db_session, monkeypatch):
    admin_id = 6003
    u = _seed_user(db_session, admin_id, "tg_adm", "tg_u")
    c = _client(db_session, monkeypatch, admin_id)
    r1 = c.put(
        f"/api/v1/admin/users/{u.id}/telegram",
        json={"telegram_id": 12345, "telegram_chat_id": 67890},
        headers={"Authorization": "Bearer t"},
    )
    assert r1.status_code == 200 and r1.json()["telegram_id"] == 12345
    r2 = c.put(
        f"/api/v1/admin/users/{u.id}/telegram",
        json={"telegram_id": None, "telegram_chat_id": None},
        headers={"Authorization": "Bearer t"},
    )
    assert r2.status_code == 200 and r2.json()["telegram_id"] is None


def test_reset_traffic_zeros_used(db_session, monkeypatch):
    admin_id = 6004
    u = _seed_user(
        db_session, admin_id, "rt_adm", "rt_u", traffic_used_bytes=9 * 1024**3
    )
    c = _client(db_session, monkeypatch, admin_id)
    resp = c.post(
        f"/api/v1/admin/users/{u.id}/reset-traffic",
        json={},
        headers={"Authorization": "Bearer t"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["traffic_used_gb"] == 0


def test_toggle_writes_status_audit(db_session, monkeypatch):
    admin_id = 7001
    u = _seed_user(db_session, admin_id, "tg_st_adm", "tg_st_u", status="active")
    c = _client(db_session, monkeypatch, admin_id)
    r = c.post(
        f"/api/v1/admin/users/{u.id}/toggle", headers={"Authorization": "Bearer t"}
    )
    assert r.status_code == 200
    from app.models.user_adjustments import UserAdjustment

    assert (
        db_session.query(UserAdjustment)
        .filter(UserAdjustment.user_id == u.id, UserAdjustment.action == "suspend")
        .count()
        == 1
    )


def test_renew_set_absolute_limit(db_session, monkeypatch):
    admin_id = 7002
    u = _seed_user(
        db_session, admin_id, "lim_adm", "lim_u", traffic_limit_bytes=1024**3
    )
    c = _client(db_session, monkeypatch, admin_id)
    r = c.post(
        f"/api/v1/admin/users/{u.id}/renew",
        json={"set_traffic_limit_gb": 50},
        headers={"Authorization": "Bearer t"},
    )
    assert r.status_code == 200, r.text
    assert abs(r.json()["traffic_limit_gb"] - 50.0) < 0.001
    r2 = c.post(
        f"/api/v1/admin/users/{u.id}/renew",
        json={"set_unlimited": True},
        headers={"Authorization": "Bearer t"},
    )
    assert r2.status_code == 200 and r2.json()["traffic_limit_gb"] is None


def test_detail_response_includes_telegram(db_session, monkeypatch):
    admin_id = 7003
    u = _seed_user(
        db_session, admin_id, "d_adm", "d_u", telegram_id=999, telegram_chat_id=888
    )
    c = _client(db_session, monkeypatch, admin_id)
    body = c.get(
        f"/api/v1/admin/users/{u.id}", headers={"Authorization": "Bearer t"}
    ).json()
    assert body["telegram_id"] == 999 and body["telegram_chat_id"] == 888


def test_update_user_traffic_limit_is_audited(db_session, monkeypatch):
    # Item 2: the edit-form (PUT /users/{id}) traffic-limit path must write an
    # audit row via set_traffic_limit, not mutate bytes silently.
    admin_id = 7101
    u = _seed_user(
        db_session, admin_id, "au_adm", "au_u", traffic_limit_bytes=1024**3
    )
    c = _client(db_session, monkeypatch, admin_id)
    r = c.put(
        f"/api/v1/admin/users/{u.id}",
        json={"traffic_limit_gb": 25},
        headers={"Authorization": "Bearer t"},
    )
    assert r.status_code == 200, r.text
    db_session.refresh(u)
    assert u.traffic_limit_bytes == 25 * 1024**3
    from app.models.user_adjustments import UserAdjustment

    assert (
        db_session.query(UserAdjustment)
        .filter(
            UserAdjustment.user_id == u.id, UserAdjustment.action == "set_traffic_limit"
        )
        .count()
        == 1
    )


def test_rename_to_current_is_noop(db_session, monkeypatch):
    # Item 3a: renaming to the current username is an idempotent 200 no-op,
    # not a 400 — and it writes no audit row.
    admin_id = 7102
    u = _seed_user(db_session, admin_id, "noop_adm", "noop_u")
    c = _client(db_session, monkeypatch, admin_id)
    r = c.put(
        f"/api/v1/admin/users/{u.id}/username",
        json={"new_username": "noop_u"},
        headers={"Authorization": "Bearer t"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["username"] == "noop_u"
    from app.models.user_adjustments import UserAdjustment

    assert (
        db_session.query(UserAdjustment)
        .filter(UserAdjustment.user_id == u.id, UserAdjustment.action == "set_username")
        .count()
        == 0
    )


def test_renew_zero_limit_returns_clear_400(db_session, monkeypatch):
    # Item 3b: a 0 absolute limit returns a friendly 400, not a raw 422.
    admin_id = 7103
    u = _seed_user(db_session, admin_id, "z_adm", "z_u", traffic_limit_bytes=1024**3)
    c = _client(db_session, monkeypatch, admin_id)
    r = c.post(
        f"/api/v1/admin/users/{u.id}/renew",
        json={"set_traffic_limit_gb": 0},
        headers={"Authorization": "Bearer t"},
    )
    assert r.status_code == 400, r.text
    assert "greater than 0" in r.json()["detail"]
