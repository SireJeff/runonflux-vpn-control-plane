"""
Integration Tests for Celery Background Tasks.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models import ConnectionLog, Credential, Subscription
from app.tasks.subscription_tasks import (
    calculate_churn_rate,
    cleanup_old_subscriptions,
    expire_subscriptions,
    expire_trials,
    process_auto_renewals,
)
from app.tasks.usage_tasks import (
    aggregate_daily_usage,
    calculate_bandwidth_stats,
    check_usage_thresholds,
    cleanup_old_logs,
)


class _SessionWrapper:
    def __init__(self, session):
        self._session = session

    def close(self):
        # Keep the shared transactional session open for test assertions.
        return None

    def __getattr__(self, item):
        return getattr(self._session, item)


class _SessionFactory:
    def __init__(self, session):
        self._session = session

    def __call__(self):
        return _SessionWrapper(self._session)


@pytest.fixture
def patched_task_sessions(monkeypatch, db):
    factory = _SessionFactory(db)
    monkeypatch.setattr("app.tasks.subscription_tasks.SessionLocal", factory)
    monkeypatch.setattr("app.tasks.usage_tasks.SessionLocal", factory)
    return db


@pytest.mark.celery
@pytest.mark.integration
@pytest.mark.usefixtures("patched_task_sessions")
class TestSubscriptionTasks:
    """Test subscription management Celery tasks."""

    def test_process_auto_renewals_success(
        self, db, test_user, subscription_plan_factory
    ):
        """Auto-renewal extends expiry when user has sufficient balance."""
        plan = subscription_plan_factory.create(
            name="AutoRenew Success Plan",
            tier="silver",
            duration_months=1,
            price_usd=Decimal("9.99"),
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)

        subscription = Subscription(
            user_id=test_user.id,
            plan_id=plan.id,
            started_at=datetime.now(timezone.utc).replace(tzinfo=None)
            - timedelta(days=29),
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None)
            + timedelta(hours=12),
            status="active",
            is_active=True,
            auto_renew=True,
            is_trial=False,
        )
        db.add(subscription)

        test_user.wallet_balance = Decimal("50.00")
        db.commit()
        db.refresh(subscription)

        initial_balance = test_user.wallet_balance
        initial_expires_at = subscription.expires_at

        result = process_auto_renewals()

        db.refresh(subscription)
        db.refresh(test_user)

        assert result["renewed"] == 1
        assert result["failed"] == 0
        assert subscription.expires_at > initial_expires_at
        assert subscription.is_active is True
        assert test_user.wallet_balance == initial_balance - Decimal(plan.price_usd)

    def test_process_auto_renewals_insufficient_balance(
        self, db, test_user, subscription_plan_factory
    ):
        """Auto-renewal is skipped when balance is insufficient."""
        plan = subscription_plan_factory.create(
            name="AutoRenew Insufficient Plan",
            tier="silver",
            duration_months=1,
            price_usd=Decimal("19.99"),
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)

        subscription = Subscription(
            user_id=test_user.id,
            plan_id=plan.id,
            started_at=datetime.now(timezone.utc).replace(tzinfo=None)
            - timedelta(days=29),
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None)
            + timedelta(hours=12),
            status="active",
            is_active=True,
            auto_renew=True,
        )
        db.add(subscription)

        test_user.wallet_balance = Decimal("1.00")
        db.commit()
        db.refresh(subscription)

        initial_expires_at = subscription.expires_at

        result = process_auto_renewals()

        db.refresh(subscription)
        assert result["failed"] == 1
        assert subscription.expires_at == initial_expires_at

    def test_expire_subscriptions_task(
        self,
        db,
        test_user,
        test_protocol,
        test_instance,
        subscription_plan_factory,
    ):
        """Expired subscriptions become inactive and deactivate credentials."""
        plan = subscription_plan_factory.create(
            name="Expired Sub Plan",
            tier="bronze",
            duration_months=1,
            price_usd=Decimal("5.00"),
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)

        subscription = Subscription(
            user_id=test_user.id,
            plan_id=plan.id,
            started_at=datetime.now(timezone.utc).replace(tzinfo=None)
            - timedelta(days=31),
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None)
            - timedelta(hours=1),
            status="active",
            is_active=True,
            auto_renew=False,
        )
        db.add(subscription)
        db.commit()
        db.refresh(subscription)

        credential = Credential(
            user_id=test_user.id,
            subscription_id=subscription.id,
            protocol_id=test_protocol.id,
            credential_data={
                "username": "test_user",
                "server": str(test_instance.ip_address),
                "server_ip": str(test_instance.ip_address),
                "port": 443,
                "instance_id": test_instance.id,
                "is_active": True,
            },
            server_location="United States (New York)",
        )
        db.add(credential)
        db.commit()

        result = expire_subscriptions()

        db.refresh(subscription)
        db.refresh(credential)

        assert result["expired"] == 1
        assert subscription.is_active is False
        assert credential.credential_data.get("is_active") is False

    def test_expire_trials_task(self, db, test_user, subscription_plan_factory):
        """Expired trials become inactive."""
        plan = subscription_plan_factory.create(
            name="Trial Plan",
            tier="bronze",
            duration_months=0,
            price_usd=Decimal("0.00"),
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)

        trial = Subscription(
            user_id=test_user.id,
            plan_id=plan.id,
            started_at=datetime.now(timezone.utc).replace(tzinfo=None)
            - timedelta(days=3),
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None)
            - timedelta(hours=1),
            status="active",
            is_active=True,
            is_trial=True,
        )

        db.add(trial)
        db.commit()

        result = expire_trials()

        db.refresh(trial)

        assert result["expired_trials"] == 1
        assert trial.is_active is False

    def test_calculate_churn_rate(self, db, test_user, subscription_plan_factory):
        """Churn calculation returns expected keys and non-negative rate."""
        thirty_days_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            days=30
        )

        plan = subscription_plan_factory.create(
            name="Churn Plan",
            tier="silver",
            duration_months=1,
            price_usd=Decimal("9.99"),
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)

        active_sub = Subscription(
            user_id=test_user.id,
            plan_id=plan.id,
            started_at=thirty_days_ago - timedelta(days=10),
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None)
            + timedelta(days=10),
            status="active",
            is_active=True,
            created_at=thirty_days_ago - timedelta(days=10),
        )

        db.add(active_sub)
        db.commit()

        result = calculate_churn_rate()

        assert "churn_rate" in result
        assert result["churn_rate"] >= 0

    def test_cleanup_old_subscriptions(self, db, test_user, subscription_plan_factory):
        """Old inactive subscriptions are deleted."""
        one_year_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            days=366
        )

        plan = subscription_plan_factory.create(
            name="Old Cleanup Plan",
            tier="bronze",
            duration_months=1,
            price_usd=Decimal("3.00"),
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)

        old_subscription = Subscription(
            user_id=test_user.id,
            plan_id=plan.id,
            started_at=one_year_ago - timedelta(days=30),
            expires_at=one_year_ago,
            status="expired",
            is_active=False,
            created_at=one_year_ago - timedelta(days=30),
        )

        db.add(old_subscription)
        db.commit()

        subscription_id = old_subscription.id

        result = cleanup_old_subscriptions()

        deleted_sub = db.query(Subscription).filter_by(id=subscription_id).first()

        assert result["deleted"] == 1
        assert deleted_sub is None


@pytest.mark.celery
@pytest.mark.integration
@pytest.mark.usefixtures("patched_task_sessions")
class TestUsageTasks:
    """Test usage tracking Celery tasks."""

    def test_check_usage_thresholds(
        self, db, test_user, active_subscription, test_credential
    ):
        """Threshold check task executes and returns summary keys."""
        result = check_usage_thresholds()
        assert "alerts_sent" in result

    def test_aggregate_daily_usage(self, db):
        """Daily aggregation task executes."""
        result = aggregate_daily_usage()
        assert "date" in result or "error" in result

    def test_cleanup_old_logs(self, db, test_user, test_protocol):
        """Connection logs older than 7 days are deleted."""
        eight_days_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            days=8
        )

        old_log = ConnectionLog(
            user_id=test_user.id,
            protocol_id=test_protocol.id,
            connected_at=eight_days_ago,
            disconnected_at=eight_days_ago + timedelta(hours=1),
            bytes_uploaded=1_000_000,
            bytes_downloaded=5_000_000,
        )

        db.add(old_log)
        db.commit()

        log_id = old_log.id

        result = cleanup_old_logs()

        deleted_log = db.query(ConnectionLog).filter_by(id=log_id).first()

        assert result["deleted"] >= 1
        assert deleted_log is None

    def test_calculate_bandwidth_stats(self, db):
        """Bandwidth stats task executes."""
        result = calculate_bandwidth_stats()
        assert "last_hour" in result or "error" in result


@pytest.mark.celery
class TestTaskScheduling:
    """Test that Celery Beat schedule is correctly configured."""

    def test_celery_beat_schedule_configured(self):
        """Required tasks are in beat schedule."""
        from app.core.celery_config import celery_app

        schedule = celery_app.conf.beat_schedule

        required_tasks = [
            "process-auto-renewals",
            "expire-subscriptions",
            "expire-trials",
            "sync-protocol-usage",
            "check-usage-thresholds",
            "cleanup-old-logs",
        ]

        for task_name in required_tasks:
            assert task_name in schedule, f"Task {task_name} not in beat schedule"

    def test_task_routing_configured(self):
        """Task routing maps are configured."""
        from app.core.celery_config import celery_app

        routes = celery_app.conf.task_routes

        assert "subscriptions.*" in routes
        assert "usage.*" in routes
        assert "flux.*" in routes
