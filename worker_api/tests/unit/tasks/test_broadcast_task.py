from unittest.mock import patch

from app.models.admins import Admin
from app.models.admin_bots import AdminBot
from app.models.broadcast import Broadcast
from app.services.notifications.router import SendResult


def _seed(db):
    a = Admin(username="r1", password_hash="x", status="active")
    db.add(a)
    db.flush()
    bot = AdminBot(
        admin_id=a.id, bot_token_enc=b"enc", bot_username="b",
        bot_user_id=1, webhook_secret="s", is_active=True,
    )
    db.add(bot)
    bc = Broadcast(admin_id=a.id, segment="all", message_text="hi", status="queued")
    db.add(bc)
    db.flush()
    return a, bc


def test_task_tallies_and_completes(db):
    import app.tasks.broadcast_tasks as bt
    a, bc = _seed(db)

    results = iter([SendResult("sent"), SendResult("blocked"), SendResult("failed")])

    db._broadcast_owns_session = False
    with patch.object(bt, "SessionLocal", return_value=db), \
         patch.object(bt, "decrypt_token", return_value="tok"), \
         patch.object(bt, "resolve_audience", return_value=[(1, 111), (2, 222), (3, 333)]), \
         patch.object(bt.NotificationRouter, "send_raw", side_effect=lambda *a, **k: next(results)), \
         patch.object(bt.time, "sleep", return_value=None):
        out = bt.send_broadcast(bc.id)

    assert out == {"sent": 1, "blocked": 1, "failed": 1, "audience": 3}
    db.refresh(bc)
    assert bc.status == "completed"
    assert (bc.sent_count, bc.blocked_count, bc.failed_count) == (1, 1, 1)
    assert bc.audience_count == 3
    assert bc.started_at is not None and bc.completed_at is not None


def test_idempotency_guard_skips_completed(db):
    import app.tasks.broadcast_tasks as bt
    a, bc = _seed(db)
    bc.status = "completed"
    db.flush()
    db._broadcast_owns_session = False
    with patch.object(bt, "SessionLocal", return_value=db):
        out = bt.send_broadcast(bc.id)
    assert out == {"skipped": "completed"}


def test_no_active_bot_marks_failed(db):
    import app.tasks.broadcast_tasks as bt
    a, bc = _seed(db)
    db.query(AdminBot).filter(AdminBot.admin_id == a.id).update({"is_active": False})
    db.flush()
    db._broadcast_owns_session = False
    with patch.object(bt, "SessionLocal", return_value=db):
        out = bt.send_broadcast(bc.id)
    assert out == {"error": "no_bot"}
    db.refresh(bc)
    assert bc.status == "failed"
