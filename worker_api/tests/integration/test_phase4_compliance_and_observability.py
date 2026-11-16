"""
Phase 4 integration tests:
- soft-delete lifecycle
- retention-expiry cleanup
- admin health telemetry
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.core.auth import create_access_token
from app.models import Subscription, SubscriptionPlan, User
from app.services.monitoring import admin_health_metrics
from app.tasks import compliance_tasks
from tests.factories import UserFactory


def _auth_headers(user_id: int) -> dict:
    token = create_access_token({"sub": str(user_id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.integration
class TestPhase4ComplianceLifecycle:
    def test_delete_flow_soft_deletes_and_hides_account(self, client, db, test_user):
        plan = SubscriptionPlan(
            name="Phase4 Retention Plan",
            tier="bronze",
            duration_months=1,
            price_usd=Decimal("5.00"),
            max_protocols=1,
            max_connections=1,
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)

        subscription = Subscription(
            user_id=test_user.id,
            plan_id=plan.id,
            status="active",
            is_active=True,
            auto_renew=True,
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None)
            + timedelta(days=30),
        )
        db.add(subscription)
        db.commit()
        db.refresh(subscription)

        headers = _auth_headers(test_user.id)

        delete_response = client.delete("/api/v1/users/me", headers=headers)
        assert delete_response.status_code == 200
        delete_payload = delete_response.json()
        assert delete_payload["data"]["user_id"] == test_user.id
        assert "scheduled_cleanup_at" in delete_payload["data"]

        db.refresh(test_user)
        db.refresh(subscription)

        assert test_user.is_deleted is True
        assert test_user.deleted_at is not None
        assert test_user.deletion_scheduled_at is not None
        assert test_user.refresh_token_jti is None
        assert subscription.is_active is False
        assert subscription.auto_renew is False

        hidden_response = client.get("/api/v1/users/me", headers=headers)
        assert hidden_response.status_code == 403
        assert "scheduled for deletion" in hidden_response.json()["detail"].lower()

    def test_admin_can_view_pending_account_deletions(
        self, client, db, test_admin_user
    ):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        pending_user = UserFactory.create(
            telegram_user_id=820001,
            referral_code="PH4PEND001",
            is_deleted=True,
            deleted_at=now - timedelta(days=1),
            deletion_scheduled_at=now + timedelta(days=29),
        )
        db.add(pending_user)
        db.commit()
        db.refresh(pending_user)

        headers = _auth_headers(test_admin_user.id)
        response = client.get("/api/v1/users/deletions/pending", headers=headers)
        assert response.status_code == 200

        payload = response.json()
        assert any(item["user_id"] == pending_user.id for item in payload)

    def test_cleanup_task_hard_deletes_only_expired_soft_deleted_users(
        self, db, monkeypatch
    ):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        expired_user = UserFactory.create(
            telegram_user_id=820010,
            referral_code="PH4CLN001",
            is_deleted=True,
            deleted_at=now - timedelta(days=31),
            deletion_scheduled_at=now - timedelta(minutes=10),
        )
        retained_user = UserFactory.create(
            telegram_user_id=820011,
            referral_code="PH4CLN002",
            is_deleted=True,
            deleted_at=now - timedelta(days=1),
            deletion_scheduled_at=now + timedelta(days=29),
        )
        db.add_all([expired_user, retained_user])
        db.commit()
        db.refresh(expired_user)
        db.refresh(retained_user)

        class SessionProxy:
            def __init__(self, session):
                self._session = session

            def __getattr__(self, item):
                return getattr(self._session, item)

            def close(self):
                # Keep fixture-managed session lifecycle intact.
                return None

        monkeypatch.setattr(compliance_tasks, "SessionLocal", lambda: SessionProxy(db))

        result = compliance_tasks.cleanup_soft_deleted_users()
        assert result["deleted"] == 1
        assert expired_user.id in result["user_ids"]

        assert db.query(User).filter(User.id == expired_user.id).first() is None
        assert db.query(User).filter(User.id == retained_user.id).first() is not None


@pytest.mark.integration
class TestPhase4AdminHealth:
    def test_admin_health_endpoint_returns_live_telemetry(
        self, client, test_admin_user
    ):
        admin_health_metrics.reset_for_tests(
            started_at=datetime.now(timezone.utc).replace(tzinfo=None)
            - timedelta(hours=1)
        )

        client.get("/")
        client.get("/health")

        headers = _auth_headers(test_admin_user.id)
        response = client.get("/api/v1/admin/system/health", headers=headers)
        assert response.status_code == 200

        payload = response.json()
        assert payload["api_uptime_hours"] > 0.0
        assert payload["total_requests_today"] >= 2
        assert payload["avg_response_time_ms"] >= 0.0
