"""Helpers for usage metric aggregation and idempotent upserts."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Dict, List, Tuple

from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import ConnectionLog, UsageMetricDaily, UsageMetricHourly


def upsert_hourly_usage_metrics(
    db: Session,
    start_time: datetime,
    end_time: datetime,
) -> int:
    """Recompute and upsert hourly usage metrics for a time window."""

    stmt = (
        select(
            ConnectionLog.user_id,
            ConnectionLog.protocol_id,
            func.date_trunc("hour", ConnectionLog.connected_at).label("hour_start"),
            func.coalesce(func.sum(ConnectionLog.bytes_uploaded), 0).label(
                "bytes_uploaded"
            ),
            func.coalesce(func.sum(ConnectionLog.bytes_downloaded), 0).label(
                "bytes_downloaded"
            ),
            func.count(ConnectionLog.id).label("connection_count"),
        )
        .where(
            and_(
                ConnectionLog.connected_at >= start_time,
                ConnectionLog.connected_at < end_time,
            )
        )
        .group_by(
            ConnectionLog.user_id,
            ConnectionLog.protocol_id,
            func.date_trunc("hour", ConnectionLog.connected_at),
        )
    )

    rows = db.execute(stmt).all()
    payloads = [
        {
            "user_id": row.user_id,
            "protocol_id": row.protocol_id,
            "hour_start": row.hour_start,
            "bytes_uploaded": int(row.bytes_uploaded or 0),
            "bytes_downloaded": int(row.bytes_downloaded or 0),
            "connection_count": int(row.connection_count or 0),
        }
        for row in rows
    ]

    if not payloads:
        return 0

    upsert_stmt = insert(UsageMetricHourly).values(payloads)
    upsert_stmt = upsert_stmt.on_conflict_do_update(
        constraint="uq_usage_hourly_user_protocol_hour",
        set_={
            "bytes_uploaded": upsert_stmt.excluded.bytes_uploaded,
            "bytes_downloaded": upsert_stmt.excluded.bytes_downloaded,
            "connection_count": upsert_stmt.excluded.connection_count,
            "updated_at": func.current_timestamp(),
        },
    )
    db.execute(upsert_stmt)
    return len(payloads)


def upsert_daily_usage_metrics(
    db: Session,
    usage_date: date,
) -> int:
    """Recompute and upsert daily usage metrics for a specific UTC date."""

    start_time = datetime.combine(usage_date, datetime.min.time())
    end_time = datetime.combine(usage_date, datetime.max.time())

    stmt = (
        select(
            ConnectionLog.user_id,
            ConnectionLog.protocol_id,
            func.coalesce(func.sum(ConnectionLog.bytes_uploaded), 0).label(
                "bytes_uploaded"
            ),
            func.coalesce(func.sum(ConnectionLog.bytes_downloaded), 0).label(
                "bytes_downloaded"
            ),
            func.count(ConnectionLog.id).label("connection_count"),
        )
        .where(
            and_(
                ConnectionLog.connected_at >= start_time,
                ConnectionLog.connected_at <= end_time,
            )
        )
        .group_by(ConnectionLog.user_id, ConnectionLog.protocol_id)
    )

    rows = db.execute(stmt).all()
    payloads = [
        {
            "user_id": row.user_id,
            "protocol_id": row.protocol_id,
            "usage_date": usage_date,
            "bytes_uploaded": int(row.bytes_uploaded or 0),
            "bytes_downloaded": int(row.bytes_downloaded or 0),
            "connection_count": int(row.connection_count or 0),
        }
        for row in rows
    ]

    if not payloads:
        return 0

    upsert_stmt = insert(UsageMetricDaily).values(payloads)
    upsert_stmt = upsert_stmt.on_conflict_do_update(
        constraint="uq_usage_daily_user_protocol_date",
        set_={
            "bytes_uploaded": upsert_stmt.excluded.bytes_uploaded,
            "bytes_downloaded": upsert_stmt.excluded.bytes_downloaded,
            "connection_count": upsert_stmt.excluded.connection_count,
            "updated_at": func.current_timestamp(),
        },
    )
    db.execute(upsert_stmt)
    return len(payloads)


def get_user_usage_summary(db: Session, user_id: int, days: int = 30) -> Dict[str, int]:
    """Return summary totals for a user's recent daily metrics."""

    cutoff = datetime.now(timezone.utc).replace(tzinfo=None).date().toordinal() - max(
        days, 1
    )
    cutoff_date = date.fromordinal(cutoff)

    row = (
        db.query(
            func.coalesce(func.sum(UsageMetricDaily.bytes_uploaded), 0).label(
                "uploaded"
            ),
            func.coalesce(func.sum(UsageMetricDaily.bytes_downloaded), 0).label(
                "downloaded"
            ),
            func.coalesce(func.sum(UsageMetricDaily.connection_count), 0).label(
                "connections"
            ),
        )
        .filter(
            UsageMetricDaily.user_id == user_id,
            UsageMetricDaily.usage_date >= cutoff_date,
        )
        .first()
    )
    if row is None:
        return {
            "bytes_uploaded": 0,
            "bytes_downloaded": 0,
            "connection_count": 0,
        }
    return {
        "bytes_uploaded": int(row.uploaded or 0),
        "bytes_downloaded": int(row.downloaded or 0),
        "connection_count": int(row.connections or 0),
    }


def get_protocol_daily_totals(db: Session, usage_date: date) -> List[Tuple[int, int]]:
    """Return per-protocol bytes total for a given date."""

    rows = (
        db.query(
            UsageMetricDaily.protocol_id,
            func.sum(
                UsageMetricDaily.bytes_uploaded + UsageMetricDaily.bytes_downloaded
            ).label("total_bytes"),
        )
        .filter(UsageMetricDaily.usage_date == usage_date)
        .group_by(UsageMetricDaily.protocol_id)
        .all()
    )
    return [(row.protocol_id, int(row.total_bytes or 0)) for row in rows]
