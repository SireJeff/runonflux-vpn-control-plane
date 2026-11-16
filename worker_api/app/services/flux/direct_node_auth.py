"""
Flux Direct Node Authentication Module

Provides authentication using direct Flux nodes instead of centralized API gateways.
This module bypasses congested API gateways by communicating directly with Flux nodes.

Key Finding:
- /id/loginphrase WORKS on direct nodes (600-1200ms response time)
- /id/verifylogin TIMES OUT on both API gateways AND direct nodes
- Root cause: Blockchain verification infrastructure issue, not API gateway issue

Usage:
    from app.services.flux.direct_node_auth import DirectNodeAuthProvider

    provider = DirectNodeAuthProvider()
    login_phrase = await provider.get_login_phrase()
    # Sign phrase externally or with private key
    signature = provider.sign_message(login_phrase, private_key)
    provider.set_signature(signature, login_phrase)

    # Get auth headers for API calls
    headers = await provider.get_auth_headers()
"""

import asyncio
import base64
import hashlib
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings

# secp256k1 (Bitcoin-style) signing
try:
    import base58
    import ecdsa

    SECP256K1_AVAILABLE = True
except ImportError:
    SECP256K1_AVAILABLE = False

logger = logging.getLogger(__name__)


class DirectNodeAuthProvider:
    """
    Authentication provider that uses direct Flux nodes for login phrase generation.

    Advantages:
    - Faster response times (600-1200ms vs 2000+ms for API gateway)
    - Bypasses API gateway load balancers
    - More reliable for login phrase generation

    Limitations:
    - /id/verifylogin still times out (blockchain infrastructure issue)
    - Cannot escalate privilege without working verifylogin
    """

    # Default nodes to try for authentication
    DEFAULT_AUTH_NODES = [
        "64.32.48.160",  # Fastest response (614ms)
        "64.32.48.101",  # Second fastest (624ms)
        "64.32.48.162",  # Third fastest (852ms)
        "108.235.45.109",
        "79.150.200.154",
    ]

    # Fallback to these API gateways if nodes fail
    FALLBACK_API_GATEWAYS = [
        "https://api.runonflux.io",
        "https://api.runonflux.com",
    ]

    def __init__(
        self,
        wallet_address: Optional[str] = None,
        private_key: Optional[str] = None,
        auth_nodes: Optional[List[str]] = None,
    ):
        """
        Initialize the direct node authentication provider.

        Args:
            wallet_address: Flux/Zelcore wallet address
            private_key: Private key for direct signing (secp256k1 WIF format)
            auth_nodes: List of node IPs to use for login phrase generation
        """
        self.wallet_address = wallet_address or settings.FLUX_WALLET_ADDRESS
        self._private_key = private_key or settings.FLUX_WALLET_PRIVATE_KEY
        self.auth_nodes = auth_nodes or self.DEFAULT_AUTH_NODES

        # Auth state
        self._login_phrase: Optional[str] = None
        self._signature: Optional[str] = None
        self._auth_timestamp: float = 0
        self._phrase_source: Optional[str] = None  # Which node/API provided the phrase
        self._privilege: Optional[str] = None

        # HTTP client for node communication
        self.client = httpx.AsyncClient(
            timeout=15.0,
            # nosec: B501 - Direct nodes often use self-signed certificates; intentional skip
            verify=False,  # Nodes may have self-signed certs
            limits=httpx.Limits(max_keepalive_connections=1, max_connections=1),
        )

    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def get_login_phrase(self, use_api_fallback: bool = True) -> str:
        """
        Get a login phrase from direct Flux nodes.

        Tries nodes in order, falls back to API gateways if all nodes fail.

        Args:
            use_api_fallback: If True, try API gateways if nodes fail

        Returns:
            Login phrase string

        Raises:
            FluxCloudAPIException: If all sources fail
        """
        # Try direct nodes first (faster, more reliable)
        for node_ip in self.auth_nodes:
            try:
                phrase = await self._get_phrase_from_node(node_ip)
                self._login_phrase = phrase
                self._phrase_source = f"node:{node_ip}"
                self._auth_timestamp = time.time()
                logger.info(f"Got login phrase from node {node_ip}")
                return phrase
            except Exception as e:
                logger.debug(f"Node {node_ip} failed: {e}")
                continue

        # Fallback to API gateways
        if use_api_fallback:
            for api_url in self.FALLBACK_API_GATEWAYS:
                try:
                    phrase = await self._get_phrase_from_api(api_url)
                    self._login_phrase = phrase
                    self._phrase_source = f"api:{api_url}"
                    self._auth_timestamp = time.time()
                    logger.info(f"Got login phrase from API {api_url}")
                    return phrase
                except Exception as e:
                    logger.debug(f"API {api_url} failed: {e}")
                    continue

        raise FluxCloudAPIException(
            "Failed to get login phrase from any source "
            "(tried all nodes and API gateways)"
        )

    async def _get_phrase_from_node(self, node_ip: str) -> str:
        """Get login phrase from a specific Flux node"""
        url = f"http://{node_ip}:16127/id/loginphrase"
        response = await self.client.get(url)

        if response.status_code != 200:
            raise FluxCloudAPIException(f"HTTP {response.status_code}")

        data = response.json()
        phrase = data.get("data") or data.get("loginPhrase") or data.get("message")

        if not phrase:
            raise FluxCloudAPIException("No phrase in response")

        return str(phrase)

    async def _get_phrase_from_api(self, api_url: str) -> str:
        """Get login phrase from API gateway"""
        url = f"{api_url}/id/loginphrase"
        response = await self.client.get(url)

        if response.status_code != 200:
            raise FluxCloudAPIException(f"HTTP {response.status_code}")

        data = response.json()
        phrase = data.get("data") or data.get("loginPhrase") or data.get("message")

        if not phrase:
            raise FluxCloudAPIException("No phrase in response")

        return str(phrase)

    def sign_message(self, message: str, private_key: Optional[str] = None) -> str:
        """
        Sign a message using secp256k1 private key.

        Args:
            message: Message to sign
            private_key: Private key (uses instance key if not provided)

        Returns:
            Base64-encoded signature
        """
        key = private_key or self._private_key

        if not key:
            raise FluxCloudAPIException("No private key available for signing")

        if not SECP256K1_AVAILABLE:
            raise FluxCloudAPIException(
                "secp256k1 libraries not available. Install: pip install ecdsa base58"
            )

        try:
            # Decode WIF key
            decoded = base58.b58decode(key)
            payload = decoded[:-4]  # Remove checksum

            if len(payload) == 33 and payload[0] in [0x80, 0xEF]:
                key_bytes = payload[1:]  # Remove version byte
            else:
                key_bytes = payload[-32:]

            # Create signing key
            priv_key = ecdsa.SigningKey.from_string(key_bytes, curve=ecdsa.SECP256k1)

            # Bitcoin message signing format
            message_bytes = message.encode("utf-8")
            message_prefix = b"\x18Bitcoin Signed Message:\n"
            length = len(message_bytes)
            if length < 253:
                message_length = bytes([length])
            else:
                message_length = b"\xfd" + length.to_bytes(2, "little")

            full_message = message_prefix + message_length + message_bytes

            # Sign
            signature = priv_key.sign_digest(
                hashlib.sha256(full_message).digest(),
                sigencode=ecdsa.util.sigencode_der_canonize,
            )

            return base64.b64encode(signature).decode("utf-8")

        except Exception as e:
            raise FluxCloudAPIException(f"Signing failed: {e}")

    def set_signature(self, signature: str, login_phrase: Optional[str] = None) -> None:
        """
        Set the signature for authentication.

        Args:
            signature: Base64-encoded signature
            login_phrase: The phrase that was signed (optional if already cached)
        """
        self._signature = signature
        if login_phrase:
            self._login_phrase = login_phrase
        self._auth_timestamp = time.time()
        logger.debug("Signature set successfully")

    async def verify_login(self, timeout: float = 10.0) -> Dict[str, Any]:
        """
        Attempt to verify login and get privilege level.

        WARNING: This currently times out across the entire Flux network
        (both API gateways and direct nodes) due to blockchain infrastructure issues.

        Args:
            timeout: Request timeout in seconds

        Returns:
            Dict with success status and privilege level if successful
        """
        if not self._login_phrase or not self._signature:
            raise FluxCloudAPIException(
                "Must set signature and login phrase before verifying"
            )

        payload = {
            "zelid": self.wallet_address,
            "loginPhrase": self._login_phrase,
            "signature": self._signature,
        }

        # Try direct nodes first
        for node_ip in self.auth_nodes:
            try:
                url = f"http://{node_ip}:16127/id/verifylogin"
                response = await self.client.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=timeout,
                )

                if response.status_code == 200:
                    data = response.json()
                    if data.get("status") == "success":
                        self._privilege = data.get("data", {}).get("privilege", "user")
                        return {
                            "success": True,
                            "privilege": self._privilege,
                            "source": f"node:{node_ip}",
                        }

            except (asyncio.TimeoutError, httpx.TimeoutException):
                logger.debug(f"verifylogin timeout on node {node_ip}")
                continue
            except Exception as e:
                logger.debug(f"verifylogin error on node {node_ip}: {e}")
                continue

        # Try API gateways
        for api_url in self.FALLBACK_API_GATEWAYS:
            try:
                url = f"{api_url}/id/verifylogin"
                response = await self.client.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=timeout,
                )

                if response.status_code == 200:
                    data = response.json()
                    if data.get("status") == "success":
                        self._privilege = data.get("data", {}).get("privilege", "user")
                        return {
                            "success": True,
                            "privilege": self._privilege,
                            "source": f"api:{api_url}",
                        }

            except (asyncio.TimeoutError, httpx.TimeoutException):
                logger.debug(f"verifylogin timeout on API {api_url}")
                continue
            except Exception as e:
                logger.debug(f"verifylogin error on API {api_url}: {e}")
                continue

        # All failed
        logger.warning(
            "verifylogin timed out on all endpoints (expected - blockchain infrastructure issue)"
        )
        return {
            "success": False,
            "error": "verifylogin timeout - blockchain infrastructure issue",
            "privilege": "user",  # Default privilege
        }

    async def get_auth_headers(self) -> Dict[str, str]:
        """
        Get authentication headers for API calls.

        Returns:
            Dict with zelidauth header
        """
        if not self._signature:
            # Auto-sign if we have a private key
            if self._private_key:
                if not self._login_phrase:
                    await self.get_login_phrase()
                login_phrase = self._login_phrase
                if not login_phrase:
                    raise FluxCloudAPIException("Unable to obtain login phrase")
                self._signature = self.sign_message(login_phrase)
            else:
                raise FluxCloudAPIException(
                    "No signature set. Call set_signature() or provide private_key"
                )

        from urllib.parse import quote

        login_phrase = self._login_phrase or ""
        zelidauth = (
            f"zelid={self.wallet_address}"
            f"&signature={self._signature}"
            f"&loginPhrase={quote(login_phrase)}"
        )

        return {"zelidauth": zelidauth}

    async def authenticate(self) -> Dict[str, Any]:
        """
        Perform full authentication flow.

        This will:
        1. Get a login phrase (from nodes or API)
        2. Sign it with private key
        3. Attempt verifylogin (expected to timeout)
        4. Return auth result

        Returns:
            Dict with authentication status and privilege
        """
        if not self._private_key:
            raise FluxCloudAPIException("Private key required for authentication")

        # Step 1: Get login phrase
        phrase = await self.get_login_phrase()

        # Step 2: Sign it
        signature = self.sign_message(phrase)
        self.set_signature(signature, phrase)

        # Step 3: Try to verify (expected to timeout)
        verify_result = await self.verify_login(timeout=10.0)

        logger.info(
            f"Authentication complete: "
            f"phrase from {self._phrase_source}, "
            f"privilege={verify_result.get('privilege', 'unknown')}"
        )

        return verify_result

    def get_status(self) -> Dict[str, Any]:
        """Get current authentication status"""
        return {
            "wallet_address": self.wallet_address,
            "has_private_key": bool(self._private_key),
            "has_login_phrase": bool(self._login_phrase),
            "has_signature": bool(self._signature),
            "phrase_source": self._phrase_source,
            "privilege": self._privilege,
            "auth_age_seconds": (
                time.time() - self._auth_timestamp if self._auth_timestamp else 0
            ),
        }


class FluxCloudAPIException(Exception):
    """Exception for FluxCloud API errors"""

    pass


# Test function
async def test_direct_node_auth():
    """Test the direct node authentication provider"""
    print("=" * 70)
    print("Testing Direct Node Authentication Provider")
    print("=" * 70)

    # Test with direct nodes
    provider = DirectNodeAuthProvider()

    try:
        # Get login phrase from nodes
        print("\n[1] Getting login phrase from direct nodes...")
        phrase = await provider.get_login_phrase()
        print(f"    OK: Got phrase from {provider._phrase_source}")
        print(f"    Phrase: {phrase[:30]}...")

        # Get status
        status = provider.get_status()
        print(f"\n[2] Status: {status}")

    finally:
        await provider.close()

    print("\n" + "=" * 70)


if __name__ == "__main__":
    asyncio.run(test_direct_node_auth())
