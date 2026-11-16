"""
Subscription-related model factories for testing
"""

from datetime import datetime, timedelta
from decimal import Decimal

from app.models import Protocol, Subscription, SubscriptionPlan


class ProtocolFactory:
    """Factory for creating Protocol instances"""

    @staticmethod
    def create(**kwargs):
        """Create a Protocol instance with default values"""
        defaults = {
            "name": "vless",
            "slug": None,
            "display_name": "VLESS",
            "description": "VLESS protocol for secure connections",
            "flux_app_name": "fluxvpn-vless",
            "default_port": 443,
            "is_active": True,
        }
        slug_explicitly_set = "slug" in kwargs
        flux_app_name_explicitly_set = "flux_app_name" in kwargs
        defaults.update(kwargs)

        if not slug_explicitly_set or not defaults.get("slug"):
            defaults["slug"] = str(defaults["name"]).lower().replace(" ", "-")

        if not flux_app_name_explicitly_set or not defaults.get("flux_app_name"):
            defaults["flux_app_name"] = f"fluxvpn-{defaults['slug']}"

        return Protocol(**defaults)

    @staticmethod
    def create_vless(**kwargs):
        """Create VLESS protocol"""
        defaults = {
            "name": "vless",
            "display_name": "VLESS",
            "flux_app_name": "fluxvpn-vless",
            "default_port": 443,
        }
        defaults.update(kwargs)
        return ProtocolFactory.create(**defaults)

    @staticmethod
    def create_ssh(**kwargs):
        """Create SSH protocol"""
        defaults = {
            "name": "ssh",
            "display_name": "SSH",
            "flux_app_name": "fluxvpn-ssh",
            "default_port": 22,
        }
        defaults.update(kwargs)
        return ProtocolFactory.create(**defaults)

    @staticmethod
    def create_clash(**kwargs):
        """Create Clash protocol"""
        defaults = {
            "name": "clash",
            "display_name": "Clash",
            "flux_app_name": "fluxvpn-clash",
            "default_port": 7890,
        }
        defaults.update(kwargs)
        return ProtocolFactory.create(**defaults)


class SubscriptionPlanFactory:
    """Factory for creating SubscriptionPlan instances"""

    @staticmethod
    def create(**kwargs):
        """Create a SubscriptionPlan instance with default values"""
        defaults = {
            "name": "Bronze Monthly",
            "tier": "bronze",
            "duration_months": 1,
            "price_usd": Decimal("5.00"),
            "max_protocols": 1,
            "max_connections": 1,
            "data_limit_gb": 100,
            "daily_ip_changes": 1,
        }
        defaults.update(kwargs)
        return SubscriptionPlan(**defaults)

    @staticmethod
    def create_trial(**kwargs):
        """Create trial plan"""
        defaults = {
            "name": "3-Day Trial",
            "tier": "bronze",
            "duration_months": 0,
            "price_usd": Decimal("0.00"),
            "max_protocols": 1,
            "max_connections": 1,
            "data_limit_gb": 10,
            "daily_ip_changes": 1,
        }
        defaults.update(kwargs)
        return SubscriptionPlanFactory.create(**defaults)

    @staticmethod
    def create_bronze_monthly(**kwargs):
        """Create Bronze monthly plan"""
        defaults = {
            "name": "Bronze Monthly",
            "tier": "bronze",
            "duration_months": 1,
            "price_usd": Decimal("5.00"),
        }
        defaults.update(kwargs)
        return SubscriptionPlanFactory.create(**defaults)

    @staticmethod
    def create_silver_monthly(**kwargs):
        """Create Silver monthly plan"""
        defaults = {
            "name": "Silver Monthly",
            "tier": "silver",
            "duration_months": 1,
            "price_usd": Decimal("10.00"),
            "max_protocols": 2,
            "max_connections": 2,
            "data_limit_gb": 200,
            "daily_ip_changes": 3,
        }
        defaults.update(kwargs)
        return SubscriptionPlanFactory.create(**defaults)

    @staticmethod
    def create_gold_yearly(**kwargs):
        """Create Gold yearly plan"""
        defaults = {
            "name": "Gold Yearly",
            "tier": "gold",
            "duration_months": 12,
            "price_usd": Decimal("200.00"),
            "max_protocols": 3,
            "max_connections": 5,
            "data_limit_gb": None,  # Unlimited
            "daily_ip_changes": 10,
        }
        defaults.update(kwargs)
        return SubscriptionPlanFactory.create(**defaults)


class SubscriptionFactory:
    """Factory for creating Subscription instances"""

    @staticmethod
    def create(user_id: int, plan_id: int, **kwargs):
        """Create a Subscription instance with default values"""
        now = datetime.now()
        defaults = {
            "user_id": user_id,
            "plan_id": plan_id,
            "status": "active",
            "started_at": now,
            "expires_at": now + timedelta(days=30),
            "auto_renew": False,
        }
        defaults.update(kwargs)
        return Subscription(**defaults)

    @staticmethod
    def create_active(user_id: int, plan_id: int, **kwargs):
        """Create an active subscription"""
        defaults = {
            "status": "active",
            "expires_at": datetime.now() + timedelta(days=30),
        }
        defaults.update(kwargs)
        return SubscriptionFactory.create(user_id, plan_id, **defaults)

    @staticmethod
    def create_expired(user_id: int, plan_id: int, **kwargs):
        """Create an expired subscription"""
        defaults = {
            "status": "expired",
            "expires_at": datetime.now() - timedelta(days=1),
        }
        defaults.update(kwargs)
        return SubscriptionFactory.create(user_id, plan_id, **defaults)

    @staticmethod
    def create_with_auto_renew(user_id: int, plan_id: int, **kwargs):
        """Create subscription with auto-renewal enabled"""
        defaults = {
            "auto_renew": True,
        }
        defaults.update(kwargs)
        return SubscriptionFactory.create(user_id, plan_id, **defaults)

    @staticmethod
    def create_expiring_soon(user_id: int, plan_id: int, days: int = 2, **kwargs):
        """Create subscription expiring in N days"""
        defaults = {
            "status": "active",
            "expires_at": datetime.now() + timedelta(days=days),
        }
        defaults.update(kwargs)
        return SubscriptionFactory.create(user_id, plan_id, **defaults)
