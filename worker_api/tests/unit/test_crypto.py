"""Tests for AES-GCM bot-token encrypt/decrypt."""

import os

import pytest

# Ensure FLUXVPN_SECRET_KEY is set before any import of app.core modules.
# Uses setdefault so CI can override with a real key if needed.
_TEST_SECRET_KEY = "test-secret-key-for-crypto-tests"
os.environ.setdefault("FLUXVPN_SECRET_KEY", _TEST_SECRET_KEY)


@pytest.fixture(autouse=True)
def _ensure_secret_key(monkeypatch):
    """Ensure settings.FLUXVPN_SECRET_KEY is available even if settings
    was already instantiated by a prior test module (import-order race)."""
    from app.core.config import settings

    if not settings.FLUXVPN_SECRET_KEY:
        monkeypatch.setattr(settings, "FLUXVPN_SECRET_KEY", _TEST_SECRET_KEY)


def test_round_trip_returns_original_token():
    from app.core.crypto import decrypt_token, encrypt_token

    original = "1234567890:ABCDEFghijklmnop-1234567890"
    blob = encrypt_token(original)
    assert decrypt_token(blob) == original


def test_blob_is_not_plaintext():
    """The encrypted blob must not contain the original token bytes."""
    from app.core.crypto import encrypt_token

    original = "1234567890:ABCDEFghijklmnop"
    blob = encrypt_token(original)
    assert original.encode() not in blob
    assert original not in blob.decode("latin-1", errors="ignore")


def test_blob_includes_12_byte_nonce_prefix():
    """AES-GCM nonce is 12 bytes; we prepend it."""
    from app.core.crypto import encrypt_token

    blob = encrypt_token("x")
    assert len(blob) >= 28  # 12 nonce + 16 tag + at least 1 ciphertext


def test_each_encrypt_produces_different_blob():
    """Random nonce means same input -> different output."""
    from app.core.crypto import encrypt_token

    a = encrypt_token("abc")
    b = encrypt_token("abc")
    assert a != b


def test_tamper_detection_raises_invalid_tag():
    from cryptography.exceptions import InvalidTag

    from app.core.crypto import decrypt_token, encrypt_token

    blob = bytearray(encrypt_token("hello"))
    blob[-1] ^= 0xFF  # flip last byte
    with pytest.raises(InvalidTag):
        decrypt_token(bytes(blob))
