"""Shared referral-code minting used by paid activation and free-config enrollment."""

import secrets

from app.models.admin_users import AdminUser


def ensure_referral_code(user: AdminUser) -> str:
    """Assign a referral code to ``user`` if it lacks one; return the code.

    Does not commit — the caller owns the transaction.
    """
    if not user.referral_code:
        base = (user.username or f"user{user.id}").upper().replace("-", "_")[:20]
        user.referral_code = f"{base}-{secrets.token_hex(2)}"
    return user.referral_code
