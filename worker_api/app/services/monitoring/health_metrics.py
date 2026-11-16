"""
Buffered API telemetry collection for admin health metrics.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Dict, Optional, cast

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import ApiRequestMetricHourly


@dataclass
class _HourBucket:
    request_count: int = 0
    total_response_time_ms: int = 0


class AdminHealthMetricsCollector:
    """
    Collect request metrics in-memory and flush to DB in coarse batches.
    """

    def __init__(self) -> None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        self._started_at = now
        self._last_flush_at = now
        self._pending: Dict[datetime, _HourBucket] = {}
        self._lock = Lock()

    @staticmethod
    def _hour_floor(value: datetime) -> datetime:
        return value.replace(minute=0, second=0, microsecond=0)

    @staticmethod
    def _to_int_ms(value: float) -> int:
        if value < 0:
            return 0
        return min(int(round(value)), settings.ADMIN_METRICS_MAX_RESPONSE_TIME_MS)

    def record_request(
        self, response_time_ms: float, *, observed_at: Optional[datetime] = None
    ) -> None:
        observed_at = observed_at or datetime.now(timezone.utc).replace(tzinfo=None)
        hour_start = self._hour_floor(observed_at)
        duration_ms = self._to_int_ms(response_time_ms)

        with self._lock:
            bucket = self._pending.setdefault(hour_start, _HourBucket())
            bucket.request_count += 1
            bucket.total_response_time_ms += duration_ms

    def should_flush(self, *, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now(timezone.utc).replace(tzinfo=None)
        with self._lock:
            pending_requests = sum(
                bucket.request_count for bucket in self._pending.values()
            )
            if pending_requests <= 0:
                return False

            elapsed = (now - self._last_flush_at).total_seconds()
            if (
                pending_requests >= settings.ADMIN_METRICS_MIN_FLUSH_REQUESTS
                and elapsed >= settings.ADMIN_METRICS_FLUSH_INTERVAL_SECONDS
            ):
                return True

            # Bound worst-case memory growth during very low traffic.
            if elapsed >= (settings.ADMIN_METRICS_FLUSH_INTERVAL_SECONDS * 5):
                return True

            return False

    def _drain_pending(
        self, *, now: datetime, force: bool
    ) -> Dict[datetime, _HourBucket]:
        with self._lock:
            if not self._pending:
                return {}

            elapsed = (now - self._last_flush_at).total_seconds()
            meets_threshold = (
                sum(bucket.request_count for bucket in self._pending.values())
                >= settings.ADMIN_METRICS_MIN_FLUSH_REQUESTS
            )
            exceeded_max_buffer_time = elapsed >= (
                settings.ADMIN_METRICS_FLUSH_INTERVAL_SECONDS * 5
            )

            if not force and not (
                (
                    meets_threshold
                    and elapsed >= settings.ADMIN_METRICS_FLUSH_INTERVAL_SECONDS
                )
                or exceeded_max_buffer_time
            ):
                return {}

            drained = self._pending
            self._pending = {}
            self._last_flush_at = now
            return drained

    def _requeue_pending(self, failed_payload: Dict[datetime, _HourBucket]) -> None:
        with self._lock:
            for hour_start, bucket in failed_payload.items():
                current = self._pending.setdefault(hour_start, _HourBucket())
                current.request_count += bucket.request_count
                current.total_response_time_ms += bucket.total_response_time_ms

    def flush_pending(
        self, db: Session, *, force: bool = False, now: Optional[datetime] = None
    ) -> int:
        now = now or datetime.now(timezone.utc).replace(tzinfo=None)
        payload = self._drain_pending(now=now, force=force)
        if not payload:
            return 0

        flushed_requests = sum(bucket.request_count for bucket in payload.values())

        try:
            for hour_start, bucket in payload.items():
                row = (
                    db.query(ApiRequestMetricHourly)
                    .filter(ApiRequestMetricHourly.hour_start == hour_start)
                    .first()
                )
                if row:
                    row_obj = cast(Any, row)
                    row_obj.request_count += bucket.request_count
                    row_obj.total_response_time_ms += bucket.total_response_time_ms
                else:
                    db.add(
                        ApiRequestMetricHourly(
                            hour_start=hour_start,
                            request_count=bucket.request_count,
                            total_response_time_ms=bucket.total_response_time_ms,
                        )
                    )

            db.commit()
            return flushed_requests
        except Exception:
            db.rollback()
            self._requeue_pending(payload)
            return 0

    def get_today_metrics(
        self, db: Session, *, now: Optional[datetime] = None
    ) -> Dict[str, float | int]:
        now = now or datetime.now(timezone.utc).replace(tzinfo=None)
        self.flush_pending(db, force=True, now=now)

        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_start = today_start + timedelta(days=1)
        request_count, total_ms = (
            db.query(
                func.coalesce(func.sum(ApiRequestMetricHourly.request_count), 0),
                func.coalesce(
                    func.sum(ApiRequestMetricHourly.total_response_time_ms), 0
                ),
            )
            .filter(
                ApiRequestMetricHourly.hour_start >= today_start,
                ApiRequestMetricHourly.hour_start < tomorrow_start,
            )
            .one()
        )

        request_count = int(request_count or 0)
        total_ms = int(total_ms or 0)
        avg_ms = float(total_ms / request_count) if request_count > 0 else 0.0
        uptime_hours = max((now - self._started_at).total_seconds() / 3600.0, 0.0)

        return {
            "api_uptime_hours": round(uptime_hours, 4),
            "total_requests_today": request_count,
            "avg_response_time_ms": round(avg_ms, 2),
        }

    def reset_for_tests(self, *, started_at: Optional[datetime] = None) -> None:
        test_now = started_at or datetime.now(timezone.utc).replace(tzinfo=None)
        with self._lock:
            self._pending = {}
            self._started_at = test_now
            self._last_flush_at = test_now


admin_health_metrics = AdminHealthMetricsCollector()
