from app.models.admins import Admin
from app.models.broadcast import Broadcast


def test_broadcast_row_roundtrips(db):
    admin = Admin(username="r1", password_hash="x", status="active")
    db.add(admin)
    db.flush()
    bc = Broadcast(
        admin_id=admin.id,
        segment="all",
        message_text="hello",
        status="queued",
    )
    db.add(bc)
    db.flush()
    assert bc.id is not None
    assert bc.sent_count == 0
    assert bc.blocked_count == 0
    assert admin.broadcasts_enabled is True


from datetime import datetime, timedelta, timezone

from app.models.admin_users import AdminUser
from app.services.broadcasts.broadcast_service import (
    count_audience,
    resolve_audience,
)


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _mk_admin(db, name="r1"):
    a = Admin(username=name, password_hash="x", status="active")
    db.add(a)
    db.flush()
    return a


def _mk_user(db, admin_id, **kw):
    defaults = dict(
        admin_id=admin_id,
        username=f"u{kw.get('username_suffix', '')}",
        status="active",
        telegram_chat_id=1000 + kw.get("n", 0),
        language="fa",
    )
    defaults.pop("username", None)
    defaults["username"] = kw.pop("username", f"u{kw.pop('n', 0)}")
    defaults.update(kw)
    defaults.pop("username_suffix", None)
    u = AdminUser(**defaults)
    db.add(u)
    db.flush()
    return u


def test_all_segment_excludes_free_deleted_and_no_chat(db):
    a = _mk_admin(db)
    _mk_user(db, a.id, username="ok1", n=1)
    _mk_user(db, a.id, username="__free__", n=2)               # free sentinel
    _mk_user(db, a.id, username="deleted1", n=3, status="deleted")
    _mk_user(db, a.id, username="nochat", n=4, telegram_chat_id=None)
    assert count_audience(db, a.id, "all") == 1
    ids = [uid for uid, _chat in resolve_audience(db, a.id, "all")]
    assert len(ids) == 1


def test_language_segments(db):
    a = _mk_admin(db)
    _mk_user(db, a.id, username="fa1", n=1, language="fa")
    _mk_user(db, a.id, username="en1", n=2, language="en")
    assert count_audience(db, a.id, "lang_fa") == 1
    assert count_audience(db, a.id, "lang_en") == 1


def test_active_paid_segment(db):
    a = _mk_admin(db)
    _mk_user(db, a.id, username="paid", n=1, status="active", expires_at=_now() + timedelta(days=5))
    _mk_user(db, a.id, username="expsoon", n=2, status="active", expires_at=_now() - timedelta(days=1))
    _mk_user(db, a.id, username="nopaid", n=3, status="active", expires_at=None)
    assert count_audience(db, a.id, "active_paid") == 1


def test_expired_free_segment(db):
    a = _mk_admin(db)
    _mk_user(db, a.id, username="paid", n=1, status="active", expires_at=_now() + timedelta(days=5))
    _mk_user(db, a.id, username="expired", n=2, status="expired", expires_at=_now() - timedelta(days=1))
    _mk_user(db, a.id, username="never", n=3, status="active", expires_at=None)
    # expired + never-purchased = 2
    assert count_audience(db, a.id, "expired_free") == 2


def test_scoped_to_admin(db):
    a1 = _mk_admin(db, "r1")
    a2 = _mk_admin(db, "r2")
    _mk_user(db, a1.id, username="a", n=1)
    _mk_user(db, a2.id, username="b", n=2)
    assert count_audience(db, a1.id, "all") == 1
