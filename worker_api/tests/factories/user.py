"""
User model factory for testing
"""

from datetime import datetime, timedelta
from decimal import Decimal

from app.models import User


class UserFactory:
    """Factory for creating User instances"""

    @staticmethod
    def create(**kwargs):
        """
        Create a User instance with default values
        Override any field by passing it as a keyword argument
        """
        defaults = {
            "telegram_user_id": 123456789,
            "telegram_username": "test_user",
            "email": None,
            "flux_wallet_address": None,
            "referral_code": f"REF{datetime.now().timestamp()}",
            "referred_by": None,
            "referral_tier": "bronze",
            "total_referrals": 0,
            "referral_earnings_usd": Decimal("0.00"),
            "wallet_balance": Decimal("0.00"),
            "trial_used": False,
            "trial_started_at": None,
            "trial_expires_at": None,
            "language": "en",
            "is_admin": False,
        }
        defaults.update(kwargs)
        return User(**defaults)

    @staticmethod
    def create_with_trial(**kwargs):
        """Create a user with active trial"""
        trial_start = datetime.now()
        trial_end = trial_start + timedelta(days=3)

        defaults = {
            "trial_used": True,
            "trial_started_at": trial_start,
            "trial_expires_at": trial_end,
        }
        defaults.update(kwargs)
        return UserFactory.create(**defaults)

    @staticmethod
    def create_admin(**kwargs):
        """Create an admin user"""
        defaults = {
            "is_admin": True,
            "telegram_username": "admin_user",
        }
        defaults.update(kwargs)
        return UserFactory.create(**defaults)

    @staticmethod
    def create_with_referral(**kwargs):
        """Create a user with referral earnings"""
        defaults = {
            "referral_tier": "silver",
            "total_referrals": 5,
            "referral_earnings_usd": Decimal("25.00"),
        }
        defaults.update(kwargs)
        return UserFactory.create(**defaults)

    @staticmethod
    def create_with_wallet_balance(balance: Decimal = Decimal("100.00"), **kwargs):
        """Create a user with wallet balance"""
        defaults = {
            "wallet_balance": balance,
        }
        defaults.update(kwargs)
        return UserFactory.create(**defaults)

    @staticmethod
    def create_batch(count: int, **kwargs):
        """Create multiple users"""
        users = []
        for i in range(count):
            user_kwargs = kwargs.copy()
            user_kwargs["telegram_user_id"] = 100000 + i
            user_kwargs["telegram_username"] = f"user_{i}"
            user_kwargs["referral_code"] = f"REF{100000 + i}"
            users.append(UserFactory.create(**user_kwargs))
        return users
