"""
Unit tests for Subscription models (Protocol, SubscriptionPlan, Subscription)
"""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.models import Protocol, Subscription, SubscriptionPlan
from tests.factories import (
    ProtocolFactory,
    SubscriptionFactory,
    SubscriptionPlanFactory,
    UserFactory,
)


class TestProtocolModel:
    """Test cases for Protocol model"""

    def test_create_protocol(self, db):
        """Test creating a protocol"""
        protocol = ProtocolFactory.create()
        db.add(protocol)
        db.commit()
        db.refresh(protocol)

        assert protocol.id is not None
        assert protocol.name == "vless"
        assert protocol.display_name == "VLESS"
        assert protocol.is_active is True
        assert protocol.created_at is not None

    def test_protocol_unique_name(self, db):
        """Test that protocol name must be unique"""
        protocol1 = ProtocolFactory.create(name="unique_protocol")
        db.add(protocol1)
        db.commit()

        protocol2 = ProtocolFactory.create(name="unique_protocol")
        db.add(protocol2)

        with pytest.raises(Exception):  # IntegrityError
            db.commit()

    def test_create_vless_protocol(self, db):
        """Test creating VLESS protocol"""
        protocol = ProtocolFactory.create_vless()
        db.add(protocol)
        db.commit()
        db.refresh(protocol)

        assert protocol.name == "vless"
        assert protocol.default_port == 443

    def test_create_ssh_protocol(self, db):
        """Test creating SSH protocol"""
        protocol = ProtocolFactory.create_ssh()
        db.add(protocol)
        db.commit()
        db.refresh(protocol)

        assert protocol.name == "ssh"
        assert protocol.default_port == 22

    def test_create_clash_protocol(self, db):
        """Test creating Clash protocol"""
        protocol = ProtocolFactory.create_clash()
        db.add(protocol)
        db.commit()
        db.refresh(protocol)

        assert protocol.name == "clash"
        assert protocol.default_port == 7890

    def test_protocol_inactive(self, db):
        """Test creating inactive protocol"""
        protocol = ProtocolFactory.create(is_active=False)
        db.add(protocol)
        db.commit()
        db.refresh(protocol)

        assert protocol.is_active is False


class TestSubscriptionPlanModel:
    """Test cases for SubscriptionPlan model"""

    def test_create_subscription_plan(self, db):
        """Test creating a subscription plan"""
        plan = SubscriptionPlanFactory.create()
        db.add(plan)
        db.commit()
        db.refresh(plan)

        assert plan.id is not None
        assert plan.name == "Bronze Monthly"
        assert plan.tier == "bronze"
        assert plan.duration_months == 1
        assert plan.price_usd == Decimal("5.00")
        assert plan.max_protocols == 1
        assert plan.max_connections == 1
        assert plan.data_limit_gb == 100
        assert plan.daily_ip_changes == 1

    def test_create_trial_plan(self, db):
        """Test creating trial plan"""
        plan = SubscriptionPlanFactory.create_trial()
        db.add(plan)
        db.commit()
        db.refresh(plan)

        assert plan.tier == "bronze"
        assert plan.duration_months == 0
        assert plan.price_usd == Decimal("0.00")
        assert plan.data_limit_gb == 10

    def test_create_bronze_monthly(self, db):
        """Test creating bronze monthly plan"""
        plan = SubscriptionPlanFactory.create_bronze_monthly()
        db.add(plan)
        db.commit()
        db.refresh(plan)

        assert plan.tier == "bronze"
        assert plan.duration_months == 1
        assert plan.price_usd == Decimal("5.00")

    def test_create_silver_monthly(self, db):
        """Test creating silver monthly plan"""
        plan = SubscriptionPlanFactory.create_silver_monthly()
        db.add(plan)
        db.commit()
        db.refresh(plan)

        assert plan.tier == "silver"
        assert plan.max_protocols == 2
        assert plan.max_connections == 2
        assert plan.daily_ip_changes == 3

    def test_create_gold_yearly(self, db):
        """Test creating gold yearly plan"""
        plan = SubscriptionPlanFactory.create_gold_yearly()
        db.add(plan)
        db.commit()
        db.refresh(plan)

        assert plan.tier == "gold"
        assert plan.duration_months == 12
        assert plan.data_limit_gb is None  # Unlimited

    def test_plan_different_tiers(self, db):
        """Test creating plans with different tiers"""
        tiers = ["bronze", "silver", "gold", "platinum"]
        plans = []

        for tier in tiers:
            plan = SubscriptionPlanFactory.create(
                name=f"{tier.capitalize()} Plan",
                tier=tier,
            )
            plans.append(plan)
            db.add(plan)

        db.commit()

        db_plans = db.query(SubscriptionPlan).all()
        assert len(db_plans) == 4
        assert set(p.tier for p in db_plans) == set(tiers)


class TestSubscriptionModel:
    """Test cases for Subscription model"""

    def test_create_subscription(self, db):
        """Test creating a subscription"""
        user = UserFactory.create(telegram_user_id=12345)
        plan = SubscriptionPlanFactory.create()
        db.add(user)
        db.add(plan)
        db.commit()

        subscription = SubscriptionFactory.create(user.id, plan.id)
        db.add(subscription)
        db.commit()
        db.refresh(subscription)

        assert subscription.id is not None
        assert subscription.user_id == user.id
        assert subscription.plan_id == plan.id
        assert subscription.status == "active"
        assert subscription.auto_renew is False

    def test_subscription_active(self, db):
        """Test creating active subscription"""
        user = UserFactory.create(telegram_user_id=23456)
        plan = SubscriptionPlanFactory.create()
        db.add(user)
        db.add(plan)
        db.commit()

        subscription = SubscriptionFactory.create_active(user.id, plan.id)
        db.add(subscription)
        db.commit()
        db.refresh(subscription)

        assert subscription.status == "active"
        assert subscription.expires_at > datetime.now()

    def test_subscription_expired(self, db):
        """Test creating expired subscription"""
        user = UserFactory.create(telegram_user_id=34567)
        plan = SubscriptionPlanFactory.create()
        db.add(user)
        db.add(plan)
        db.commit()

        subscription = SubscriptionFactory.create_expired(user.id, plan.id)
        db.add(subscription)
        db.commit()
        db.refresh(subscription)

        assert subscription.status == "expired"
        assert subscription.expires_at < datetime.now()

    def test_subscription_with_auto_renew(self, db):
        """Test subscription with auto-renewal"""
        user = UserFactory.create(telegram_user_id=45678)
        plan = SubscriptionPlanFactory.create()
        db.add(user)
        db.add(plan)
        db.commit()

        subscription = SubscriptionFactory.create_with_auto_renew(user.id, plan.id)
        db.add(subscription)
        db.commit()
        db.refresh(subscription)

        assert subscription.auto_renew is True

    def test_subscription_expiring_soon(self, db):
        """Test subscription expiring soon"""
        user = UserFactory.create(telegram_user_id=56789)
        plan = SubscriptionPlanFactory.create()
        db.add(user)
        db.add(plan)
        db.commit()

        subscription = SubscriptionFactory.create_expiring_soon(
            user.id, plan.id, days=2
        )
        db.add(subscription)
        db.commit()
        db.refresh(subscription)

        now = datetime.now()
        expires = subscription.expires_at
        days_until_expiry = (expires - now).days

        assert days_until_expiry <= 2
        assert subscription.status == "active"

    def test_subscription_relationship_with_user(self, db):
        """Test subscription relationship with user"""
        user = UserFactory.create(telegram_user_id=67890)
        plan = SubscriptionPlanFactory.create()
        db.add(user)
        db.add(plan)
        db.commit()

        subscription = SubscriptionFactory.create(user.id, plan.id)
        db.add(subscription)
        db.commit()
        db.refresh(subscription)

        # Access relationship
        assert subscription.user.telegram_user_id == 67890

    def test_subscription_relationship_with_plan(self, db):
        """Test subscription relationship with plan"""
        user = UserFactory.create(telegram_user_id=78901)
        plan = SubscriptionPlanFactory.create(name="Test Plan")
        db.add(user)
        db.add(plan)
        db.commit()

        subscription = SubscriptionFactory.create(user.id, plan.id)
        db.add(subscription)
        db.commit()
        db.refresh(subscription)

        # Access relationship
        assert subscription.plan.name == "Test Plan"

    def test_multiple_subscriptions_per_user(self, db):
        """Test user can have multiple subscriptions"""
        user = UserFactory.create(telegram_user_id=89012)
        plan1 = SubscriptionPlanFactory.create(name="Plan 1")
        plan2 = SubscriptionPlanFactory.create(name="Plan 2", tier="silver")
        db.add_all([user, plan1, plan2])
        db.commit()

        sub1 = SubscriptionFactory.create_active(user.id, plan1.id)
        sub2 = SubscriptionFactory.create_expired(user.id, plan2.id)
        db.add_all([sub1, sub2])
        db.commit()

        user_subs = db.query(Subscription).filter_by(user_id=user.id).all()
        assert len(user_subs) == 2

    def test_subscription_cascade_delete(self, db):
        """Test subscription is deleted when user is deleted"""
        user = UserFactory.create(telegram_user_id=90123)
        plan = SubscriptionPlanFactory.create()
        db.add(user)
        db.add(plan)
        db.commit()

        subscription = SubscriptionFactory.create(user.id, plan.id)
        db.add(subscription)
        db.commit()

        user_id = user.id
        db.delete(user)
        db.commit()

        # Subscription should be deleted due to CASCADE
        remaining_subs = db.query(Subscription).filter_by(user_id=user_id).all()
        assert len(remaining_subs) == 0
