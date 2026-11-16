from datetime import datetime, timedelta, timezone

from app.models.admins import Admin
from app.models.admin_bots import AdminBot
from app.models.broadcast import Broadcast
from app.services.broadcasts.broadcast_service import can_broadcast


def _naive_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _admin(db, enabled=True):
    a = Admin(username="r1", password_hash="x", status="active")
    a.broadcasts_enabled = enabled
    db.add(a)
    db.flush()
    return a


def _bot(db, admin_id, active=True):
    b = AdminBot(
        admin_id=admin_id,
        bot_token_enc=b"x",
        bot_username="b",
        bot_user_id=1,
        webhook_secret="s",
        is_active=active,
    )
    db.add(b)
    db.flush()
    return b


def test_ok_when_enabled_bot_active_no_inflight(db):
    a = _admin(db)
    _bot(db, a.id)
    assert can_broadcast(db, a.id).ok is True


def test_disabled_flag_blocks(db):
    a = _admin(db, enabled=False)
    _bot(db, a.id)
    r = can_broadcast(db, a.id)
    assert r.ok is False and r.reason == "disabled"


def test_no_active_bot_blocks(db):
    a = _admin(db)
    _bot(db, a.id, active=False)
    r = can_broadcast(db, a.id)
    assert r.ok is False and r.reason == "no_bot"


def test_in_flight_blocks(db):
    a = _admin(db)
    _bot(db, a.id)
    db.add(Broadcast(admin_id=a.id, segment="all", message_text="x", status="sending"))
    db.flush()
    r = can_broadcast(db, a.id)
    assert r.ok is False and r.reason == "in_flight"


def test_rate_limit_blocks(db, monkeypatch):
    from app.services.broadcasts import broadcast_service
    monkeypatch.setattr(broadcast_service.settings, "BROADCAST_MAX_PER_DAY", 2)
    a = _admin(db)
    _bot(db, a.id)
    for _ in range(2):
        db.add(Broadcast(admin_id=a.id, segment="all", message_text="x", status="completed"))
    db.flush()
    r = can_broadcast(db, a.id)
    assert r.ok is False and r.reason == "rate_limited"


def test_stale_sending_row_does_not_block(db):
    """A 'sending' row stranded by a crashed worker self-heals after the stale window."""
    a = _admin(db)
    _bot(db, a.id)
    stale = Broadcast(admin_id=a.id, segment="all", message_text="x", status="sending")
    stale.started_at = _naive_now() - timedelta(minutes=31)
    db.add(stale)
    db.flush()
    assert can_broadcast(db, a.id).ok is True


def test_fresh_sending_row_still_blocks(db):
    """A recently-started 'sending' row still blocks (real in-flight broadcast)."""
    a = _admin(db)
    _bot(db, a.id)
    fresh = Broadcast(admin_id=a.id, segment="all", message_text="x", status="sending")
    fresh.started_at = _naive_now() - timedelta(minutes=5)
    db.add(fresh)
    db.flush()
    r = can_broadcast(db, a.id)
    assert r.ok is False and r.reason == "in_flight"
