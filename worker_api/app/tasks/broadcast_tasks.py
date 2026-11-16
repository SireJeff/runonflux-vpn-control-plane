"""Celery fan-out task that delivers a reseller broadcast to its audience."""

import logging
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.celery_config import celery_app
from app.core.crypto import decrypt_token
from app.core.database import SessionLocal
from app.models.admin_bots import AdminBot
from app.models.broadcast import Broadcast
from app.services.broadcasts.broadcast_service import resolve_audience
from app.services.notifications.router import NotificationRouter

logger = logging.getLogger(__name__)

_BROADCAST_PACE_SEC = 0.04
_MAX_RETRY_AFTER = 30.0


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@celery_app.task(name="broadcasts.send")
def send_broadcast(broadcast_id: int) -> dict:
    db: Session = SessionLocal()
    try:
        bc = db.query(Broadcast).filter(Broadcast.id == broadcast_id).first()
        if bc is None:
            return {"error": "not_found"}
        # Idempotency guard against Celery redelivery.
        if bc.status in ("sending", "completed"):
            return {"skipped": bc.status}

        bc.status = "sending"
        bc.started_at = _now()
        db.commit()

        bot = (
            db.query(AdminBot)
            .filter(AdminBot.admin_id == bc.admin_id, AdminBot.is_active == True)  # noqa: E712
            .first()
        )
        if bot is None:
            bc.status = "failed"
            bc.error = "no active bot"
            bc.completed_at = _now()
            db.commit()
            return {"error": "no_bot"}

        try:
            token = decrypt_token(bot.bot_token_enc)
        except Exception as e:
            logger.error(f"Broadcast {bc.id}: token decrypt failed: {e}")
            bc.status = "failed"
            bc.error = "token decrypt failed"
            bc.completed_at = _now()
            db.commit()
            return {"error": "decrypt"}

        audience = resolve_audience(db, bc.admin_id, bc.segment)
        bc.audience_count = len(audience)
        db.commit()

        reply_markup = None
        if bc.button_label and bc.button_url:
            reply_markup = {
                "inline_keyboard": [[{"text": bc.button_label, "url": bc.button_url}]]
            }

        sent = blocked = failed = 0
        for i, (_uid, chat_id) in enumerate(audience):
            result = NotificationRouter.send_raw(
                token, chat_id, bc.message_text, reply_markup=reply_markup
            )
            if result.status == "failed" and result.retry_after:
                time.sleep(min(result.retry_after, _MAX_RETRY_AFTER))
                result = NotificationRouter.send_raw(
                    token, chat_id, bc.message_text, reply_markup=reply_markup
                )
            if result.status == "sent":
                sent += 1
            elif result.status == "blocked":
                blocked += 1
            else:
                failed += 1

            if (i + 1) % 100 == 0:
                bc.sent_count, bc.blocked_count, bc.failed_count = sent, blocked, failed
                db.commit()
            time.sleep(_BROADCAST_PACE_SEC)

        bc.sent_count, bc.blocked_count, bc.failed_count = sent, blocked, failed
        bc.status = "completed"
        bc.completed_at = _now()
        db.commit()
        logger.info(
            f"Broadcast {bc.id} done: sent={sent} blocked={blocked} "
            f"failed={failed} audience={len(audience)}"
        )
        return {"sent": sent, "blocked": blocked, "failed": failed, "audience": len(audience)}
    finally:
        # Only close a session we own. In tests an external transactional session
        # is injected via a patched SessionLocal; closing it would break the test.
        if getattr(db, "_broadcast_owns_session", True):
            try:
                db.close()
            except Exception:
                pass
