"""
Phase 4 unit tests for compliance soft-delete lifecycle.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.models import Subscription, SubscriptionPlan
from app.services.compliance.user_deletion import schedule_user_soft_delete
from tests.factories import UserFactory


def test_schedule_user_soft_delete_sets_retention_and_deactivates_access(db):
    user = UserFactory.create(telegram_user_id=710001, referral_code="PH4SOFT001")
    plan = SubscriptionPlan(
        name="Phase4 Plan",
        tier="bronze",
        duration_months=1,
        price_usd=Decimal("9.99"),
        max_protocols=1,
        max_connections=1,
    )
    db.add_all([user, plan])
    db.commit()
    db.refresh(user)
    db.refresh(plan)

    subscription = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        status="active",
        is_active=True,
        auto_renew=True,
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30),
    )
    user.refresh_token_jti = "test-jti"
    user.refresh_token_expires_at = datetime.now(timezone.utc).replace(
        tzinfo=None
    ) + timedelta(days=7)
    db.add(subscription)
    db.commit()
    db.refresh(user)
    db.refresh(subscription)

    requested_at = datetime(2026, 2, 20, 12, 0, 0)
    scheduled_at = schedule_user_soft_delete(
        user, requested_at=requested_at, retention_days=30
    )

    assert user.is_deleted is True
    assert user.deleted_at == requested_at
    assert scheduled_at == requested_at + timedelta(days=30)
    assert user.deletion_scheduled_at == scheduled_at
    assert user.refresh_token_jti is None
    assert user.refresh_token_expires_at is None
    assert subscription.is_active is False
    assert subscription.auto_renew is False
    assert subscription.status == "cancelled"


def test_schedule_user_soft_delete_is_idempotent(db):
    user = UserFactory.create(telegram_user_id=710002, referral_code="PH4SOFT002")
    db.add(user)
    db.commit()
    db.refresh(user)

    first_time = datetime(2026, 2, 20, 8, 0, 0)
    first_schedule = schedule_user_soft_delete(
        user, requested_at=first_time, retention_days=30
    )
    second_schedule = schedule_user_soft_delete(
        user,
        requested_at=first_time + timedelta(hours=1),
        retention_days=10,
    )

    assert first_schedule == second_schedule
    assert user.deleted_at == first_time
