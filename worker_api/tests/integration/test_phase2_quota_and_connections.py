from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.models import (
    ConnectionViolation,
    Credential,
    Protocol,
    Subscription,
    SubscriptionPlan,
    UsageAlert,
    UsageMetricDaily,
)
from app.tasks import usage_tasks


def test_usage_thresholds_progression_and_no_duplicate_spam(db, test_user, monkeypatch):
    user_id = test_user.id
    protocol = Protocol(
        name="ssh",
        slug="ssh",
        display_name="SSH",
        flux_app_name="fluxvpn-ssh",
        default_port=22,
        is_active=True,
    )
    plan = SubscriptionPlan(
        name="Bronze Monthly",
        tier="bronze",
        duration_months=1,
        price_usd=Decimal("5.00"),
        max_protocols=1,
        max_connections=1,
        data_limit_gb=10,
        daily_ip_changes=1,
    )
    db.add_all([protocol, plan])
    db.commit()
    db.refresh(protocol)
    db.refresh(plan)

    subscription = Subscription(
        user_id=test_user.id,
        plan_id=plan.id,
        status="active",
        is_active=True,
        started_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=2),
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=20),
    )
    db.add(subscription)
    db.commit()
    db.refresh(subscription)

    db.add(
        Credential(
            user_id=test_user.id,
            subscription_id=subscription.id,
            protocol_id=protocol.id,
            credential_data={"username": "phase2-user"},
        )
    )

    db.add(
        UsageMetricDaily(
            user_id=user_id,
            protocol_id=protocol.id,
            usage_date=datetime.now(timezone.utc).replace(tzinfo=None).date(),
            bytes_uploaded=5 * 1024**3,
            bytes_downloaded=6 * 1024**3,
            connection_count=20,
        )
    )
    db.commit()

    sent_notifications = []
    monkeypatch.setattr(db, "close", lambda: None)
    monkeypatch.setattr(usage_tasks, "SessionLocal", lambda: db)
    monkeypatch.setattr(
        usage_tasks,
        "send_notification_sync",
        lambda user_id, message, channel="telegram": sent_notifications.append(
            (user_id, message, channel)
        )
        or True,
    )

    first = usage_tasks.check_usage_thresholds()
    second = usage_tasks.check_usage_thresholds()

    alerts = db.query(UsageAlert).filter_by(subscription_id=subscription.id).all()
    thresholds = sorted(alert.threshold_percent for alert in alerts)
    db.refresh(subscription)

    assert first["alerts_sent"] == {"50%": 1, "80%": 1, "90%": 1, "100%": 1}
    assert second["alerts_sent"] == {"50%": 0, "80%": 0, "90%": 0, "100%": 0}
    assert thresholds == [50, 80, 90, 100]
    assert len(sent_notifications) == 4
    assert subscription.is_active is False
    assert subscription.status == "expired"


def test_monitor_concurrent_connections_blocks_over_limit(db, test_user, monkeypatch):
    user_id = test_user.id
    protocol = Protocol(
        name="ssh",
        slug="ssh",
        display_name="SSH",
        flux_app_name="fluxvpn-ssh",
        default_port=22,
        is_active=True,
    )
    plan = SubscriptionPlan(
        name="Bronze Monthly",
        tier="bronze",
        duration_months=1,
        price_usd=Decimal("5.00"),
        max_protocols=1,
        max_connections=1,
        data_limit_gb=20,
        daily_ip_changes=1,
    )
    db.add_all([protocol, plan])
    db.commit()
    db.refresh(protocol)
    db.refresh(plan)

    subscription = Subscription(
        user_id=test_user.id,
        plan_id=plan.id,
        status="active",
        is_active=True,
        started_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=2),
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=20),
    )
    db.add(subscription)
    db.commit()
    db.refresh(subscription)

    db.add(
        Credential(
            user_id=user_id,
            subscription_id=subscription.id,
            protocol_id=protocol.id,
            credential_data={"username": "phase2-user-conn"},
        )
    )
    db.commit()

    monkeypatch.setattr(db, "close", lambda: None)
    monkeypatch.setattr(usage_tasks, "SessionLocal", lambda: db)
    monkeypatch.setattr(
        usage_tasks,
        "collect_live_connection_counts",
        lambda instances: ({user_id: 3}, [], 1),
    )
    monkeypatch.setattr(
        usage_tasks, "fallback_connection_counts_from_logs", lambda _db, _ids: {}
    )
    monkeypatch.setattr(
        usage_tasks,
        "send_notification_sync",
        lambda user_id, message, channel="telegram": True,
    )

    result = usage_tasks.monitor_concurrent_connections()

    violation = db.query(ConnectionViolation).filter_by(user_id=user_id).first()
    assert result["violations"] == 1
    assert result["blocked"] == 1
    assert violation is not None
    assert violation.action_taken == "blocked"
