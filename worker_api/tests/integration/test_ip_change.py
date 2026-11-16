"""
Integration tests for IP change request flow.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.core.auth.jwt import create_access_token
from app.models import IPChangeRequest
from app.tasks.ip_tasks import process_ip_change


class _SessionProxy:
    def __init__(self, session):
        self._session = session

    def __getattr__(self, item):
        return getattr(self._session, item)

    def close(self):
        return None


class TestIPChangeRequestFlow:
    def test_create_ip_change_request(self, client, test_user, test_credential):
        token = create_access_token({"sub": str(test_user.id)})

        with patch("app.api.v1.endpoints.ip_management.process_ip_change") as mock_task:
            mock_task.delay.return_value = MagicMock(id="mock-task-id")

            response = client.post(
                "/api/v1/ip-management/request",
                json={
                    "credential_id": test_credential.id,
                    "preferred_country": "US",
                    "reason": "Testing IP change",
                },
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "pending"
        assert data["credential_id"] == test_credential.id

    def test_ip_change_task_completes_successfully(
        self,
        db,
        test_user,
        test_protocol,
        active_subscription,
        test_credential,
        test_instances,
    ):
        old_instance = test_instances[0]
        new_instance = test_instances[1]

        # Ensure credential starts on old instance.
        data = dict(test_credential.credential_data or {})
        data["instance_id"] = old_instance.id
        data["server"] = str(old_instance.ip_address)
        data["server_ip"] = str(old_instance.ip_address)
        data["is_active"] = True
        test_credential.credential_data = data
        db.commit()

        ip_request = IPChangeRequest(
            user_id=test_user.id,
            subscription_id=active_subscription.id,
            protocol_id=test_protocol.id,
            old_instance_id=old_instance.id,
            requested_country_code=new_instance.country_code,
            status="pending",
        )
        db.add(ip_request)
        db.commit()
        db.refresh(ip_request)

        with patch("app.tasks.ip_tasks.SessionLocal", return_value=_SessionProxy(db)):
            result = process_ip_change(ip_request.id)

        db.refresh(ip_request)
        db.refresh(test_credential)

        assert isinstance(result, dict)
        assert result["success"] is True
        assert ip_request.status == "completed"
        assert ip_request.new_instance_id == new_instance.id
        assert test_credential.credential_data["instance_id"] == new_instance.id

    def test_ip_change_rate_limit(
        self, client, db, test_user, test_protocol, active_subscription, test_credential
    ):
        token = create_access_token({"sub": str(test_user.id)})
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        for _ in range(3):
            db.add(
                IPChangeRequest(
                    user_id=test_user.id,
                    subscription_id=active_subscription.id,
                    protocol_id=test_protocol.id,
                    status="completed",
                    created_at=now - timedelta(days=5),
                    processed_at=now - timedelta(days=5),
                )
            )
        db.commit()

        with patch("app.api.v1.endpoints.ip_management.process_ip_change") as mock_task:
            mock_task.delay.return_value = MagicMock(id="mock-task-id")
            response = client.post(
                "/api/v1/ip-management/request",
                json={
                    "credential_id": test_credential.id,
                    "preferred_country": "US",
                    "reason": "Rate limit test",
                },
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 429
