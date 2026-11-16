"""AES-GCM encrypt/decrypt for bot tokens at rest.

The 12-byte nonce is prepended to the ciphertext+tag blob, so the stored
LargeBinary column contains:
    [nonce (12 bytes)] [ciphertext + GCM tag (rest)]
"""

import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings


def _derive_key() -> bytes:
    """Derive a 32-byte AES key from FLUXVPN_SECRET_KEY via SHA-256."""
    secret = settings.FLUXVPN_SECRET_KEY
    if not secret:
        raise RuntimeError("FLUXVPN_SECRET_KEY must be set")
    return hashlib.sha256(secret.encode()).digest()


def encrypt_token(plaintext: str) -> bytes:
    """Encrypt a bot token. Returns nonce + ciphertext + tag."""
    nonce = os.urandom(12)
    ciphertext = AESGCM(_derive_key()).encrypt(nonce, plaintext.encode(), None)
    return nonce + ciphertext


def decrypt_token(blob: bytes) -> str:
    """Decrypt a blob produced by encrypt_token. Raises InvalidTag on tamper."""
    nonce, ciphertext = blob[:12], blob[12:]
    return AESGCM(_derive_key()).decrypt(nonce, ciphertext, None).decode()
