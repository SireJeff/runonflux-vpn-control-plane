"""
Compliance lifecycle Celery tasks.
"""

import logging
from datetime import datetime, timezone

from celery import shared_task

from app.core.database import SessionLocal
from app.services.compliance import purge_expired_soft_deleted_users

logger = logging.getLogger(__name__)


@shared_task(name="compliance.cleanup_soft_deleted_users")
def cleanup_soft_deleted_users() -> dict:
    """
    Hard-delete users whose retention window has expired.
    """
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        result = purge_expired_soft_deleted_users(db, now=now)
        db.commit()
        logger.info(
            "Compliance cleanup complete. Deleted %s users.",
            result["deleted"],
        )
        return {
            "deleted": result["deleted"],
            "user_ids": result["user_ids"],
            "executed_at": now.isoformat(),
        }
    except Exception as exc:
        db.rollback()
        logger.error("Compliance cleanup failed: %s", str(exc))
        return {"error": str(exc)}
    finally:
        db.close()
