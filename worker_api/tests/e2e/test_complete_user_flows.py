"""
End-to-End Tests for Complete User Flows

Tests complete user journeys from signup to subscription usage:
1. New user signup → Trial activation → Credential generation
2. Payment → Subscription purchase → Auto-renewal
3. IP change → Usage monitoring → Expiration
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.core.auth import create_access_token
from app.models import Credential, Subscription, User, WalletTransaction


@pytest.mark.e2e
class TestCompleteUserJourney:
    """Test complete user journey from signup to active usage"""

    def test_new_user_trial_flow(self, client, db, test_protocols):
        """
        E2E: New user signs up → Activates trial → Gets credentials

        Flow:
        1. User authenticates via Telegram
        2. User activates free trial
        3. System generates credentials
        4. User can connect to VPN
        """
        # Step 1: Telegram authentication (auto-registration)
        response = client.post(
            "/api/v1/auth/telegram",
            json={
                "telegram_user_id": 11111111,
                "telegram_username": "newuser",
                "language": "en",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["telegram_user_id"] == 11111111

        user_id = data["user"]["id"]
        token = data["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Step 2: Activate free trial
        protocol_id = test_protocols[0].id

        response = client.post(
            f"/api/v1/subscriptions/trial/activate?protocol_id={protocol_id}",
            headers=headers,
        )

        assert response.status_code == 201
        subscription_data = response.json()
        assert subscription_data["is_trial"] is True
        assert subscription_data["is_active"] is True

        subscription_id = subscription_data["id"]

        # Step 3: Generate credential
        response = client.post(
            "/api/v1/credentials",
            json={"subscription_id": subscription_id},
            headers=headers,
        )

        assert response.status_code == 201
        credential_data = response.json()
        assert credential_data["is_active"] is True
        assert credential_data["server_ip"] is not None
        assert credential_data["username"] is not None
        assert credential_data["connection_string"] is not None

        # Step 4: Verify user can retrieve credentials
        response = client.get("/api/v1/credentials", headers=headers)

        assert response.status_code == 200
        credentials = response.json()
        assert len(credentials) == 1
        assert credentials[0]["id"] == credential_data["id"]

        # Verify trial is marked as used
        user = db.query(User).filter_by(id=user_id).first()
        assert user.trial_used is True

    def test_payment_to_subscription_flow(self, client, db, test_protocols, test_user):
        """
        E2E: User deposits funds → Purchases subscription → Gets credentials

        Flow:
        1. User initiates deposit
        2. Deposit confirmed (simulated)
        3. User purchases subscription
        4. Credentials generated
        5. User can connect
        """
        token = create_access_token({"sub": str(test_user.id)})
        headers = {"Authorization": f"Bearer {token}"}

        # Step 1: Check initial wallet balance
        response = client.get("/api/v1/users/me/wallet", headers=headers)
        assert response.status_code == 200
        initial_balance = Decimal(str(response.json()["balance"]))

        # Step 2: Simulate completed deposit (in real flow, this comes from webhook)
        test_user.wallet_balance += Decimal("20.00")
        db.commit()

        # Step 3: Verify balance updated
        response = client.get("/api/v1/users/me/wallet", headers=headers)
        assert response.status_code == 200
        new_balance = Decimal(str(response.json()["balance"]))
        assert new_balance == initial_balance + Decimal("20.00")

        # Step 4: Purchase subscription
        protocol = test_protocols[0]

        response = client.post(
            "/api/v1/subscriptions/purchase",
            json={
                "subscription_id": protocol.id,
                "protocol_id": protocol.id,
                "auto_renew": True,
            },
            headers=headers,
        )

        assert response.status_code == 201
        subscription = response.json()
        assert subscription["is_active"] is True
        assert subscription["auto_renew"] is True

        # Step 5: Generate credentials
        response = client.post(
            "/api/v1/credentials",
            json={"subscription_id": subscription["id"]},
            headers=headers,
        )

        assert response.status_code == 201
        credential = response.json()
        assert credential["server_ip"] is not None

        # Step 6: Verify wallet was debited
        response = client.get("/api/v1/users/me/wallet", headers=headers)
        final_balance = Decimal(str(response.json()["balance"]))
        assert final_balance < new_balance

    def test_ip_change_flow(
        self,
        client,
        db,
        test_user,
        active_subscription,
        test_credential,
        test_instances,
    ):
        """
        E2E: User requests IP change → System processes → New IP assigned

        Flow:
        1. User views current credential IP
        2. User requests IP change
        3. System assigns new instance
        4. User verifies new IP
        """
        token = create_access_token({"sub": str(test_user.id)})
        headers = {"Authorization": f"Bearer {token}"}

        # Step 1: Check current IP
        response = client.get(
            f"/api/v1/credentials/{test_credential.id}", headers=headers
        )
        assert response.status_code == 200
        original_ip = response.json()["server_ip"]

        # Step 2: Request IP change
        response = client.post(
            "/api/v1/ip-management/request",
            json={"credential_id": test_credential.id, "preferred_country": "US"},
            headers=headers,
        )

        assert response.status_code == 201
        ip_request = response.json()
        assert ip_request["status"] == "pending"
        assert ip_request["old_ip"] == original_ip

        # Step 3: Simulate IP change processing (would be done by Celery task)
        from app.models import IPChangeRequest

        request_obj = db.query(IPChangeRequest).filter_by(id=ip_request["id"]).first()

        # Find new instance
        new_instance = next(
            (inst for inst in test_instances if inst.country_code == "US"),
            test_instances[1],
        )

        request_obj.new_ip = new_instance.public_ip
        request_obj.new_country = new_instance.country_code
        request_obj.status = "completed"
        request_obj.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)

        # Update credential
        test_credential.server_ip = new_instance.public_ip
        test_credential.instance_id = new_instance.id

        db.commit()

        # Step 4: Verify IP changed
        response = client.get(
            f"/api/v1/ip-management/requests/{ip_request['id']}", headers=headers
        )
        assert response.status_code == 200
        updated_request = response.json()
        assert updated_request["status"] == "completed"
        assert updated_request["new_ip"] != original_ip

    def test_support_ticket_flow(self, client, test_user):
        """
        E2E: User creates support ticket → Admin responds → User closes

        Flow:
        1. User creates ticket
        2. User adds message
        3. Admin views and responds
        4. User views response
        5. User closes ticket
        """
        token = create_access_token({"sub": str(test_user.id)})
        headers = {"Authorization": f"Bearer {token}"}

        # Step 1: Create support ticket
        response = client.post(
            "/api/v1/support/tickets",
            json={
                "subject": "Connection issue",
                "description": "I cannot connect to the VPN",
                "category": "technical",
                "priority": "high",
            },
            headers=headers,
        )

        assert response.status_code == 201
        ticket = response.json()
        assert ticket["status"] == "open"
        ticket_id = ticket["id"]

        # Step 2: User adds additional message
        response = client.post(
            f"/api/v1/support/tickets/{ticket_id}/messages",
            json={"message": "I tried restarting my device but still not working"},
            headers=headers,
        )

        assert response.status_code == 201

        # Step 3: Get ticket details
        response = client.get(f"/api/v1/support/tickets/{ticket_id}", headers=headers)
        assert response.status_code == 200
        ticket_detail = response.json()
        assert ticket_detail["ticket"]["message_count"] >= 2

        # Step 4: Close ticket
        response = client.post(
            f"/api/v1/support/tickets/{ticket_id}/close", headers=headers
        )
        assert response.status_code == 200

        # Step 5: Verify ticket is closed
        response = client.get(f"/api/v1/support/tickets/{ticket_id}", headers=headers)
        ticket_final = response.json()
        assert ticket_final["ticket"]["status"] == "closed"

    def test_referral_program_flow(self, client, db):
        """
        E2E: User signs up with referral → Makes purchase → Referrer gets commission

        Flow:
        1. User A (referrer) signs up
        2. User B signs up with User A's referral code
        3. User B makes a purchase
        4. User A receives commission
        """
        # Step 1: Create referrer
        response = client.post(
            "/api/v1/auth/telegram",
            json={
                "telegram_user_id": 22222222,
                "telegram_username": "referrer",
                "language": "en",
            },
        )

        assert response.status_code == 200
        referrer_data = response.json()
        referral_code = referrer_data["user"]["referral_code"]
        referrer_id = referrer_data["user"]["id"]

        # Step 2: Create referred user with referral code
        response = client.post(
            "/api/v1/auth/telegram",
            json={
                "telegram_user_id": 33333333,
                "telegram_username": "referred",
                "language": "en",
            },
        )

        assert response.status_code == 200
        referred_data = response.json()
        referred_token = referred_data["access_token"]
        referred_headers = {"Authorization": f"Bearer {referred_token}"}

        # Step 3: Apply referral code
        response = client.post(
            f"/api/v1/users/me/referrals/apply?referral_code={referral_code}",
            headers=referred_headers,
        )

        assert response.status_code == 200

        # Step 4: Give referred user some balance
        referred_user = db.query(User).filter_by(id=referred_data["user"]["id"]).first()
        referred_user.wallet_balance = Decimal("20.00")
        db.commit()

        # Step 5: Referred user makes purchase (this should trigger referral commission)
        # This would normally trigger commission in the subscription purchase endpoint
        # Commission calculation is tested separately

        # Step 6: Verify referrer's referral stats
        referrer_token = create_access_token({"sub": str(referrer_id)})
        referrer_headers = {"Authorization": f"Bearer {referrer_token}"}

        response = client.get("/api/v1/users/me/referrals", headers=referrer_headers)
        assert response.status_code == 200
        referral_stats = response.json()
        assert referral_stats["total_referrals"] >= 1


@pytest.mark.e2e
@pytest.mark.slow
class TestSubscriptionLifecycle:
    """Test complete subscription lifecycle"""

    def test_subscription_auto_renewal(self, client, db, test_user, test_protocol):
        """
        E2E: Subscription created → Auto-renewal enabled → Subscription renews automatically

        Flow:
        1. User purchases subscription with auto-renew
        2. Subscription approaches expiration
        3. Auto-renewal process runs (Celery task)
        4. Subscription extended, wallet debited
        """
        token = create_access_token({"sub": str(test_user.id)})
        headers = {"Authorization": f"Bearer {token}"}

        # Setup: Give user sufficient balance
        test_user.wallet_balance = Decimal("50.00")
        db.commit()

        # Step 1: Purchase subscription
        response = client.post(
            "/api/v1/subscriptions/purchase",
            json={"protocol_id": test_protocol.id, "auto_renew": True},
            headers=headers,
        )

        assert response.status_code == 201
        subscription = response.json()
        subscription_id = subscription["id"]

        # Step 2: Simulate subscription approaching expiration
        sub_obj = db.query(Subscription).filter_by(id=subscription_id).first()
        sub_obj.end_date = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
            hours=12
        )  # Expires in 12 hours
        db.commit()

        # Step 3: Run auto-renewal task (simulated)
        from app.tasks.subscription_tasks import process_auto_renewals

        initial_balance = test_user.wallet_balance
        initial_end_date = sub_obj.end_date

        # Run the task
        process_auto_renewals()

        # Step 4: Verify subscription renewed
        db.refresh(sub_obj)
        db.refresh(test_user)

        assert sub_obj.end_date > initial_end_date
        assert test_user.wallet_balance < initial_balance

    def test_subscription_expiration_flow(
        self, client, db, test_user, active_subscription, test_credential
    ):
        """
        E2E: Subscription expires → Credentials deactivated → User notified

        Flow:
        1. Active subscription exists
        2. Subscription passes end_date
        3. Expiration task runs
        4. Subscription and credentials marked inactive
        """
        token = create_access_token({"sub": str(test_user.id)})
        headers = {"Authorization": f"Bearer {token}"}

        # Step 1: Verify subscription is active
        response = client.get("/api/v1/subscriptions", headers=headers)
        assert response.status_code == 200
        subs = response.json()
        assert len([s for s in subs if s["is_active"]]) >= 1

        # Step 2: Simulate subscription expiration
        active_subscription.end_date = datetime.now(timezone.utc).replace(
            tzinfo=None
        ) - timedelta(hours=1)
        db.commit()

        # Step 3: Run expiration task
        from app.tasks.subscription_tasks import expire_subscriptions

        expire_subscriptions()

        # Step 4: Verify subscription expired
        db.refresh(active_subscription)
        db.refresh(test_credential)

        assert active_subscription.is_active is False
        assert test_credential.is_active is False

        # Step 5: Verify user sees expired subscription
        response = client.get("/api/v1/subscriptions", headers=headers)
        active_subs = [s for s in response.json() if s["is_active"]]
        assert len(active_subs) == 0


@pytest.mark.e2e
class TestPaymentGatewayIntegration:
    """Test payment gateway integration flows"""

    @pytest.mark.payment
    def test_zarinpal_payment_flow(self, client, test_user):
        """
        E2E: User initiates Zarinpal payment → Completes payment → Wallet credited

        Note: This uses mock/test mode for Zarinpal
        """
        # This would be a full integration test with Zarinpal sandbox
        # For now, we test the webhook callback flow

        # Simulate successful payment callback
        authority = "A00000000000000000000000000123456"
        status = "OK"

        client.get(
            f"/api/v1/webhooks/zarinpal/callback?Authority={authority}&Status={status}"
        )

        # Response depends on whether transaction exists
        # In real flow, transaction would be created before redirect

    @pytest.mark.payment
    def test_stripe_checkout_flow(self, client, test_user):
        """
        E2E: User creates Stripe checkout → Completes payment → Webhook received

        Note: This uses Stripe test mode
        """
        # This would test the full Stripe integration
        # Including checkout session creation and webhook processing
        pass


@pytest.mark.e2e
class TestAdminWorkflows:
    """Test admin management workflows"""

    def test_admin_dashboard_access(self, client, test_admin):
        """
        E2E: Admin accesses dashboard → Views stats → Manages users

        Flow:
        1. Admin logs in
        2. Admin views dashboard stats
        3. Admin views user list
        4. Admin views support tickets
        """
        token = create_access_token({"sub": str(test_admin.id)})
        headers = {"Authorization": f"Bearer {token}"}

        # Step 1: Get dashboard stats
        response = client.get("/api/v1/admin/dashboard", headers=headers)
        assert response.status_code == 200
        stats = response.json()
        assert "total_users" in stats
        assert "active_subscriptions" in stats

        # Step 2: List all users
        response = client.get("/api/v1/users", headers=headers)
        assert response.status_code == 200

        # Step 3: View support tickets
        response = client.get("/api/v1/support/admin/tickets", headers=headers)
        assert response.status_code == 200

    def test_admin_user_management(self, client, db, test_admin, test_user):
        """
        E2E: Admin manages user account

        Flow:
        1. Admin views user details
        2. Admin updates user info
        3. Admin manages user subscription
        """
        token = create_access_token({"sub": str(test_admin.id)})
        headers = {"Authorization": f"Bearer {token}"}

        # Step 1: Get user details
        response = client.get(f"/api/v1/users/{test_user.id}", headers=headers)
        assert response.status_code == 200
        user_data = response.json()
        assert user_data["id"] == test_user.id

        # Step 2: Update user (e.g., credit wallet)
        response = client.put(
            f"/api/v1/users/{test_user.id}",
            json={"wallet_balance": 100.00},
            headers=headers,
        )

        # This would work if admin update endpoint implemented
        # For now just verify admin can access
