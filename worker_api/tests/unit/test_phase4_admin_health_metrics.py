"""
Phase 4 unit tests for admin health telemetry aggregation.
"""

from datetime import datetime, timedelta

from app.services.monitoring.health_metrics import AdminHealthMetricsCollector


def test_admin_health_metrics_aggregation_and_daily_reset(db):
    collector = AdminHealthMetricsCollector()
    base_time = datetime(2099, 1, 15, 10, 0, 0)
    collector.reset_for_tests(started_at=base_time - timedelta(hours=2))

    # Yesterday's traffic should not be included in today's totals.
    collector.record_request(100, observed_at=base_time - timedelta(days=1))

    # Today's requests.
    collector.record_request(100, observed_at=base_time)
    collector.record_request(300, observed_at=base_time + timedelta(minutes=5))

    flushed = collector.flush_pending(
        db, force=True, now=base_time + timedelta(minutes=6)
    )
    assert flushed == 3

    metrics = collector.get_today_metrics(db, now=base_time + timedelta(minutes=6))
    assert metrics["total_requests_today"] == 2
    assert metrics["avg_response_time_ms"] == 200.0
    assert metrics["api_uptime_hours"] > 0


def test_admin_health_metrics_reset_clears_pending_state(db):
    collector = AdminHealthMetricsCollector()
    base_time = datetime(2099, 2, 1, 9, 0, 0)
    collector.record_request(250, observed_at=base_time)
    # Low-traffic safety path triggers a forced flush after extended buffer time.
    assert collector.should_flush(now=base_time + timedelta(minutes=10)) is True

    collector.reset_for_tests(started_at=base_time)
    assert collector.should_flush(now=base_time + timedelta(minutes=10)) is False

    collector.flush_pending(db, force=True, now=base_time + timedelta(minutes=10))
    metrics = collector.get_today_metrics(db, now=base_time + timedelta(minutes=10))
    assert metrics["total_requests_today"] == 0
