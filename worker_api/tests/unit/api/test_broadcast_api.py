from unittest.mock import patch

from app.core.auth.jwt import create_access_token
from app.models.admins import Admin
from app.models.admin_bots import AdminBot
from app.models.admin_users import AdminUser
from app.models.broadcast import Broadcast


def _admin(db, name="r1"):
    a = Admin(username=name, password_hash="x", status="active")
    db.add(a)
    db.flush()
    return a


def _bot(db, admin_id):
    db.add(AdminBot(
        admin_id=admin_id, bot_token_enc=b"x", bot_username="b",
        bot_user_id=admin_id, webhook_secret="s", is_active=True,
    ))
    db.flush()


def _hdr(admin_id):
    tok = create_access_token({"sub": str(admin_id), "role": "admin"})
    return {"Authorization": f"Bearer {tok}"}


def test_audience_count(client, db):
    a = _admin(db)
    _bot(db, a.id)
    db.add(AdminUser(admin_id=a.id, username="u1", status="active", telegram_chat_id=5, language="fa"))
    db.commit()
    resp = client.post("/api/v1/admin/broadcasts/audience-count",
                       json={"segment": "all"}, headers=_hdr(a.id))
    assert resp.status_code == 200
    assert resp.json()["count"] == 1


def test_create_enqueues_and_persists(client, db):
    a = _admin(db)
    _bot(db, a.id)
    db.commit()
    with patch("app.api.v1.endpoints.broadcast_api.send_broadcast.delay") as delay:
        resp = client.post("/api/v1/admin/broadcasts",
                           json={"message_text": "hello", "segment": "all"},
                           headers=_hdr(a.id))
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "queued"
    delay.assert_called_once_with(body["id"])


def test_create_rejects_bad_html(client, db):
    a = _admin(db)
    _bot(db, a.id)
    db.commit()
    resp = client.post("/api/v1/admin/broadcasts",
                       json={"message_text": "<script>x</script>", "segment": "all"},
                       headers=_hdr(a.id))
    assert resp.status_code == 422


def test_create_blocked_when_disabled(client, db):
    a = _admin(db)
    a.broadcasts_enabled = False
    _bot(db, a.id)
    db.commit()
    resp = client.post("/api/v1/admin/broadcasts",
                       json={"message_text": "hi", "segment": "all"},
                       headers=_hdr(a.id))
    assert resp.status_code == 409


def test_get_scoped_to_owner(client, db):
    a1 = _admin(db, "r1")
    a2 = _admin(db, "r2")
    bc = Broadcast(admin_id=a1.id, segment="all", message_text="x", status="completed")
    db.add(bc)
    db.commit()
    # owner sees it
    assert client.get(f"/api/v1/admin/broadcasts/{bc.id}", headers=_hdr(a1.id)).status_code == 200
    # other reseller gets 404
    assert client.get(f"/api/v1/admin/broadcasts/{bc.id}", headers=_hdr(a2.id)).status_code == 404


def _sa_hdr(admin_id):
    tok = create_access_token({"sub": str(admin_id), "role": "super_admin"})
    return {"Authorization": f"Bearer {tok}"}


def test_superadmin_sees_all_resellers(client, db):
    sa = _admin(db, "super")
    a1 = _admin(db, "r1")
    a2 = _admin(db, "r2")
    db.add(Broadcast(admin_id=a1.id, segment="all", message_text="x", status="completed"))
    db.add(Broadcast(admin_id=a2.id, segment="all", message_text="y", status="completed"))
    db.commit()
    resp = client.get("/api/v1/super-admin/broadcasts", headers=_sa_hdr(sa.id))
    assert resp.status_code == 200
    assert len(resp.json()) >= 2
    # filter works
    resp2 = client.get(f"/api/v1/super-admin/broadcasts?admin_id={a1.id}", headers=_sa_hdr(sa.id))
    assert all(r["admin_id"] == a1.id for r in resp2.json())


def test_superadmin_toggle_kill_switch(client, db):
    sa = _admin(db, "super")
    a1 = _admin(db, "r1")
    db.commit()
    resp = client.patch(
        f"/api/v1/super-admin/admins/{a1.id}/broadcasts-enabled",
        json={"enabled": False}, headers=_sa_hdr(sa.id),
    )
    assert resp.status_code == 200
    assert resp.json()["broadcasts_enabled"] is False
    db.refresh(a1)
    assert a1.broadcasts_enabled is False


def test_reseller_cannot_use_superadmin_routes(client, db):
    a1 = _admin(db, "r1")
    db.commit()
    resp = client.get("/api/v1/super-admin/broadcasts", headers=_hdr(a1.id))
    assert resp.status_code == 403
