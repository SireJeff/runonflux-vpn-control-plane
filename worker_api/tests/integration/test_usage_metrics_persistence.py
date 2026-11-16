from datetime import datetime, timedelta, timezone

from app.models import ConnectionLog, ProtocolInstance, UsageMetricHourly
from app.services.usage.adapters import NormalizedUsageRecord
from app.services.usage.metrics_service import upsert_hourly_usage_metrics
from app.tasks import usage_tasks


def test_upsert_hourly_usage_metrics_is_idempotent(db, test_user, protocol_factory):
    protocol = protocol_factory.create(name="ssh", slug="ssh", display_name="SSH")
    db.add(protocol)
    db.commit()
    db.refresh(protocol)

    now = (
        datetime.now(timezone.utc)
        .replace(tzinfo=None)
        .replace(minute=10, second=0, microsecond=0)
    )
    db.add_all(
        [
            ConnectionLog(
                user_id=test_user.id,
                protocol_id=protocol.id,
                connected_at=now,
                bytes_uploaded=100,
                bytes_downloaded=300,
            ),
            ConnectionLog(
                user_id=test_user.id,
                protocol_id=protocol.id,
                connected_at=now + timedelta(minutes=5),
                bytes_uploaded=50,
                bytes_downloaded=150,
            ),
        ]
    )
    db.commit()

    window_start = now.replace(minute=0)
    window_end = window_start + timedelta(hours=1)

    first = upsert_hourly_usage_metrics(
        db, start_time=window_start, end_time=window_end
    )
    db.commit()
    second = upsert_hourly_usage_metrics(
        db, start_time=window_start, end_time=window_end
    )
    db.commit()

    row = (
        db.query(UsageMetricHourly)
        .filter_by(
            user_id=test_user.id, protocol_id=protocol.id, hour_start=window_start
        )
        .first()
    )

    assert first == 1
    assert second == 1
    assert row is not None
    assert row.bytes_uploaded == 150
    assert row.bytes_downloaded == 450
    assert row.connection_count == 2


def test_sync_protocol_usage_persists_logs_and_metrics(
    db, test_user, protocol_factory, monkeypatch
):
    user_id = test_user.id

    protocol = protocol_factory.create(name="ssh", slug="ssh", display_name="SSH")
    db.add(protocol)
    db.commit()
    db.refresh(protocol)

    instance = ProtocolInstance(
        protocol_id=protocol.id,
        flux_app_name="fluxvpn-ssh-test",
        component_name="ssh",
        instance_number=1,
        flux_node_name="test-node",
        ip_address="127.0.0.1",
        country_code="US",
        country_name="United States",
        health_status="healthy",
        is_active=True,
    )
    db.add(instance)
    db.commit()
    protocol_id = protocol.id

    class FakeAdapter:
        def collect(self, _instance):
            return [
                NormalizedUsageRecord(
                    user_id=user_id,
                    bytes_uploaded=200,
                    bytes_downloaded=800,
                    connected_at=datetime.now(timezone.utc)
                    .replace(tzinfo=None)
                    .replace(minute=0, second=0, microsecond=0),
                )
            ]

    monkeypatch.setattr(
        usage_tasks, "resolve_usage_adapter", lambda _name: FakeAdapter()
    )
    monkeypatch.setattr(usage_tasks, "SessionLocal", lambda: db)

    result = usage_tasks.sync_protocol_usage()

    assert result["synced"] == 1
    assert result["total"] == 1
    assert float(result["total_bandwidth_gb"]) > 0

    logs = (
        db.query(ConnectionLog)
        .filter_by(user_id=user_id, protocol_id=protocol_id)
        .all()
    )
    assert len(logs) == 1

    metrics = (
        db.query(UsageMetricHourly)
        .filter_by(user_id=user_id, protocol_id=protocol_id)
        .all()
    )
    assert len(metrics) == 1
