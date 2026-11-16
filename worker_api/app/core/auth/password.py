"""
Password hashing and verification utilities
"""

import logging

import bcrypt

from app.core.crypto import encrypt_token

logger = logging.getLogger(__name__)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )
    except Exception as e:
        logger.error(f"Password verification error: {str(e)}")
        return False


def set_password(user, plaintext: str) -> None:
    """Set both password_hash (for verification) and password_enc (for display).

    Must be called on every password write to maintain the dual-storage
    invariant. Migration-safe: existing users with NULL password_enc simply
    don't have plaintext available for display until next reset.
    """
    user.password_hash = hash_password(plaintext)
    user.password_enc = encrypt_token(plaintext)
