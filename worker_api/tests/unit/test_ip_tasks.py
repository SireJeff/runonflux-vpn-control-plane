"""
Unit tests for IP change processing tasks.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.models import (
    Credential,
    IPChangeRequest,
    ProtocolInstance,
    Subscription,
    SubscriptionPlan,
)
from app.tasks.ip_tasks import (
    _find_available_instance,
    cleanup_old_ip_requests,
    process_ip_change,
)
from tests.factories import UserFactory


def _create_plan(db):
    plan = SubscriptionPlan(
        name=f"IP Tasks Plan {datetime.now(timezone.utc).replace(tzinfo=None).timestamp()}",
        tier="silver",
        duration_months=1,
        price_usd=Decimal("9.99"),
        max_protocols=1,
        max_connections=3,
        data_limit_gb=100,
        daily_ip_changes=3,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def _create_subscription(db, user_id: int, plan_id: int):
    subscription = Subscription(
        user_id=user_id,
        plan_id=plan_id,
        status="active",
        is_active=True,
        started_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1),
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30),
        auto_renew=True,
    )
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return subscription


def _create_instance(
    db,
    protocol_id: int,
    instance_number: int,
    country_code: str,
    country_name: str,
):
    instance = ProtocolInstance(
        protocol_id=protocol_id,
        flux_app_name=f"fluxvpn-{country_code.lower()}-{instance_number}",
        component_name="vless",
        instance_number=instance_number,
        flux_node_name=f"{country_code.lower()}-{instance_number}.flux.local",
        ip_address=f"10.200.{instance_number}.10",
        country_code=country_code,
        country_name=country_name,
        city="Test City",
        health_status="healthy",
        is_active=True,
    )
    db.add(instance)
    db.commit()
    db.refresh(instance)
    return instance


def _create_credential(
    db, user_id: int, subscription_id: int, protocol_id: int, instance_id: int
):
    credential = Credential(
        user_id=user_id,
        subscription_id=subscription_id,
        protocol_id=protocol_id,
        credential_data={
            "instance_id": instance_id,
            "server": f"10.200.{instance_id}.10",
            "server_ip": f"10.200.{instance_id}.10",
            "port": 443,
            "username": f"user_{user_id}",
            "is_active": True,
        },
        server_location="Legacy Location",
    )
    db.add(credential)
    db.commit()
    db.refresh(credential)
    return credential


class _SessionProxy:
    """Proxy that forwards to fixture session but keeps close() as a no-op."""

    def __init__(self, session):
        self._session = session

    def __getattr__(self, item):
        return getattr(self._session, item)

    def close(self):
        return None


class TestProcessIpChange:
    def test_nonexistent_request_returns_error(self):
        result = process_ip_change(999999)
        assert result["success"] is False
        assert result["status"] == "error"

    def test_already_processed_request_returns_error(
        self, db, test_user, test_protocol
    ):
        plan = _create_plan(db)
        subscription = _create_subscription(db, test_user.id, plan.id)
        ip_request = IPChangeRequest(
            user_id=test_user.id,
            subscription_id=subscription.id,
            protocol_id=test_protocol.id,
            status="completed",
        )
        db.add(ip_request)
        db.commit()
        db.refresh(ip_request)

        with patch("app.tasks.ip_tasks.SessionLocal", return_value=_SessionProxy(db)):
            result = process_ip_change(ip_request.id)

        assert result["success"] is False
        assert result["status"] == "error"

    def test_successful_ip_change(self, db, test_user, test_protocol):
        plan = _create_plan(db)
        subscription = _create_subscription(db, test_user.id, plan.id)

        old_instance = _create_instance(
            db,
            protocol_id=test_protocol.id,
            instance_number=1,
            country_code="NL",
            country_name="Netherlands",
        )
        new_instance = _create_instance(
            db,
            protocol_id=test_protocol.id,
            instance_number=2,
            country_code="US",
            country_name="United States",
        )

        credential = _create_credential(
            db,
            user_id=test_user.id,
            subscription_id=subscription.id,
            protocol_id=test_protocol.id,
            instance_id=old_instance.id,
        )

        ip_request = IPChangeRequest(
            user_id=test_user.id,
            subscription_id=subscription.id,
            protocol_id=test_protocol.id,
            old_instance_id=old_instance.id,
            requested_country_code="US",
            status="pending",
        )
        db.add(ip_request)
        db.commit()
        db.refresh(ip_request)

        with patch("app.tasks.ip_tasks.SessionLocal", return_value=_SessionProxy(db)):
            result = process_ip_change(ip_request.id)

        db.refresh(ip_request)
        db.refresh(credential)
        updated_data = credential.credential_data

        assert result["success"] is True
        assert result["status"] == "success"
        assert ip_request.status == "completed"
        assert ip_request.new_instance_id == new_instance.id
        assert updated_data["instance_id"] == new_instance.id
        assert updated_data["country_code"] == "US"


class TestFindAvailableInstance:
    def test_no_instances_returns_none(self, db):
        result = _find_available_instance(
            db=db, protocol_id=9999, preferred_country="US"
        )
        assert result is None

    def test_returns_least_loaded_instance(self, db, test_protocol):
        plan = _create_plan(db)

        instance_a = _create_instance(
            db,
            protocol_id=test_protocol.id,
            instance_number=11,
            country_code="US",
            country_name="United States",
        )
        instance_b = _create_instance(
            db,
            protocol_id=test_protocol.id,
            instance_number=12,
            country_code="US",
            country_name="United States",
        )

        # Seed load: instance_a has two active credentials, instance_b has one.
        for index, instance_id in enumerate(
            [instance_a.id, instance_a.id, instance_b.id], start=1
        ):
            user = UserFactory.create(telegram_user_id=81000 + index)
            db.add(user)
            db.commit()
            db.refresh(user)

            subscription = _create_subscription(db, user.id, plan.id)
            _create_credential(
                db,
                user_id=user.id,
                subscription_id=subscription.id,
                protocol_id=test_protocol.id,
                instance_id=instance_id,
            )

        result = _find_available_instance(
            db=db,
            protocol_id=test_protocol.id,
            preferred_country="US",
        )

        assert result is not None
        assert result.id == instance_b.id


class TestCleanupOldIpRequests:
    def test_cleanup_returns_result(self, db, test_user, test_protocol):
        plan = _create_plan(db)
        subscription = _create_subscription(db, test_user.id, plan.id)

        stale_request = IPChangeRequest(
            user_id=test_user.id,
            subscription_id=subscription.id,
            protocol_id=test_protocol.id,
            status="pending",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None)
            - timedelta(days=35),
        )
        fresh_request = IPChangeRequest(
            user_id=test_user.id,
            subscription_id=subscription.id,
            protocol_id=test_protocol.id,
            status="pending",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None)
            - timedelta(days=2),
        )
        db.add_all([stale_request, fresh_request])
        db.commit()
        db.refresh(stale_request)
        db.refresh(fresh_request)

        with patch("app.tasks.ip_tasks.SessionLocal", return_value=_SessionProxy(db)):
            result = cleanup_old_ip_requests()

        db.refresh(stale_request)
        db.refresh(fresh_request)

        assert result["success"] is True
        assert result["cleaned_count"] == 1
        assert stale_request.status == "denied"
        assert fresh_request.status == "pending"

    def test_cleanup_handles_error(self):
        with patch("app.tasks.ip_tasks.SessionLocal") as mock_session_cls:
            mock_session = MagicMock()
            mock_session.query.side_effect = Exception("DB connection failed")
            mock_session_cls.return_value = mock_session

            result = cleanup_old_ip_requests()

            assert result["success"] is False
            assert result["status"] == "error"
