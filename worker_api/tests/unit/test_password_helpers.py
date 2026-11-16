"""Tests for set_password helper (dual hash + encrypted plaintext write)."""
from unittest.mock import MagicMock

import pytest

from app.core.auth.password import set_password, verify_password


@pytest.fixture(autouse=True)
def _fluxvpn_secret_key(monkeypatch):
    """encrypt_token/decrypt_token (app.core.crypto) derive their AES key from
    settings.FLUXVPN_SECRET_KEY. The test .env doesn't set it (defaults to
    None), so pin a per-test value here instead of stubbing app.core.config
    at import time.
    """
    from app.core.config import settings

    monkeypatch.setattr(
        settings, "FLUXVPN_SECRET_KEY", "test-secret-key-for-tests-only-32bytes"
    )


def test_set_password_writes_both_hash_and_enc():
    """set_password should populate both password_hash and password_enc."""
    user = MagicMock()
    plaintext = "TestPass123"

    set_password(user, plaintext)

    # hash should be set (not equal to plaintext)
    assert user.password_hash is not None
    assert user.password_hash != plaintext

    # enc should be set and decryptable back to plaintext
    assert user.password_enc is not None
    from app.core.crypto import decrypt_token

    assert decrypt_token(user.password_enc) == plaintext


def test_set_password_different_plaintexts_yield_different_enc():
    """Each plaintext should produce unique ciphertext (nonce varies)."""
    u1 = MagicMock()
    u2 = MagicMock()
    set_password(u1, "password1")
    set_password(u2, "password2")
    assert u1.password_enc != u2.password_enc


def test_verify_password_still_works_against_hash():
    """verify_password should still accept the original plaintext."""
    user = MagicMock()
    plaintext = "MyPortal77"
    set_password(user, plaintext)
    assert verify_password(plaintext, user.password_hash) is True
    assert verify_password("wrong", user.password_hash) is False
