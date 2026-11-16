"""
Unit tests for User model
"""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.models import User
from tests.factories import UserFactory


class TestUserModel:
    """Test cases for User model"""

    def test_create_user(self, db):
        """Test creating a basic user"""
        user = UserFactory.create(
            telegram_user_id=12345,
            telegram_username="test_user",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        assert user.id is not None
        assert user.telegram_user_id == 12345
        assert user.telegram_username == "test_user"
        assert user.language == "en"
        assert user.is_admin is False
        assert user.wallet_balance == Decimal("0.00")
        assert user.created_at is not None

    def test_user_unique_telegram_id(self, db):
        """Test that telegram_user_id must be unique"""
        user1 = UserFactory.create(telegram_user_id=99999)
        db.add(user1)
        db.commit()

        user2 = UserFactory.create(telegram_user_id=99999)
        db.add(user2)

        with pytest.raises(Exception):  # IntegrityError
            db.commit()

    def test_user_unique_referral_code(self, db):
        """Test that referral_code must be unique"""
        user1 = UserFactory.create(referral_code="UNIQUE123")
        db.add(user1)
        db.commit()

        user2 = UserFactory.create(telegram_user_id=88888, referral_code="UNIQUE123")
        db.add(user2)

        with pytest.raises(Exception):  # IntegrityError
            db.commit()

    def test_user_with_trial(self, db):
        """Test creating user with trial"""
        trial_start = datetime.now()
        trial_end = trial_start + timedelta(days=3)

        user = UserFactory.create_with_trial(
            telegram_user_id=55555,
            trial_started_at=trial_start,
            trial_expires_at=trial_end,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        assert user.trial_used is True
        assert user.trial_started_at is not None
        assert user.trial_expires_at is not None
        assert (user.trial_expires_at - user.trial_started_at).days == 3

    def test_user_admin(self, db):
        """Test creating admin user"""
        user = UserFactory.create_admin(telegram_user_id=11111)
        db.add(user)
        db.commit()
        db.refresh(user)

        assert user.is_admin is True

    def test_user_with_wallet_balance(self, db):
        """Test user with wallet balance"""
        user = UserFactory.create_with_wallet_balance(
            telegram_user_id=22222, balance=Decimal("150.50")
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        assert user.wallet_balance == Decimal("150.50")

    def test_user_referral_system(self, db):
        """Test referral system fields"""
        referrer = UserFactory.create(
            telegram_user_id=33333,
            referral_code="REF33333",
        )
        db.add(referrer)
        db.commit()
        db.refresh(referrer)

        referred = UserFactory.create(
            telegram_user_id=44444,
            referred_by=referrer.id,
        )
        db.add(referred)
        db.commit()
        db.refresh(referred)

        assert referred.referred_by == referrer.id
        assert referrer.referral_code is not None

    def test_user_referral_earnings(self, db):
        """Test referral earnings tracking"""
        user = UserFactory.create_with_referral(
            telegram_user_id=66666,
            referral_tier="gold",
            total_referrals=10,
            referral_earnings_usd=Decimal("100.00"),
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        assert user.referral_tier == "gold"
        assert user.total_referrals == 10
        assert user.referral_earnings_usd == Decimal("100.00")

    def test_user_language_support(self, db):
        """Test multi-language support"""
        languages = ["en", "fa", "ar", "ru", "zh"]

        for lang in languages:
            user = UserFactory.create(
                telegram_user_id=70000 + languages.index(lang),
                language=lang,
            )
            db.add(user)

        db.commit()

        users = db.query(User).filter(User.telegram_user_id >= 70000).all()
        assert len(users) == 5
        assert set(u.language for u in users) == set(languages)

    def test_user_default_values(self, db):
        """Test that default values are set correctly"""
        user = User(
            telegram_user_id=88888,
            telegram_username="defaults_test",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        assert user.referral_tier == "bronze"
        assert user.total_referrals == 0
        assert user.referral_earnings_usd == Decimal("0.00")
        assert user.wallet_balance == Decimal("0.00")
        assert user.trial_used is False
        assert user.language == "en"
        assert user.is_admin is False

    def test_user_repr(self, db):
        """Test User __repr__ method"""
        user = UserFactory.create(
            telegram_user_id=99999,
            telegram_username="repr_test",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        repr_str = repr(user)
        assert "User" in repr_str
        assert "99999" in repr_str
        assert "repr_test" in repr_str

    def test_user_batch_creation(self, db):
        """Test creating multiple users"""
        users = UserFactory.create_batch(5)
        for user in users:
            db.add(user)
        db.commit()

        count = db.query(User).filter(User.telegram_user_id >= 100000).count()
        assert count == 5

    def test_user_optional_fields(self, db):
        """Test that optional fields can be None"""
        user = UserFactory.create(
            telegram_user_id=77777,
            email=None,
            flux_wallet_address=None,
            referred_by=None,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        assert user.email is None
        assert user.flux_wallet_address is None
        assert user.referred_by is None

    def test_user_with_email(self, db):
        """Test user with email"""
        user = UserFactory.create(
            telegram_user_id=55555,
            email="test@example.com",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        assert user.email == "test@example.com"

    def test_user_with_flux_wallet(self, db):
        """Test user with Flux wallet address"""
        user = UserFactory.create(
            telegram_user_id=66666,
            flux_wallet_address="t1abc123def456ghi789",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        assert user.flux_wallet_address == "t1abc123def456ghi789"
