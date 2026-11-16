"""
Unit tests for JWT refresh token system
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.core.auth.jwt import create_refresh_token, verify_refresh_token
from app.models import User
from tests.factories import UserFactory


class TestCreateRefreshToken:
    """Test cases for create_refresh_token()"""

    def test_creates_token_string(self, db):
        """Test that a token string is returned"""
        user = UserFactory.create(telegram_user_id=10001)
        db.add(user)
        db.commit()
        db.refresh(user)

        token = create_refresh_token(user.id, db)

        assert isinstance(token, str)
        assert len(token) > 0

    def test_stores_jti_in_database(self, db):
        """Test that JTI is stored on the user record"""
        user = UserFactory.create(telegram_user_id=10002)
        db.add(user)
        db.commit()
        db.refresh(user)

        assert user.refresh_token_jti is None

        create_refresh_token(user.id, db)
        db.refresh(user)

        assert user.refresh_token_jti is not None

    def test_stores_expiration_in_database(self, db):
        """Test that expiration timestamp is stored"""
        user = UserFactory.create(telegram_user_id=10003)
        db.add(user)
        db.commit()
        db.refresh(user)

        create_refresh_token(user.id, db)
        db.refresh(user)

        assert user.refresh_token_expires_at is not None
        # Should be ~30 days in the future
        delta = user.refresh_token_expires_at - datetime.now(timezone.utc).replace(
            tzinfo=None
        )
        assert 29 <= delta.days <= 30

    def test_rotation_invalidates_old_jti(self, db):
        """Test that creating a new token overwrites the old JTI"""
        user = UserFactory.create(telegram_user_id=10004)
        db.add(user)
        db.commit()
        db.refresh(user)

        create_refresh_token(user.id, db)
        db.refresh(user)
        old_jti = user.refresh_token_jti

        create_refresh_token(user.id, db)
        db.refresh(user)
        new_jti = user.refresh_token_jti

        assert old_jti != new_jti

    def test_nonexistent_user_returns_token(self, db):
        """Test behavior with nonexistent user ID (no crash)"""
        # Should still return a token even if user not found
        token = create_refresh_token(999999, db)
        assert isinstance(token, str)


class TestVerifyRefreshToken:
    """Test cases for verify_refresh_token()"""

    def test_valid_token_returns_user_id(self, db):
        """Test that a valid refresh token returns the user ID"""
        user = UserFactory.create(telegram_user_id=20001)
        db.add(user)
        db.commit()
        db.refresh(user)

        token = create_refresh_token(user.id, db)
        result = verify_refresh_token(token, db)

        assert result == user.id

    def test_invalid_token_string_returns_none(self, db):
        """Test that garbage token returns None"""
        result = verify_refresh_token("invalid.token.string", db)
        assert result is None

    def test_expired_token_returns_none(self, db):
        """Test that an expired token returns None"""
        user = UserFactory.create(telegram_user_id=20002)
        db.add(user)
        db.commit()
        db.refresh(user)

        token = create_refresh_token(user.id, db)

        # Manually set expiration to the past
        user.refresh_token_expires_at = datetime.now(timezone.utc).replace(
            tzinfo=None
        ) - timedelta(hours=1)
        db.commit()

        result = verify_refresh_token(token, db)
        assert result is None

    def test_revoked_token_returns_none(self, db):
        """Test that a revoked (JTI cleared) token returns None"""
        user = UserFactory.create(telegram_user_id=20003)
        db.add(user)
        db.commit()
        db.refresh(user)

        token = create_refresh_token(user.id, db)

        # Simulate revocation by clearing JTI
        user.refresh_token_jti = None
        db.commit()

        result = verify_refresh_token(token, db)
        assert result is None

    def test_rotated_token_invalidates_old(self, db):
        """Test that after rotation, old token is invalid"""
        user = UserFactory.create(telegram_user_id=20004)
        db.add(user)
        db.commit()
        db.refresh(user)

        old_token = create_refresh_token(user.id, db)
        new_token = create_refresh_token(user.id, db)

        # Old token should be invalid (JTI changed)
        assert verify_refresh_token(old_token, db) is None
        # New token should be valid
        assert verify_refresh_token(new_token, db) == user.id

    def test_access_token_rejected_as_refresh(self, db):
        """Test that an access token is rejected when used as refresh"""
        from app.core.auth.jwt import create_access_token

        access_token = create_access_token({"sub": "1"})
        result = verify_refresh_token(access_token, db)
        assert result is None
