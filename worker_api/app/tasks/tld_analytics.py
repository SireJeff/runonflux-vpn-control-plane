"""TldUsageDaily snapshot beat task (phase 5.2).

Daily snapshot of per-TLD active-user counts. Reads the SAME
``active_user_counts`` query the load-balancer uses, so analytics history
can never disagree with live routing (drift-proof). Prunes rows > 90 days.

Logic lives in ``run_tld_snapshot(db)`` (testable directly with a session);
the ``@shared_task`` wrapper is a thin SessionLocal/close shell.
"""
import logging
from datetime import date, timedelta

from celery import shared_task

from app.core.database import SessionLocal
from app.models.registered_tld import PURPOSES, RegisteredTld
from app.models.tld_usage_daily import TldUsageDaily
from app.services.tlds.selection import TldSelectionService

logger = logging.getLogger(__name__)

RETENTION_DAYS = 90


def _upsert_day(db, snapshot_date, purpose, tld, count):
    """Insert or update today's row for (date, purpose, tld). Idempotent."""
    row = (
        db.query(TldUsageDaily)
        .filter(
            TldUsageDaily.snapshot_date == snapshot_date,
            TldUsageDaily.purpose == purpose,
            TldUsageDaily.tld_id == tld.id,
        )
        .first()
    )
    if row is None:
        db.add(
            TldUsageDaily(
                snapshot_date=snapshot_date,
                purpose=purpose,
                tld_id=tld.id,
                domain_snapshot=tld.domain,
                active_user_count=count,  # domain frozen
            )
        )
    else:
        row.active_user_count = count
        row.domain_snapshot = tld.domain


def run_tld_snapshot(db, today=None):
    """Write one row per active non-deleted TLD per purpose (count may be 0)
    plus any TLD that still carries active users even if now inactive
    (migration tail). Count comes from ``active_user_counts`` — identical to
    the LB view. Returns the number of pruned rows.
    """
    today = today or date.today()
    svc = TldSelectionService(db)
    for purpose in PURPOSES:
        counts = svc.active_user_counts(purpose)  # {tld_id: count}
        active_tlds = (
            db.query(RegisteredTld)
            .filter(
                RegisteredTld.purpose == purpose,
                RegisteredTld.is_active.is_(True),
                RegisteredTld.deleted_at.is_(None),
            )
            .all()
        )
        snapshot_ids = {t.id for t in active_tlds} | set(counts.keys())
        active_by_id = {t.id: t for t in active_tlds}
        for tid in snapshot_ids:
            tld = active_by_id.get(tid) or db.get(RegisteredTld, tid)
            if tld is None or tld.deleted_at is not None:
                continue
            _upsert_day(db, today, purpose, tld, counts.get(tid, 0))

    cutoff = today - timedelta(days=RETENTION_DAYS)
    deleted = (
        db.query(TldUsageDaily)
        .filter(TldUsageDaily.snapshot_date < cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted


@shared_task(name="analytics.tld_snapshot")
def snapshot_tld_usage():
    """Daily Celery beat task — snapshot TLD usage. See run_tld_snapshot."""
    logger.info("Snapshotting TLD usage (analytics.tld_snapshot)")
    db = SessionLocal()
    try:
        return run_tld_snapshot(db)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
