"""
Integration Tests for API Endpoints.
"""
from decimal import Decimal

import pytest

from app.core.auth import create_access_token


@pytest.mark.integration
class TestAuthenticationEndpoints:
    """Test authentication API endpoints"""

    def test_telegram_auth_creates_new_user(self, client, db, internal_api_headers):
        """Test Telegram authentication with auto-registration"""
        response = client.post(
            "/api/v1/auth/telegram",
            json={
                "telegram_user_id": 99999999,
                "telegram_username": "newtestuser",
                "language_code": "en",
            },
            headers=internal_api_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["telegram_user_id"] == 99999999
        assert data["user"]["referral_code"] is not None

    def test_token_refresh(self, client, db, test_user):
        """Test JWT token refresh"""
        from app.core.auth.jwt import create_refresh_token

        refresh_token = create_refresh_token(test_user.id, db)
        response = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data

    def test_verify_token(self, client, test_user):
        """Test token verification endpoint"""
        token = create_access_token({"sub": str(test_user.id)})
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/api/v1/auth/verify", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_user.id


@pytest.mark.integration
class TestUserEndpoints:
    """Test user management endpoints"""

    def test_get_current_user_profile(self, client, test_user):
        """Test retrieving current user profile"""
        token = create_access_token({"sub": str(test_user.id)})
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/api/v1/users/me", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_user.id
        assert data["telegram_username"] == test_user.telegram_username

    def test_update_current_user(self, client, test_user):
        """Test updating user profile"""
        token = create_access_token({"sub": str(test_user.id)})
        headers = {"Authorization": f"Bearer {token}"}

        response = client.put(
            "/api/v1/users/me", json={"language": "fa"}, headers=headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["language"] == "fa"

    def test_get_wallet_balance(self, client, test_user):
        """Test retrieving wallet balance"""
        token = create_access_token({"sub": str(test_user.id)})
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/api/v1/users/me/wallet", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert "wallet_balance" in data
        assert Decimal(str(data["wallet_balance"])) == test_user.wallet_balance

    def test_get_referral_stats(self, client, test_user):
        """Test retrieving referral statistics"""
        token = create_access_token({"sub": str(test_user.id)})
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/api/v1/users/me/referrals", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert "total_referrals" in data
        assert "referral_tier" in data


@pytest.mark.integration
class TestSubscriptionEndpoints:
    """Test subscription management endpoints"""

    def test_list_subscription_plans(self, client, test_protocols):
        """Test listing available subscription plans"""
        response = client.get("/api/v1/subscriptions/plans")

        assert response.status_code == 200
        plans = response.json()
        assert len(plans) >= 3  # VLESS, SSH, Clash

    def test_get_subscription_plan_details(self, client, test_protocol):
        """Test getting specific plan details"""
        response = client.get(f"/api/v1/subscriptions/plans/{test_protocol.id}")

        assert response.status_code == 200
        plan = response.json()
        assert plan["id"] == test_protocol.id
        assert plan["name"] == test_protocol.name

    def test_purchase_subscription(
        self, client, db, test_user, subscription_plan_factory
    ):
        """Test purchasing a subscription"""
        token = create_access_token({"sub": str(test_user.id)})
        headers = {"Authorization": f"Bearer {token}"}

        plan = subscription_plan_factory.create(
            name="API Endpoint Plan",
            tier="silver",
            duration_months=1,
            price_usd=Decimal("9.99"),
            max_connections=3,
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)

        # Give user sufficient balance
        test_user.wallet_balance = Decimal("20.00")
        db.commit()

        response = client.post(
            "/api/v1/subscriptions/purchase",
            json={"plan_id": plan.id, "auto_renew": True},
            headers=headers,
        )

        assert response.status_code == 201
        subscription = response.json()
        assert subscription["plan_id"] == plan.id
        assert subscription["status"] == "active"

    def test_list_user_subscriptions(self, client, test_user, active_subscription):
        """Test listing user's subscriptions"""
        token = create_access_token({"sub": str(test_user.id)})
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/api/v1/subscriptions", headers=headers)

        assert response.status_code == 200
        subscriptions = response.json()
        assert len(subscriptions) >= 1

    def test_activate_trial(self, client, db, test_user, test_protocol):
        """Test trial activation"""
        token = create_access_token({"sub": str(test_user.id)})
        headers = {"Authorization": f"Bearer {token}"}

        # Ensure user hasn't used trial
        test_user.trial_used = False
        db.commit()

        response = client.post(
            f"/api/v1/subscriptions/trial/activate?protocol_id={test_protocol.id}",
            headers=headers,
        )

        assert response.status_code == 201
        trial = response.json()
        assert trial["status"] == "active"
        assert trial["auto_renew"] is False


@pytest.mark.integration
class TestCredentialEndpoints:
    """Test credential generation endpoints"""

    def test_generate_credential(
        self, client, test_user, active_subscription, test_instance
    ):
        """Test credential generation"""
        token = create_access_token({"sub": str(test_user.id)})
        headers = {"Authorization": f"Bearer {token}"}

        response = client.post(
            "/api/v1/credentials",
            json={"subscription_id": active_subscription.id},
            headers=headers,
        )

        assert response.status_code == 201
        credential = response.json()
        assert credential["subscription_id"] == active_subscription.id
        assert credential["server"] is not None
        assert credential["credential_data"] is not None

    def test_list_credentials(self, client, test_user, test_credential):
        """Test listing user credentials"""
        token = create_access_token({"sub": str(test_user.id)})
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/api/v1/credentials", headers=headers)

        assert response.status_code == 200
        credentials = response.json()
        assert len(credentials) >= 1

    def test_get_credential_config(self, client, test_user, test_credential):
        """Test getting credential configuration file"""
        token = create_access_token({"sub": str(test_user.id)})
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get(
            f"/api/v1/credentials/{test_credential.id}/config/url", headers=headers
        )

        assert response.status_code == 200
        config = response.json()
        assert "config_content" in config


@pytest.mark.integration
class TestSupportEndpoints:
    """Test support ticket endpoints"""

    def test_create_support_ticket(self, client, test_user):
        """Test creating a support ticket"""
        token = create_access_token({"sub": str(test_user.id)})
        headers = {"Authorization": f"Bearer {token}"}

        response = client.post(
            "/api/v1/support/tickets",
            json={
                "subject": "Test issue",
                "description": "This is a test support ticket",
                "category": "technical",
                "priority": "medium",
            },
            headers=headers,
        )

        assert response.status_code == 201
        ticket = response.json()
        assert ticket["subject"] == "Test issue"
        assert ticket["status"] == "open"

    def test_list_user_tickets(self, client, test_user):
        """Test listing user's tickets"""
        token = create_access_token({"sub": str(test_user.id)})
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/api/v1/support/tickets", headers=headers)

        assert response.status_code == 200
        tickets = response.json()
        assert isinstance(tickets, list)

    def test_add_ticket_message(self, client, db, test_user):
        """Test adding a message to ticket"""
        token = create_access_token({"sub": str(test_user.id)})
        headers = {"Authorization": f"Bearer {token}"}

        # Create ticket first
        from app.models import SupportTicket

        ticket = SupportTicket(
            user_id=test_user.id,
            ticket_number="20240101-12345",
            subject="Test ticket",
            description="Test",
            category="technical",
            priority="medium",
            status="open",
        )

        db.add(ticket)
        db.commit()

        response = client.post(
            f"/api/v1/support/tickets/{ticket.id}/messages",
            json={"message": "Additional information"},
            headers=headers,
        )

        assert response.status_code == 201


@pytest.mark.integration
class TestIPManagementEndpoints:
    """Test IP change management endpoints"""

    def test_request_ip_change(self, client, test_user, test_credential):
        """Test requesting IP change"""
        token = create_access_token({"sub": str(test_user.id)})
        headers = {"Authorization": f"Bearer {token}"}

        response = client.post(
            "/api/v1/ip-management/request",
            json={"credential_id": test_credential.id, "preferred_country": "US"},
            headers=headers,
        )

        # Might fail if no instances available
        assert response.status_code in [201, 503]

    def test_get_ip_change_stats(self, client, test_user):
        """Test getting IP change statistics"""
        token = create_access_token({"sub": str(test_user.id)})
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/api/v1/ip-management/stats", headers=headers)

        assert response.status_code == 200
        stats = response.json()
        assert "total_ip_changes_allowed" in stats

    def test_list_available_countries(self, client, test_instances):
        """Test listing available countries"""
        response = client.get("/api/v1/ip-management/countries")

        assert response.status_code == 200
        countries = response.json()
        assert isinstance(countries, list)


@pytest.mark.integration
class TestAdminEndpoints:
    """Test admin dashboard endpoints"""

    def test_get_dashboard_stats(self, client, test_admin):
        """Test getting dashboard statistics"""
        token = create_access_token({"sub": str(test_admin.id)})
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/api/v1/admin/dashboard", headers=headers)

        assert response.status_code == 200
        stats = response.json()
        assert "total_users" in stats
        assert "active_subscriptions" in stats
        assert "total_revenue" in stats

    def test_get_revenue_analytics(self, client, test_admin):
        """Test getting revenue analytics"""
        token = create_access_token({"sub": str(test_admin.id)})
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get(
            "/api/v1/admin/analytics/revenue?period=daily&days=30", headers=headers
        )

        assert response.status_code == 200
        analytics = response.json()
        assert "total_revenue" in analytics

    def test_list_all_tickets_admin(self, client, test_admin):
        """Test admin viewing all tickets"""
        token = create_access_token({"sub": str(test_admin.id)})
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/api/v1/support/admin/tickets", headers=headers)

        assert response.status_code == 200
        tickets = response.json()
        assert isinstance(tickets, list)

    def test_non_admin_cannot_access_admin_endpoints(self, client, test_user):
        """Test that non-admin users cannot access admin endpoints"""
        token = create_access_token({"sub": str(test_user.id)})
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/api/v1/admin/dashboard", headers=headers)

        assert response.status_code == 403  # Forbidden


@pytest.mark.integration
class TestHealthEndpoints:
    """Test health check endpoints"""

    def test_root_endpoint(self, client):
        """Test root endpoint"""
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert "service" in data
        assert data["status"] == "running"

    def test_health_check(self, client):
        """Test basic health check"""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_database_health(self, client):
        """Test database health check"""
        response = client.get("/health/db")

        # Might fail if DB connection issue
        assert response.status_code in [200, 503]

    def test_redis_health(self, client):
        """Test Redis health check"""
        response = client.get("/health/redis")

        # Might fail if Redis not available
        assert response.status_code in [200, 503]
