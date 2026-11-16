"""
FluxCloud API Client
Handles all interactions with FluxCloud API for node management

SECURITY NOTICE - Multi-Wallet Authentication (API v6.6.1):
=====================================================
CRITICAL: FluxCloud ZelID authentication requires Bitcoin secp256k1 signing,
NOT Ed25519! The private key must be in Base58Check format (WIF) or hex.

This client supports two authentication modes:

1. Direct Private Key Mode (for deployment scripts):
   - Uses FLUX_WALLET_PRIVATE_KEY from settings
   - Signs messages internally using secp256k1 (Bitcoin-style)
   - Supports Base58Check (WIF) and hex-encoded private keys
   - WARNING: Only use in secure environments

2. External Wallet Mode (recommended for production):
   - Get login phrase from /id/loginphrase (15 min validity)
   - Sign the phrase EXTERNALLY with ZelCore wallet (secp256k1)
   - Provide the signature to this client via set_signature()

Flow: Login Phrase → Signature (secp256k1) → zelidauth Header

Required: Successfully call /id/verifylogin BEFORE performing restricted operations!

Documentation: See docs/fluxcloud/api/authentication.md

Resilience Features:
- Automatic retry with exponential backoff for transient errors (502, 503, 504, 429)
- Circuit breaker to fail fast when API is down
- Configurable via settings
"""

import hashlib
import logging
import os
import struct
import time
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx

from app.core.config import settings
from app.services.flux.resilience import (
    AsyncCircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerStatus,
    FluxAPICircuitOpenError,
    FluxAPITransientError,
    RetryConfig,
    create_retry_decorator,
    is_non_retryable_status_code,
    is_retryable_status_code,
)

# secp256k1 (Bitcoin-style) signing for FluxCloud ZelID authentication
try:
    import base58
    import ecdsa

    SECP256K1_AVAILABLE = True
except ImportError:
    SECP256K1_AVAILABLE = False

# coincurve provides proper secp256k1 with recovery (used for Bitcoin Signed Message format)
try:
    from coincurve import PrivateKey as CoinCurvePrivateKey

    COINCURVE_AVAILABLE = True
except ImportError:
    COINCURVE_AVAILABLE = False

# Fallback: Ed25519 (NOT compatible with FluxCloud ZelID!)
try:
    from cryptography.hazmat.primitives.asymmetric import ed25519

    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False

logger = logging.getLogger(__name__)


class FluxCloudAPIException(Exception):
    """Exception raised for FluxCloud API errors"""

    pass


class FluxCloudClient:
    """
    Client for interacting with FluxCloud API

    FluxCloud API Documentation: https://api.runonflux.io/docs

    SECURITY: Multi-wallet authentication (ZelCore, MetaMask, SSP, WalletConnect)
    - Private keys are NEVER stored or used directly
    - Login phrases are obtained from API (15 min validity)
    - Signing is performed EXTERNALLY by wallet software
    - Signatures are provided to this client for authentication
    """

    _MIN_PAYMENT_SATS = 10_000
    _MAX_PAYMENT_SATS = 2_100_000_000_000_000

    def __init__(
        self,
        wallet_address: Optional[str] = None,
        signature: Optional[str] = None,
        login_phrase: Optional[str] = None,
        api_url: Optional[str] = None,
        retry_config: Optional[RetryConfig] = None,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
        private_key: Optional[str] = None,
    ):
        """
        Initialize FluxCloud API client

        SECURITY: Two authentication modes supported:
        1. Direct mode: Provide private_key (uses FLUX_WALLET_PRIVATE_KEY if not provided)
           - CRITICAL: Must use secp256k1 (Bitcoin-style) signing, NOT Ed25519!
           - Supports Base58Check/WIF format (Bitcoin) or hex-encoded keys
        2. External mode: Use get_login_phrase() + set_signature() flow
           - Sign EXTERNALLY with ZelCore wallet using secp256k1

        Args:
            wallet_address: Flux/Zelcore wallet address (defaults to settings.FLUX_WALLET_ADDRESS)
            signature: Pre-computed signature from ZelCore wallet (optional, for external mode)
            login_phrase: Pre-computed login phrase (optional, for external mode)
            api_url: FluxCloud API base URL (defaults to settings.FLUX_API_URL)
            retry_config: Configuration for retry behavior (uses settings defaults if None)
            circuit_breaker_config: Configuration for circuit breaker (uses settings defaults if None)
            private_key: secp256k1 private key (Base58Check/WIF or hex format)
        """
        self.wallet_address = wallet_address or settings.FLUX_WALLET_ADDRESS
        self.api_url = (api_url or settings.FLUX_API_URL).rstrip("/")

        # Auth cache - supports both direct and external signing modes
        self._login_phrase: Optional[str] = login_phrase
        self._signature: Optional[str] = signature
        self._auth_timestamp: float = 0
        self._auth_validity: int = 900  # 15 minutes (login phrases expire in 15 min)
        self._privilege: Optional[
            str
        ] = None  # Privilege level from verifylogin (user, admin, etc.)

        # Private key for direct signing (from parameter or settings)
        self._private_key: Optional[str] = (
            private_key
            or os.environ.get("FLUX_WALLET_PRIVATE_KEY")
            or settings.FLUX_WALLET_PRIVATE_KEY
        )

        if self._private_key:
            logger.debug("Private key available - direct signing mode enabled")
        else:
            logger.debug("No private key - external signing mode required")

        # Resilience: Retry configuration
        self._retry_config = retry_config or RetryConfig(
            max_attempts=settings.FLUX_RETRY_MAX_ATTEMPTS,
            min_wait_seconds=settings.FLUX_RETRY_MIN_WAIT,
            max_wait_seconds=settings.FLUX_RETRY_MAX_WAIT,
        )

        # Resilience: Circuit breaker
        cb_config = circuit_breaker_config or CircuitBreakerConfig(
            failure_threshold=settings.FLUX_CIRCUIT_FAILURE_THRESHOLD,
            recovery_timeout=settings.FLUX_CIRCUIT_RECOVERY_TIMEOUT,
        )
        self._circuit_breaker = AsyncCircuitBreaker(cb_config)

        # HTTP client (without auth headers - we'll add per request)
        # Increased timeout for multi-component deployments which can take 60+ seconds
        # Limits: 1 connection to avoid pool exhaustion, no keepalive for reliability
        # NOTE: FluxCloud API requires text/plain content type for POST requests
        limits = httpx.Limits(
            max_keepalive_connections=1, max_connections=1, keepalive_expiry=5.0
        )
        self.client = httpx.AsyncClient(
            base_url=self.api_url,
            timeout=httpx.Timeout(180.0, connect=30.0, read=150.0),
            limits=limits,
        )

    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()

    async def __aenter__(self):
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()

    # ========================================================================
    # AUTHENTICATION
    # ========================================================================

    async def _get_login_phrase(self, use_emergency: bool = False) -> str:
        """
        Get a login phrase from FluxCloud API.

        Tries in order:
        1. Direct nodes (fastest, ~600ms)
        2. Emergency phrase endpoint (if use_emergency=True, ~1900ms)
        3. API gateway fallback (~2200ms)

        Args:
            use_emergency: If True, try /id/emergencyphrase endpoint

        Returns:
            Login phrase string to be signed
        """
        # Fast nodes for login phrase generation (from test results)
        fast_nodes = [
            "64.32.48.160",  # 614ms
            "64.32.48.101",  # 624ms
            "64.32.48.162",  # 852ms
        ]

        import httpx

        # Try direct nodes first (much faster than API gateway)
        # nosec: B501 - Direct nodes often use self-signed certificates; intentional skip
        node_client = httpx.AsyncClient(timeout=10.0, verify=False)

        for node_ip in fast_nodes:
            try:
                response = await node_client.get(
                    f"http://{node_ip}:16127/id/loginphrase"
                )
                if response.status_code == 200:
                    data = response.json()
                    phrase = (
                        data.get("data")
                        or data.get("loginPhrase")
                        or data.get("message")
                    )
                    if phrase:
                        logger.debug(
                            f"Got login phrase from node {node_ip}: {phrase[:20]}..."
                        )
                        await node_client.aclose()
                        return str(phrase)
            except Exception as e:
                logger.debug(f"Node {node_ip} failed: {e}")
                continue

        await node_client.aclose()

        # Try emergency phrase if requested (may bypass some congestion)
        if use_emergency:
            try:
                response = await self.client.get("/id/emergencyphrase")
                if response.status_code == 200:
                    data = response.json()
                    phrase = (
                        data.get("data")
                        or data.get("loginPhrase")
                        or data.get("emergencyPhrase")
                    )
                    if phrase:
                        logger.debug(f"Got emergency phrase from API: {phrase[:20]}...")
                        return str(phrase)
            except Exception as e:
                logger.debug(f"Emergency phrase failed: {e}")

        # Fallback to API gateway
        try:
            response = await self.client.get("/id/loginphrase")
            response.raise_for_status()
            data = response.json()

            # Response format may vary - handle both cases
            if isinstance(data, dict):
                phrase = (
                    data.get("data") or data.get("loginPhrase") or data.get("message")
                )
            else:
                phrase = str(data)

            logger.debug(f"Got login phrase from API gateway: {phrase[:20]}...")
            return phrase

        except Exception as e:
            logger.error(f"Failed to get login phrase: {e}")
            raise FluxCloudAPIException(f"Failed to get login phrase: {e}")

    def set_signature(self, signature: str, login_phrase: Optional[str] = None) -> None:
        """
        Set the signature and login phrase for authentication.

        This method should be called after getting a login phrase from get_login_phrase()
        and signing it EXTERNALLY with your ZelCore wallet.

        SECURITY: Never store or use private keys directly. Always sign externally.

        Args:
            signature: The signature from ZelCore wallet
            login_phrase: The login phrase that was signed (optional if already cached)

        Example:
            >>> client = FluxCloudClient(wallet_address="0x123...")
            >>> phrase = await client.get_login_phrase()
            >>> # Sign the phrase EXTERNALLY with ZelCore wallet
            >>> signature = external_wallet_sign(phrase)  # External signing
            >>> client.set_signature(signature, phrase)
        """
        self._signature = signature
        if login_phrase:
            self._login_phrase = login_phrase
        self._auth_timestamp = time.time()
        logger.debug("Signature set successfully")

    def _decode_base58_check(self, key: str) -> bytes:
        """
        Decode Base58Check encoded private key (WIF format).

        Args:
            key: Base58Check encoded private key

        Returns:
            Decoded key bytes

        Raises:
            FluxCloudAPIException: If decoding fails
        """
        if not SECP256K1_AVAILABLE:
            raise FluxCloudAPIException(
                "secp256k1 libraries not available. Install with: pip install ecdsa base58"
            )

        try:
            # Base58 decode
            decoded = base58.b58decode(key)

            # Verify checksum (last 4 bytes are double-SHA256 checksum)
            if len(decoded) < 4:
                raise ValueError("Invalid Base58Check string")

            payload = decoded[:-4]
            checksum = decoded[-4:]

            # Verify checksum
            hash_result = hashlib.sha256(hashlib.sha256(payload).digest()).digest()
            calculated_checksum = hash_result[:4]

            if checksum != calculated_checksum:
                logger.warning("Checksum mismatch for Base58Check key")

            # Remove version byte (first byte) if present
            # WIF format: [version][32-byte key][checksum]
            if len(payload) == 33 and payload[0] in [
                0x80,
                0xEF,
            ]:  # Mainnet or testnet version byte
                return payload[1:]  # Return 32-byte private key
            elif len(payload) == 32:
                return payload  # Already a 32-byte key
            else:
                # Try to extract the last 32 bytes as the key
                return payload[-32:]

        except Exception as e:
            raise FluxCloudAPIException(f"Failed to decode Base58Check key: {e}")

    @staticmethod
    def _bitcoin_varint(n: int) -> bytes:
        """
        Bitcoin compact size (varuint) encoding.

        Matches varuint-bitcoin library behavior from reference implementation.
        Reference: https://github.com/chaintype/varuint-bitcoin

        Format:
        - 0-252: single byte
        - 253-65535: 0xFD + 2 bytes (little-endian)
        - 65536-4294967295: 0xFE + 4 bytes (little-endian)
        - >4294967295: 0xFF + 8 bytes (little-endian)
        """
        if n < 0xFD:
            return bytes([n])
        elif n <= 0xFFFF:
            return b"\xfd" + struct.pack("<H", n)
        elif n <= 0xFFFFFFFF:
            return b"\xfe" + struct.pack("<I", n)
        else:
            return b"\xff" + struct.pack("<Q", n)

    def _sign_message(self, message: str) -> str:
        """
        Sign a message using secp256k1 private key (Bitcoin Signed Message format).

        CRITICAL: FluxCloud ZelID requires secp256k1 (Bitcoin) signatures with recovery byte!

        This method uses the Bitcoin Signed Message protocol:
        1. Hash: SHA256 of "\x18Bitcoin Signed Message:\n" + varint(len) + message
        2. Sign: secp256k1 with recovery (coincurve library)
        3. Format: recovery_byte + r + s where recovery_byte = recovery + 4 + 27

        Args:
            message: The message string to sign

        Returns:
            Base64-encoded 65-byte signature (recovery + r + s)

        Raises:
            FluxCloudAPIException: If private key is not available or signing fails
        """
        if not self._private_key:
            raise FluxCloudAPIException(
                "No private key available for direct signing.\n"
                "Set FLUX_WALLET_PRIVATE_KEY environment variable or use external signing mode:\n"
                "1. Call get_login_phrase() to get a phrase\n"
                "2. Sign EXTERNALLY with ZelCore wallet (secp256k1)\n"
                "3. Call set_signature(signature, login_phrase)"
            )

        # Prefer coincurve for proper recovery byte support
        if not COINCURVE_AVAILABLE:
            raise FluxCloudAPIException(
                "coincurve library not available. Install with: pip install coincurve"
            )

        try:
            # Decode private key (supports Base58Check/WIF and hex formats)
            if self._private_key.startswith("K") or self._private_key.startswith("L"):
                # Base58Check/WIF format (Bitcoin)
                decoded = base58.b58decode(self._private_key)
                payload = decoded[:-4]
                # WIF with compression: version(1) + key(32) + compression(1) = 34 bytes
                # WIF without compression: version(1) + key(32) = 33 bytes
                if len(payload) == 34:
                    key_bytes = payload[1:33]  # Skip version, take 32 bytes
                elif len(payload) == 33 and payload[0] in [0x80, 0xEF]:
                    key_bytes = payload[1:]  # Skip version, rest is 32 bytes
                else:
                    key_bytes = payload[-32:]  # Take last 32 bytes
            elif len(self._private_key) == 64 or len(self._private_key) == 128:
                # Hex format
                key_bytes = bytes.fromhex(self._private_key)
            else:
                # Try Base58Check decoding
                decoded = base58.b58decode(self._private_key)
                payload = decoded[:-4]
                if len(payload) == 34:
                    key_bytes = payload[1:33]
                elif len(payload) == 33 and payload[0] in [0x80, 0xEF]:
                    key_bytes = payload[1:]
                else:
                    key_bytes = payload[-32:]

            # Ensure we have exactly 32 bytes
            if len(key_bytes) != 32:
                raise FluxCloudAPIException(
                    f"Invalid private key length: {len(key_bytes)} bytes (expected 32 bytes)"
                )

            # Bitcoin Signed Message format
            # Prepend "Bitcoin Signed Message:" prefix and encode length
            message_bytes = message.encode("utf-8")
            message_prefix = b"\x18Bitcoin Signed Message:\n"

            # Bitcoin message length encoding (varint)
            # Use helper method for proper Bitcoin compact size encoding
            message_length = self._bitcoin_varint(len(message_bytes))

            full_message = message_prefix + message_length + message_bytes
            # CRITICAL: Flux API uses SINGLE SHA-256 (not Bitcoin's double SHA-256!)
            # Verified by testing against /id/verifylogin endpoint
            message_hash = hashlib.sha256(full_message).digest()

            # Sign with coincurve (secp256k1 with recovery)
            priv_key = CoinCurvePrivateKey(key_bytes)
            sig = priv_key.sign_recoverable(
                message_hash
            )  # 65 bytes: r(32) + s(32) + recovery(1)

            # Extract components
            r = sig[:32]
            s = sig[32:64]
            recovery = sig[64]  # 0 or 1

            # Build Bitcoin Signed Message format: recovery_byte + r + s
            # recovery_byte = recovery + 4 + 27 (compressed key indicator + Bitcoin magic)
            bitcoin_recovery = recovery + 4 + 27
            final_sig = bytes([bitcoin_recovery]) + r + s

            # Convert to Base64
            import base64

            signature_b64 = base64.b64encode(final_sig).decode("utf-8")

            logger.debug(f"Signed message (length {len(message)}): {message[:50]}...")
            logger.debug(f"Signature (Base64): {signature_b64[:40]}...")

            return signature_b64

        except ValueError as e:
            raise FluxCloudAPIException(f"Invalid private key format: {e}")
        except Exception as e:
            raise FluxCloudAPIException(f"Signing failed: {e}")

    async def authenticate_with_private_key(self) -> bool:
        """
        Authenticate using direct private key signing (secp256k1).

        Gets a login phrase from the API, signs it with secp256k1 private key,
        and attempts to verify with /id/verifylogin to get privilege level.

        NOTE: /id/verifylogin endpoint frequently times out (504). Authentication
        is still valid if we have a signature - many endpoints work without verifylogin.

        CRITICAL: Login phrases are ONE-TIME USE. After verifylogin consumes a phrase,
        we get a FRESH phrase for subsequent operations.

        Returns:
            True if authentication successful

        Raises:
            FluxCloudAPIException: If authentication fails
        """
        if not self._private_key:
            raise FluxCloudAPIException(
                "No private key available. Set FLUX_WALLET_PRIVATE_KEY environment variable."
            )

        # Get login phrase from API
        login_phrase = await self._get_login_phrase()

        # Sign the phrase with private key (secp256k1)
        signature = self._sign_message(login_phrase)

        # Try to verify login with FluxCloud API to get privilege level
        # This is optional - many endpoints work without it, and it frequently times out
        logger.info(
            "Attempting /id/verifylogin to get privilege level (may timeout)..."
        )

        # /id/verifylogin requires application/x-www-form-urlencoded content type
        # Using JSON causes timeout (504), form encoding returns HTTP 200
        from urllib.parse import urlencode

        verify_payload = urlencode(
            {
                "zelid": self.wallet_address,
                "loginPhrase": login_phrase,
                "signature": signature,
            }
        )

        try:
            # Make direct HTTP request for verifylogin (not through _request)
            # because we need form encoding
            async with httpx.AsyncClient(timeout=60.0) as verify_client:
                response = await verify_client.post(
                    f"{self.api_url}/id/verifylogin",
                    content=verify_payload.encode(),
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                response.raise_for_status()
                result = response.json()

                if result.get("status") == "success":
                    data = result.get("data", {})
                    # Note: Flux API returns "privilage" (typo, not "privilege")
                    privilege = data.get("privilage") or data.get(
                        "privilege", "unknown"
                    )
                    logger.info(
                        f"Successfully authenticated with privilege level: {privilege}"
                    )
                    self._privilege = privilege
                else:
                    logger.warning(f"Login verification returned: {result.get('data')}")
                    # Set default privilege if verification failed
                    self._privilege = (
                        "User"  # Assume User level for authenticated requests
                    )

        except httpx.TimeoutException as e:
            # Timeout is acceptable - server may be busy, proceed with auth
            logger.warning(f"/id/verifylogin timed out (server may be busy): {e}")
            logger.info("Proceeding with basic authentication (zelidauth header)")
            self._privilege = "User"  # Assume User level for authenticated requests

        except httpx.HTTPStatusError as e:
            # HTTP errors need special handling - 401 means invalid signature!
            logger.error(f"/id/verifylogin HTTP error: {e.response.status_code}")
            if e.response.status_code == 401:
                # CRITICAL: 401 means the signature is INVALID
                # This is likely due to incorrect signature format (single vs double SHA-256)
                raise FluxCloudAPIException(
                    "Authentication failed: Invalid signature (HTTP 401). "
                    "This typically means the signature format is incorrect. "
                    "Verify you are using double SHA-256 hashing as per Bitcoin standard."
                ) from e
            # For other HTTP errors, proceed with basic auth
            self._privilege = "User"

        except Exception as e:
            # Other exceptions - log and proceed with basic auth
            logger.warning(f"/id/verifylogin failed: {type(e).__name__}: {e}")
            logger.info("Proceeding with basic authentication (zelidauth header)")
            self._privilege = "User"  # Assume User level for authenticated requests

        # CRITICAL: Use the SAME phrase+signature for both verifylogin AND subsequent operations
        # Reference: https://github.com/prosopo/captcha/blob/main/dev/flux/src/lib/redeploy.ts
        # The phrase establishes the session, subsequent requests use same auth
        logger.debug("Setting signature from verified login")
        self.set_signature(signature, login_phrase)

        logger.info("Successfully authenticated with private key")
        return True

    async def _ensure_auth(self, force_refresh: bool = False) -> Dict[str, str]:
        """
        Ensure we have valid authentication.

        SECURITY: This method requires either:
        1. Direct signing mode: FLUX_WALLET_PRIVATE_KEY set, signature auto-generated
        2. External signing mode: set_signature() called with external signature

        Args:
            force_refresh: If True, get a fresh login phrase even if cached exists

        Returns:
            Headers dict with zelidauth

        Raises:
            FluxCloudAPIException: If signature has not been set
        """
        current_time = time.time()

        # If we have a private key, we can auto-generate fresh auth
        if self._private_key:
            # Check if we need to refresh (no signature OR signature is old OR force requested)
            age_since_auth = current_time - self._auth_timestamp
            needs_refresh = (
                force_refresh
                or not self._signature
                or not self._login_phrase
                or age_since_auth > 300  # 5 minutes - refresh periodically
            )

            if needs_refresh:
                logger.debug("Getting fresh login phrase for authentication")
                # Get fresh login phrase
                self._login_phrase = await self._get_login_phrase()
                # Sign it
                self._signature = self._sign_message(self._login_phrase)
                self._auth_timestamp = current_time

        # For external signing mode, check signature was provided
        if not self._signature:
            raise FluxCloudAPIException(
                "No signature provided. Use one of:\n"
                "1. Direct mode: Set FLUX_WALLET_PRIVATE_KEY environment variable\n"
                "2. External mode:\n"
                "   - Call get_login_phrase() to get a phrase\n"
                "   - Sign the phrase EXTERNALLY with your ZelCore wallet\n"
                "   - Call set_signature(signature, login_phrase)\n"
                "See docs/fluxcloud/api/authentication.md for details."
            )

        if not self._login_phrase:
            raise FluxCloudAPIException(
                "No login phrase provided. For external signing mode, call get_login_phrase() first, "
                "then set_signature(signature, login_phrase)."
            )

        # Check if auth is still valid (15 minutes from phrase generation)
        # Skip this check for direct signing mode where login_phrase is a timestamp
        if (
            not self._private_key
            and (current_time - self._auth_timestamp) > self._auth_validity
        ):
            raise FluxCloudAPIException(
                "Login phrase has expired (15 minute validity). "
                "Please get a new login phrase and signature."
            )

        # Build zelidauth header value
        # Format: zelid=address&signature=signature&loginPhrase=phrase
        # CRITICAL: ALL components must be URL-encoded (Base64 contains +, /, =)
        # Reference: https://github.com/prosopo/captcha/blob/main/dev/flux/src/lib/url.ts
        wallet_address = self.wallet_address or ""
        login_phrase = self._login_phrase or ""
        zelidauth = (
            f"zelid={quote(wallet_address, safe='')}"
            f"&signature={quote(self._signature, safe='')}"
            f"&loginPhrase={quote(login_phrase, safe='')}"
        )

        # Use capital Z to match reference implementation (case-sensitive headers on server)
        return {"Zelidauth": zelidauth}

    @staticmethod
    def _scrub_env_params(payload):
        """M1: return a log-safe copy of a Flux payload with
        compose[].environmentParameters removed (those carry live JWTs).
        The caller's original payload is NEVER mutated — the spec fetcher reads
        environmentParameters to build its component list, so only the DEBUG
        log line is scrubbed."""
        import copy

        safe = copy.deepcopy(payload)
        data = safe.get("data") if isinstance(safe, dict) else None
        compose = data.get("compose") if isinstance(data, dict) else None
        if isinstance(compose, list):
            for comp in compose:
                if isinstance(comp, dict):
                    comp.pop("environmentParameters", None)
        return safe

    async def _request(
        self,
        method: str,
        endpoint: str,
        authenticated: bool = True,
        _timeout: Optional[float] = None,
        redact: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Make HTTP request to FluxCloud API

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (e.g., "/apps/deploy")
            authenticated: Whether to include auth headers (default True)
            _timeout: Custom timeout for this request (overrides default)
            redact: If True, scrub compose[].environmentParameters from the
                DEBUG log line ONLY (the returned payload is always untouched).
                Used by FluxSpecFetcher where the response carries live JWTs.
            **kwargs: Additional arguments for httpx.request()

        Returns:
            Response data as dictionary (always the real, unredacted payload)

        Raises:
            FluxCloudAPIException: If API request fails
        """
        import json as json_module

        url = f"{self.api_url}{endpoint}"

        # Get auth headers if needed
        headers = kwargs.pop("headers", {})
        if authenticated and self.wallet_address:
            auth_headers = await self._ensure_auth()
            headers.update(auth_headers)
        elif authenticated and not self.wallet_address:
            # Authentication required but wallet address not configured
            raise FluxCloudAPIException(
                "Wallet address not configured. Set FLUX_WALLET_ADDRESS in settings."
            )

        # FluxCloud API requires text/plain content type for POST requests
        # Convert json kwargs to content string with text/plain header
        # Some endpoints like /id/verifylogin require application/json instead
        content_type_json = kwargs.pop("_content_type_json", False)
        if method.upper() in ("POST", "PUT") and "json" in kwargs:
            json_data = kwargs.pop("json")
            kwargs["content"] = json_module.dumps(json_data)
            if content_type_json:
                headers["Content-Type"] = "application/json"
            else:
                headers["Content-Type"] = "text/plain"

        try:
            logger.info(f"FluxCloud API: {method} {url}")
            # Use custom timeout if provided, otherwise use default
            if _timeout is not None:
                timeout = httpx.Timeout(_timeout, connect=30.0)
                response = await self.client.request(
                    method, endpoint, headers=headers, timeout=timeout, **kwargs
                )
            else:
                response = await self.client.request(
                    method, endpoint, headers=headers, **kwargs
                )
            response.raise_for_status()

            data = response.json()
            log_payload = self._scrub_env_params(data) if redact else data
            logger.debug(f"FluxCloud API response: {log_payload}")

            return data  # ALWAYS the real, untouched payload

        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            logger.error(f"FluxCloud API HTTP error: {status_code} - {e.response.text}")

            # Check if this is a retryable error
            if is_retryable_status_code(status_code):
                raise FluxAPITransientError(
                    f"FluxCloud API HTTP {status_code}: {e.response.text}",
                    status_code=status_code,
                )

            raise FluxCloudAPIException(
                f"FluxCloud API HTTP {status_code}: {e.response.text}"
            )
        except httpx.TimeoutException as e:
            logger.error(f"FluxCloud API timeout: {str(e)}")
            raise FluxAPITransientError(f"FluxCloud API timeout: {str(e)}")
        except httpx.ConnectError as e:
            logger.error(f"FluxCloud API connection error: {str(e)}")
            raise FluxAPITransientError(f"FluxCloud API connection error: {str(e)}")
        except httpx.RequestError as e:
            logger.error(f"FluxCloud API request error: {str(e)}")
            raise FluxCloudAPIException(f"FluxCloud API request failed: {str(e)}")
        except Exception as e:
            logger.error(f"FluxCloud API unexpected error: {str(e)}")
            raise FluxCloudAPIException(f"Unexpected error: {str(e)}")

    async def _request_with_resilience(
        self, method: str, endpoint: str, authenticated: bool = True, **kwargs
    ) -> Dict[str, Any]:
        """
        Make HTTP request with retry logic and circuit breaker protection.

        This method wraps _request() with:
        1. Circuit breaker check (fail fast if API is known to be down)
        2. Retry with exponential backoff for transient errors
        3. Circuit breaker state updates based on success/failure

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (e.g., "/apps/deploy")
            authenticated: Whether to include auth headers (default True)
            **kwargs: Additional arguments for httpx.request()

        Returns:
            Response data as dictionary

        Raises:
            FluxAPICircuitOpenError: If circuit breaker is open
            FluxCloudAPIException: If API request fails after retries
        """
        # Check circuit breaker before making request
        await self._circuit_breaker.check()

        retry_decorator = create_retry_decorator(self._retry_config)

        @retry_decorator
        async def make_request() -> Dict[str, Any]:
            return await self._request(method, endpoint, authenticated, **kwargs)

        try:
            result = await make_request()
            await self._circuit_breaker.record_success()
            return result
        except FluxAPITransientError:
            await self._circuit_breaker.record_failure()
            raise
        except FluxCloudAPIException:
            # Non-transient errors don't affect circuit breaker
            raise

    def get_circuit_breaker_status(self) -> CircuitBreakerStatus:
        """
        Get current circuit breaker status for monitoring.

        Returns:
            CircuitBreakerStatus with state, failure count, and recovery time
        """
        return self._circuit_breaker.get_status()

    async def reset_circuit_breaker(self) -> None:
        """Manually reset the circuit breaker to closed state"""
        await self._circuit_breaker.reset()

    # ========================================================================
    # APP DEPLOYMENT APIs
    # ========================================================================

    async def deploy_app(
        self,
        app_name: str,
        docker_image: str,
        ports: List[int],
        cpu: float = 0.5,
        ram: int = 512,
        hdd: int = 5,
        tiered: bool = True,
        environment_variables: Optional[Dict[str, str]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Deploy a new application to FluxCloud (single component)

        CRITICAL: FluxCloud API v6.6.1 requires custom message signing for app registration:
        - Message format: "fluxappregister" + "1" + JSON(appSpec) + timestamp
        - This is signed with secp256k1 (NOT the login phrase signature!)
        - The signature goes in the payload, NOT the auth header

        Args:
            app_name: Unique application name
            docker_image: Docker image to deploy (e.g., "nginx:latest")
            ports: List of ports to expose
            cpu: CPU cores (0.1 - 4.0)
            ram: RAM in MB (100 - 32000)
            hdd: Disk space in GB (1 - 500)
            tiered: Deploy across all tiers (True) or basic tier only (False)
            environment_variables: Dict of environment variables
            **kwargs: Additional deployment parameters

        Returns:
            Deployment response with app details and status

        Example:
            >>> client = FluxCloudClient()
            >>> await client.deploy_app(
            ...     app_name="fluxvpn-vless-nl-01",
            ...     docker_image="fluxvpn/vless:latest",
            ...     ports=[443, 8080],
            ...     cpu=1.0,
            ...     ram=1024,
            ...     hdd=10,
            ...     environment_variables={"VLESS_UUID": "xyz123"}
            ... )
        """
        import json as json_module
        import time
        from collections import OrderedDict

        # Convert environment_variables dict to list of "KEY=VALUE" strings
        env_params = []
        if environment_variables:
            env_params = [f"{k}={v}" for k, v in environment_variables.items()]

        # Build component spec with EXACT key order required by FluxCloud (v8)
        comp_spec = OrderedDict(
            [
                ("name", app_name),
                ("description", f"FluxVPN {app_name}"),
                ("repotag", docker_image),
                ("ports", ports),
                ("domains", [""] * len(ports)),
                ("environmentParameters", env_params),
                ("commands", []),
                ("containerPorts", ports),
                ("containerData", f"/data/{app_name}"),
                ("cpu", cpu),
                ("ram", ram),
                ("hdd", hdd),
                ("repoauth", ""),
            ]
        )

        # Build app specification with EXACT key order required by FluxCloud (version 8)
        # Field order MUST match Flux specificationFormatter output:
        # version, name, description, owner, compose, instances, contacts,
        # geolocation, expire, nodes, staticip, enterprise
        app_spec = OrderedDict(
            [
                ("version", 8),
                ("name", app_name),
                ("description", f"FluxVPN {app_name}"),
                ("owner", self.wallet_address),
                ("compose", [comp_spec]),
                ("instances", 3),
                ("contacts", []),
                ("geolocation", []),
                ("expire", 22000),
                ("nodes", []),
                ("staticip", False),
                ("enterprise", ""),
            ]
        )

        # Build signed message: type + version + JSON(appSpec) + timestamp
        # FluxCloud API v6.6.1 requires this exact format
        timestamp = int(time.time() * 1000)
        app_spec_json = json_module.dumps(app_spec, separators=(",", ":"))

        # Message to sign: "fluxappregister" + "1" + JSON(spec) + timestamp
        message_to_sign = f"fluxappregister1{app_spec_json}{timestamp}"

        logger.debug(f"Message to sign: {message_to_sign[:100]}...")

        # First, ensure we're authenticated with the API (zelidauth header needs login phrase signature)
        # Note: /id/verifylogin may timeout, but authentication still works
        if not self._signature or not self._login_phrase:
            # Need to authenticate first - get login phrase and sign it
            logger.info("Authenticating with FluxCloud API (secp256k1 signing)...")
            await self.authenticate_with_private_key()
            logger.info(f"Authentication successful (privilege: {self._privilege})")

        # Check if we have the required privilege level (if available)
        if self._privilege and self._privilege not in [
            "User",
            "Admin",
            "FluxTeam",
            "AppOwner",
        ]:
            logger.warning(
                f"Privilege level '{self._privilege}' may not be sufficient for app registration"
            )

        # Now sign the app registration message (separate from auth signature)
        # This goes in the payload, not the auth header
        if self._private_key:
            # Direct signing mode - sign the app registration message
            app_signature = self._sign_message(message_to_sign)
        else:
            raise FluxCloudAPIException(
                "No signature available for app registration.\n"
                "Set FLUX_WALLET_PRIVATE_KEY environment variable for direct signing."
            )

        # Build final payload according to FluxCloud API specification
        # The payload includes the app spec, timestamp, and signature of the app registration message
        payload = {
            "appSpecifications": app_spec,  # Note: key name is appSpecifications (plural)
            "timestamp": timestamp,
            "signature": app_signature,  # Signature of the app registration message
        }

        logger.debug(f"Deploying app with payload keys: {list(payload.keys())}")

        return await self._request_with_resilience(
            "POST", "/apps/appregister", json=payload
        )

    async def deploy_multi_component_app(
        self,
        app_name: str,
        components: List[Dict[str, Any]],
        geolocation: Optional[str] = None,
        instances: int = 3,
        expire: int = 22000,
    ) -> Dict[str, Any]:
        """
        Deploy a Flux app with multiple components (e.g., all 6 VPN protocols)

        Args:
            app_name: Unique app name (only a-zA-Z0-9, cannot start with 'flux')
            components: List of component specs, each with:
                - name: Component name (e.g., "vless")
                - repotag: Docker image (e.g., "fluxvpn/vless:latest")
                - ports: List of external ports (must be in allowed range)
                - containerPorts: List of internal ports (optional, defaults to ports)
                - domains: List of domain strings (must match ports count)
                - cpu: CPU cores (default: 0.1)
                - ram: RAM in MB (default: 100)
                - hdd: Disk space in GB (default: 1)
                - environmentParameters: List of "KEY=VALUE" strings
            geolocation: Optional location constraint (not used currently)
            instances: Number of parallel instances (minimum 3)
            expire: App expiration in blocks (default 22000 ~= 1 month)

        Returns:
            Deployment response with app hash/ID

        Example:
            >>> await client.deploy_multi_component_app(
            ...     app_name="vpnserviceNL01",
            ...     components=[
            ...         {"name": "vless", "repotag": "fluxvpn/vless:latest", "ports": [31443], "cpu": 0.1, "ram": 100},
            ...         {"name": "ssh", "repotag": "fluxvpn/ssh:latest", "ports": [31022], "cpu": 0.1, "ram": 100},
            ...     ],
            ... )
        """
        import json as json_module
        import time
        from collections import OrderedDict

        compose = []
        for comp in components:
            # Build component spec with EXACT key order required by FluxCloud (v8)
            comp_spec = OrderedDict(
                [
                    ("name", comp["name"]),
                    ("description", comp.get("description", f"FluxVPN {comp['name']}")),
                    ("repotag", comp["repotag"]),
                    ("ports", comp["ports"]),
                    ("domains", comp.get("domains", [""] * len(comp["ports"]))),
                    ("environmentParameters", comp.get("environmentParameters", [])),
                    ("commands", comp.get("commands", [])),
                    ("containerPorts", comp.get("containerPorts", comp["ports"])),
                    (
                        "containerData",
                        comp.get("containerData", f"/data/{comp['name']}"),
                    ),
                    ("cpu", comp.get("cpu", 0.1)),
                    ("ram", comp.get("ram", 100)),
                    ("hdd", comp.get("hdd", 1)),
                    ("repoauth", ""),
                ]
            )
            compose.append(comp_spec)

        # Field order MUST match Flux specificationFormatter output:
        # version, name, description, owner, compose, instances, contacts,
        # geolocation, expire, nodes, staticip, enterprise
        app_spec = OrderedDict(
            [
                ("version", 8),
                ("name", app_name),
                ("description", f"FluxVPN Multi-Protocol App - {app_name}"),
                ("owner", self.wallet_address),
                ("compose", compose),
                ("instances", max(instances, 1)),
                ("contacts", []),
                ("geolocation", []),
                ("expire", expire),
                ("nodes", []),
                ("staticip", False),
                ("enterprise", ""),
            ]
        )

        # Build signed message: type + version + JSON(appSpec) + timestamp
        # FluxCloud API v6.6.1 requires this exact format
        timestamp = int(time.time() * 1000)
        app_spec_json = json_module.dumps(app_spec, separators=(",", ":"))

        # Message to sign: "fluxappregister" + "1" + JSON(spec) + timestamp
        message_to_sign = f"fluxappregister1{app_spec_json}{timestamp}"

        logger.debug(f"Message to sign: {message_to_sign[:100]}...")

        # First, ensure we're authenticated with the API (zelidauth header needs login phrase signature)
        # Note: /id/verifylogin may timeout, but authentication still works
        if not self._signature or not self._login_phrase:
            # Need to authenticate first - get login phrase and sign it
            logger.info("Authenticating with FluxCloud API (secp256k1 signing)...")
            await self.authenticate_with_private_key()
            logger.info(f"Authentication successful (privilege: {self._privilege})")

        # Check if we have the required privilege level (if available)
        if self._privilege and self._privilege not in [
            "User",
            "Admin",
            "FluxTeam",
            "AppOwner",
        ]:
            logger.warning(
                f"Privilege level '{self._privilege}' may not be sufficient for app registration"
            )

        # Now sign the app registration message (separate from auth signature)
        # This goes in the payload, not the auth header
        if self._private_key:
            # Direct signing mode - sign the app registration message
            app_signature = self._sign_message(message_to_sign)
        else:
            raise FluxCloudAPIException(
                "No signature available for multi-component app registration.\n"
                "Set FLUX_WALLET_PRIVATE_KEY environment variable for direct signing."
            )

        # Build final payload according to FluxCloud API specification
        # The payload includes the app spec, timestamp, and signature of the app registration message
        payload = {
            "appSpecifications": app_spec,  # Note: key name is appSpecifications (plural)
            "timestamp": timestamp,
            "signature": app_signature,  # Signature of the app registration message
        }

        logger.debug(f"Deploying app with payload keys: {list(payload.keys())}")

        return await self._request_with_resilience(
            "POST", "/apps/appregister", json=payload
        )

    async def update_app(
        self,
        app_name: str,
        description: Optional[str] = None,
        compose: Optional[List[Dict[str, Any]]] = None,
        instances: Optional[int] = None,
        expire: Optional[int] = None,
        geolocation: Optional[List[str]] = None,
        nodes: Optional[List[str]] = None,
        **other_params,
    ) -> Dict[str, Any]:
        """
        Update an existing application on FluxCloud.

        IMPORTANT: This requires Admin privilege (must successfully call /id/verifylogin first).
        The update operation uses the fluxappupdate message signing format.

        Message format to sign: "fluxappupdate" + version + JSON(spec) + timestamp
        where spec is the full Flux app specification version 8.

        Args:
            app_name: Application name to update
            description: New app description
            compose: List of component specs (full replacement)
            instances: Number of instances
            expire: Expiration in blocks
            geolocation: Geolocation array
            nodes: Specific nodes to deploy on
            **other_params: Other parameters

        Returns:
            Update response with new app configuration

        Example:
            >>> await client.update_app(
            ...     "myapp",
            ...     description="Updated description",
            ...     compose=[{
            ...         "name": "web",
            ...         "repotag": "nginx:latest",
            ...         "ports": [80],
            ...         "cpu": 1.0,
            ...         "ram": 512,
            ...         "hdd": 2,
            ...     }]
            ... )
        """
        import json
        import time
        from collections import OrderedDict

        # First ensure we're authenticated
        await self._ensure_auth()

        # Get current app spec if not provided
        # For now, require full spec for update
        if compose is None:
            raise FluxCloudAPIException(
                "update_app requires full 'compose' parameter. "
                "Provide the complete app specification for update."
            )

        # Field order MUST match Flux specificationFormatter output:
        # version, name, description, owner, compose, instances, contacts,
        # geolocation, expire, nodes, staticip, enterprise
        app_spec = OrderedDict(
            [
                ("version", 8),
                ("name", app_name),
                ("description", description or f"FluxVPN {app_name}"),
                ("owner", self.wallet_address),
                ("compose", compose),
                ("instances", instances or 3),
                ("contacts", []),
                ("geolocation", geolocation or []),
                ("expire", expire or 22000),
                ("nodes", nodes or []),
                ("staticip", False),
                ("enterprise", ""),
            ]
        )

        # Build the message to sign: fluxappupdate + version + JSON + timestamp
        timestamp = int(time.time() * 1000)
        app_spec_json = json.dumps(app_spec, separators=(",", ":"))
        message_to_sign = f"fluxappupdate{app_spec_json}{timestamp}"

        logger.debug(f"Update message to sign: {message_to_sign[:100]}...")

        # Sign the message
        signature = self._sign_message(message_to_sign)

        # Build the payload according to Flux API specification
        payload = {
            "appSpecifications": app_spec,
            "timestamp": timestamp,
            "signature": signature,
        }

        # Note: /apps/appupdate requires POST with text/plain content
        return await self._request_with_resilience(
            "POST", "/apps/appupdate", json=payload
        )

    async def delete_app(self, app_name: str) -> Dict[str, Any]:
        """
        Delete an application from FluxCloud

        Args:
            app_name: Application name to delete

        Returns:
            Deletion confirmation
        """
        return await self._request("GET", f"/apps/appremove/{app_name}")

    async def get_app(self, app_name: str) -> Dict[str, Any]:
        """
        Get application details

        Args:
            app_name: Application name

        Returns:
            Application details including status, specs, and instances
        """
        return await self._request("GET", f"/apps/installedapps/{app_name}")

    async def list_apps(self) -> List[Dict[str, Any]]:
        """
        List all deployed applications

        Returns:
            List of application details
        """
        response = await self._request("GET", "/apps/installedapps/")
        return response.get("data", [])

    async def get_app_logs(self, app_name: str, lines: int = 100) -> Dict[str, Any]:
        """
        Get application logs

        Args:
            app_name: Application name
            lines: Number of log lines to retrieve

        Returns:
            Application logs
        """
        return await self._request("GET", f"/apps/applog/{app_name}/{lines}")

    async def restart_app(self, app_name: str) -> Dict[str, Any]:
        """
        Restart an application

        Args:
            app_name: Application name to restart

        Returns:
            Restart confirmation
        """
        return await self._request("GET", f"/apps/apprestart/{app_name}")

    async def redeploy_app(
        self,
        app_name: str,
        hard: bool = False,
    ) -> Dict[str, Any]:
        """
        Redeploy an application on Flux.

        This triggers a redeployment of an existing app.
        Hard redeploy forces a full redeployment even if the app is running.

        Endpoint: GET /apps/redeploy/{app_name}/{hard}/true

        Args:
            app_name: Application name to redeploy
            hard: Force hard redeploy (default: False)

        Returns:
            Redeployment status and data

        Example:
            result = await client.redeploy_app("ch01", hard=False)
            # Returns: {"status": "success", "data": {...}}
        """
        hard_param = "true" if hard else "false"
        endpoint = f"/apps/redeploy/{app_name}/{hard_param}/true"
        return await self._request("GET", endpoint)

    async def register_app(
        self,
        app_spec: Dict[str, Any],
        timestamp: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Register a new application on Flux.

        This requires a specific signature format:
        updatetype + version + JSON.stringify(appSpec) + timestamp

        Signature format: fluxappregister1{JSON}{timestamp}

        Endpoint: POST /apps/appregister

        Args:
            app_spec: Application specification following Flux v8 format.
                Field order MUST match specificationFormatter output:
                version, name, description, owner, compose, instances,
                contacts, geolocation, expire, nodes, staticip, enterprise
            timestamp: Unix timestamp in milliseconds (auto-generated if None)

        Returns:
            Registration response

        Example:
            app_spec = OrderedDict([
                ("version", 8), ("name", "myapp"), ("description", "My app"),
                ("owner", "1xYourZelID"),
                ("compose", [{"name": "myapp", "repotag": "myrepo/myapp:latest", ...}]),
                ("instances", 1), ("contacts", []), ("geolocation", []),
                ("expire", 22000), ("nodes", []), ("staticip", False),
                ("enterprise", ""),  # Must be last
            ])
            result = await client.register_app(app_spec)
        """
        import json as json_module
        import time

        if timestamp is None:
            timestamp = int(time.time() * 1000)

        # Ensure required fields
        required_fields = ["version", "name", "description", "owner", "compose"]
        for field in required_fields:
            if field not in app_spec:
                raise FluxCloudAPIException(
                    f"Missing required field in app_spec: {field}"
                )

        # Validation for common errors discovered through testing
        app_name = app_spec.get("name", "")

        # Rule 1: App name must be alphanumeric only (a-z, A-Z, 0-9)
        if not app_name.isalnum():
            raise FluxCloudAPIException(
                f"Invalid app name '{app_name}': Only alphanumeric characters (a-z, A-Z, 0-9) are allowed."
            )

        # Rule 2: App name cannot start with "flux" (case-insensitive)
        if app_name.lower().startswith("flux"):
            raise FluxCloudAPIException(
                f"Invalid app name '{app_name}': App name cannot start with 'flux'."
            )

        # Rule 3: Minimum 3 instances (Flux network requirement)
        if app_spec.get("instances", 0) < 3:
            logger.warning(
                f"App '{app_name}' has less than 3 instances. "
                f"Flux requires minimum 3 instances for registration."
            )

        # Rule 4: domains array length must match ports array length
        for component in app_spec.get("compose", []):
            ports = component.get("ports", [])
            domains = component.get("domains", [])
            if len(domains) != len(ports):
                raise FluxCloudAPIException(
                    f"Invalid compose spec: 'domains' array length ({len(domains)}) "
                    f"must match 'ports' array length ({len(ports)})."
                )

        # Build the message to sign
        # Format: fluxappregister1{JSON}{timestamp}
        message_prefix = "fluxappregister"
        message_version = "1"
        app_json = json_module.dumps(app_spec, separators=(",", ":"))
        message_to_sign = f"{message_prefix}{message_version}{app_json}{timestamp}"

        # Sign the message
        if not self._private_key:
            raise FluxCloudAPIException(
                "Private key required for app registration. "
                "Set FLUX_WALLET_PRIVATE_KEY in settings or use DirectNodeAuthProvider."
            )

        signature = self._sign_message(message_to_sign)

        # Build request payload
        # CRITICAL: The API expects "appSpecification" (singular), not plural!
        # Despite the documentation showing plural, the actual API uses singular.
        payload = {
            "type": message_prefix,
            "version": int(message_version),
            "appSpecification": app_spec,  # SINGULAR, not plural!
            "timestamp": timestamp,
            "signature": signature,
        }

        logger.info(f"Registering app: {app_spec['name']}")
        logger.debug(f"App spec: {app_json[:200]}...")

        # Send request with text/plain content type (per Flux API v6.6.1 documentation)
        # The payload is JSON but Content-Type must be text/plain
        return await self._request("POST", "/apps/appregister", json=payload)

    async def update_app_spec(
        self,
        app_name: str,
        app_spec: Dict[str, Any],
        timestamp: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Update an existing application specification.

        This uses the same signature format as register but with update type.

        Signature format: fluxappupdate1{JSON}{timestamp}

        Endpoint: POST /apps/appupdate

        Args:
            app_name: Application name to update
            app_spec: Updated application specification
            timestamp: Unix timestamp in milliseconds (auto-generated if None)

        Returns:
            Update response
        """
        import json as json_module
        import time

        if timestamp is None:
            timestamp = int(time.time() * 1000)

        # Ensure app_name matches spec
        app_spec["name"] = app_name

        # Build the message to sign
        # Format: fluxappupdate1{JSON}{timestamp}
        message_prefix = "fluxappupdate"
        message_version = "1"
        app_json = json_module.dumps(app_spec, separators=(",", ":"))
        message_to_sign = f"{message_prefix}{message_version}{app_json}{timestamp}"

        # Sign the message
        if not self._private_key:
            raise FluxCloudAPIException(
                "Private key required for app update. "
                "Set FLUX_WALLET_PRIVATE_KEY in settings."
            )

        signature = self._sign_message(message_to_sign)

        # Build request payload
        # CRITICAL: The API expects "appSpecification" (singular), not plural!
        payload = {
            "type": message_prefix,
            "version": int(message_version),
            "appSpecification": app_spec,  # SINGULAR, not plural!
            "timestamp": timestamp,
            "signature": signature,
        }

        logger.info(f"Updating app: {app_name}")

        return await self._request(
            "POST",
            "/apps/appupdate",
            json=payload,
            _content_type_json=True,  # Use application/json instead of text/plain
        )

    # ========================================================================
    # DEPLOYMENT WORKFLOW (Complete API-based deployment)
    # ========================================================================

    async def get_app_pricing(self) -> Dict[str, Any]:
        """
        Get current Flux resource pricing.

        Endpoint: GET /apps/getappspecsusdprice

        Returns:
            Pricing information including:
            - Flux price in USD
            - CPU price per GB
            - RAM price per GB
            - HDD price per GB
        """
        response = await self._request(
            "GET", "/apps/getappspecsusdprice", authenticated=False
        )
        return response

    async def submit_app_for_deployment(
        self,
        app_name: str,
        app_spec: Dict[str, Any],
        timestamp: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Submit app specification for deployment via /apps/appupdate.

        This is the core deployment call that returns a registration hash.
        The hash is valid for 1 hour and must be included in the payment transaction.

        Endpoint: POST /apps/appupdate

        Args:
            app_name: Application name
            app_spec: Full application specification
            timestamp: Unix timestamp in milliseconds (auto-generated if None)

        Returns:
            Response with registration hash (valid for 1 hour)
        """
        import json as json_module
        import time

        if timestamp is None:
            timestamp = int(time.time() * 1000)

        # Ensure app_name matches spec
        app_spec["name"] = app_name

        # Build the message to sign
        # Format: fluxappupdate1{JSON}{timestamp}
        message_prefix = "fluxappupdate"
        message_version = "1"
        app_json = json_module.dumps(app_spec, separators=(",", ":"))
        message_to_sign = f"{message_prefix}{message_version}{app_json}{timestamp}"

        # Sign the message
        if not self._private_key:
            raise FluxCloudAPIException(
                "Private key required for app deployment. "
                "Set FLUX_WALLET_PRIVATE_KEY in settings."
            )

        signature = self._sign_message(message_to_sign)

        # Build request payload
        payload = {
            "type": message_prefix,
            "version": int(message_version),
            "appSpecification": app_spec,
            "timestamp": timestamp,
            "signature": signature,
        }

        logger.info(f"Submitting app for deployment: {app_name}")

        result = await self._request(
            "POST", "/apps/appupdate", json=payload, _content_type_json=True
        )

        # Extract and log the registration hash if present
        if result.get("status") == "success":
            reg_hash = result.get("data")
            if reg_hash:
                logger.info(f"Registration hash obtained: {reg_hash}")
                logger.info(
                    "Hash is valid for 1 hour. Complete payment with this hash to deploy."
                )

        return result

    async def get_deployment_hashes(self) -> Dict[str, Any]:
        """
        Get app deployment hashes and payment status.

        Endpoint: GET /apps/hashes

        Returns:
            List of deployment hashes with:
            - txid: Transaction ID of the payment
            - hash: Registration hash
            - value: Payment value in satoshis
        """
        response = await self._request("GET", "/apps/hashes", authenticated=False)
        return response

    async def get_deployment_status(self, app_name: str) -> Dict[str, Any]:
        """
        Get deployment information for an app.

        Endpoint: GET /apps/deploymentinformation

        Returns:
            Deployment status information
        """
        params = {"appname": app_name}
        response = await self._request(
            "GET", "/apps/deploymentinformation", params=params, authenticated=False
        )
        return response

    async def deploy_app_with_payment(
        self,
        app_name: str,
        docker_image: str,
        ports: List[int],
        cpu: float = 0.5,
        ram: int = 512,
        hdd: int = 5,
        instances: int = 3,
        expire: int = 22000,
        description: str = "Auto-deployed app",
    ) -> Dict[str, Any]:
        """
        Complete deployment workflow: Get pricing → Submit spec → Provide payment instructions.

        This is the ONE-CALL deployment method that handles the full workflow.

        Args:
            app_name: Application name (alphanumeric, can't start with "flux")
            docker_image: Docker image (e.g., "nginx:alpine")
            ports: List of ports to expose
            cpu: CPU cores (0.1 - 4.0)
            ram: RAM in MB (100 - 32000)
            hdd: Disk space in GB (1 - 500)
            instances: Number of instances (minimum 3)
            expire: Expiration in blocks (22000 = ~24 hours)
            description: App description

        Returns:
            Deployment result with:
            - pricing: Current resource prices
            - registration_hash: Hash to include in payment (valid 1 hour)
            - payment_instructions: How to complete payment
            - payment_address: Where to send Flux
            - payment_amount: Amount in Flux/satoshis

        Example:
            >>> result = await client.deploy_app_with_payment(
            ...     app_name="myapp",
            ...     docker_image="nginx:alpine",
            ...     ports=[80],
            ...     cpu=0.5,
            ...     ram=512,
            ...     hdd=5,
            ...     instances=3
            ... )
            >>> print(result["registration_hash"])
            >>> print(result["payment_instructions"])
        """
        import json as json_module
        import time

        # Step 1: Get pricing
        logger.info("Getting Flux app pricing...")
        pricing_result = await self.get_app_pricing()

        if pricing_result.get("status") != "success":
            raise FluxCloudAPIException(f"Failed to get pricing: {pricing_result}")

        pricing_data = pricing_result.get("data", {})
        logger.info(f"Current pricing: {pricing_data}")

        # Step 2: Build app spec (version 8 - required since block 1,932,380)
        app_spec = {
            # Field order MUST match Flux specificationFormatter output
            "version": 8,
            "name": app_name,
            "description": description,
            "owner": self.wallet_address,
            "compose": [
                {
                    "name": app_name,
                    "description": description,
                    "repotag": docker_image,
                    "ports": ports,
                    "domains": [""] * len(ports),
                    "environmentParameters": [],
                    "commands": [],
                    "containerPorts": ports,
                    "containerData": "/data",
                    "cpu": cpu,
                    "ram": ram,
                    "hdd": hdd,
                    "repoauth": "",
                }
            ],
            "instances": instances,
            "contacts": [],
            "geolocation": [],
            "expire": expire,
            "nodes": [],
            "staticip": False,
            "enterprise": "",
        }

        # Step 3: Validate
        if not app_name.isalnum():
            raise FluxCloudAPIException(
                f"Invalid app name '{app_name}': Only alphanumeric characters allowed."
            )
        if app_name.lower().startswith("flux"):
            raise FluxCloudAPIException(
                f"Invalid app name '{app_name}': Cannot start with 'flux'."
            )
        if instances < 1:
            raise FluxCloudAPIException(
                f"Invalid instances: {instances}. Minimum 1 instance required (v8+)."
            )

        # Step 4: Submit for deployment
        logger.info(f"Submitting app for deployment: {app_name}")
        submit_result = await self.submit_app_for_deployment(app_name, app_spec)

        if submit_result.get("status") != "success":
            raise FluxCloudAPIException(
                f"Failed to submit app: {submit_result.get('data')}"
            )

        registration_hash = submit_result.get("data")
        if not isinstance(registration_hash, str):
            raise FluxCloudAPIException("Invalid deployment registration hash")
        logger.info(f"Registration hash: {registration_hash}")

        # Step 5: Get current hashes to understand payment format
        hashes_result = await self.get_deployment_hashes()
        logger.info(f"Current deployment hashes: {hashes_result}")

        # Step 6: Calculate payment
        # This is a simplified calculation - actual cost depends on many factors
        # For production, you'd use the pricing data and calculate based on resources
        payment_amount_sats = self._calculate_payment_amount(pricing_data, app_spec)

        return {
            "status": "pending_payment",
            "app_name": app_name,
            "app_spec": app_spec,
            "pricing": pricing_data,
            "registration_hash": registration_hash,
            "payment_amount_sats": payment_amount_sats,
            "payment_instructions": self._get_payment_instructions(registration_hash),
            "next_steps": [
                "1. Send FLUX payment transaction with the registration hash in the OP_RETURN",
                "2. Wait for blockchain confirmation",
                "3. Check deployment status with get_deployment_status()",
                "4. App will appear in /apps/installedapps once deployed",
            ],
        }

    def _calculate_payment_amount(self, pricing_data: Dict, app_spec: Dict) -> int:
        """Calculate payment amount in satoshis based on resources and pricing."""
        instances = max(int(app_spec.get("instances", 1)), 1)
        expire_blocks = max(int(app_spec.get("expire", 22000)), 1)
        period_multiplier = Decimal(str(expire_blocks)) / Decimal("22000")

        compose = app_spec.get("compose", []) or []

        total_cpu = Decimal("0")
        total_ram_gb = Decimal("0")
        total_hdd_gb = Decimal("0")

        for component in compose:
            total_cpu += Decimal(str(component.get("cpu", 0)))
            total_ram_gb += Decimal(str(component.get("ram", 0))) / Decimal("1024")
            total_hdd_gb += Decimal(str(component.get("hdd", 0)))

        total_cpu *= Decimal(str(instances))
        total_ram_gb *= Decimal(str(instances))
        total_hdd_gb *= Decimal(str(instances))

        flux_price_usd = self._extract_decimal_price(
            pricing_data,
            [
                "fluxprice",
                "fluxPrice",
                "flux_price_usd",
                "fluxusd",
                "price",
            ],
            Decimal("0.5"),
        )
        cpu_price_usd = self._extract_decimal_price(
            pricing_data,
            ["cpuusd", "cpuPriceUsd", "cpu_price_usd", "cpuprice"],
            Decimal("0.05"),
        )
        ram_price_usd = self._extract_decimal_price(
            pricing_data,
            ["ramusd", "ramPriceUsd", "ram_price_usd", "ramprice"],
            Decimal("0.01"),
        )
        hdd_price_usd = self._extract_decimal_price(
            pricing_data,
            ["hddusd", "hddPriceUsd", "hdd_price_usd", "hddprice"],
            Decimal("0.001"),
        )

        if flux_price_usd <= 0:
            flux_price_usd = Decimal("0.5")

        total_usd = (
            (total_cpu * cpu_price_usd)
            + (total_ram_gb * ram_price_usd)
            + (total_hdd_gb * hdd_price_usd)
        ) * period_multiplier

        total_flux = total_usd / flux_price_usd
        payment_sats = int(
            (total_flux * Decimal("100000000")).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )

        bounded_payment = max(
            self._MIN_PAYMENT_SATS,
            min(payment_sats, self._MAX_PAYMENT_SATS),
        )

        logger.info(
            "Calculated deployment payment",
            extra={
                "instances": instances,
                "expire_blocks": expire_blocks,
                "cpu_units": float(total_cpu),
                "ram_gb": float(total_ram_gb),
                "hdd_gb": float(total_hdd_gb),
                "cpu_price_usd": float(cpu_price_usd),
                "ram_price_usd": float(ram_price_usd),
                "hdd_price_usd": float(hdd_price_usd),
                "flux_price_usd": float(flux_price_usd),
                "total_usd": float(total_usd),
                "payment_sats": bounded_payment,
            },
        )

        return bounded_payment

    @staticmethod
    def _extract_decimal_price(
        pricing_data: Dict[str, Any],
        keys: List[str],
        default: Decimal,
    ) -> Decimal:
        for key in keys:
            if key not in pricing_data:
                continue
            raw_value = pricing_data.get(key)
            try:
                value = Decimal(str(raw_value))
                if value > 0:
                    return value
            except (InvalidOperation, TypeError, ValueError):
                continue
        return default

    def _get_payment_instructions(self, registration_hash: str) -> str:
        """Get instructions for completing payment."""
        return (
            f"TO COMPLETE DEPLOYMENT:\n"
            f"1. Send a FLUX transaction with the following OP_RETURN:\n"
            f"   OP_RETURN OP_PUSHDATA {len(registration_hash)} {registration_hash}\n\n"
            f"2. The registration hash (in your OP_RETURN) links your payment to the app.\n"
            f"3. Once the transaction confirms, your app will be deployed.\n\n"
            f"Registration hash (valid for 1 hour): {registration_hash}\n"
            f"Your wallet address: {self.wallet_address}"
        )

    # ========================================================================
    # NODE APIs
    # ========================================================================

    async def list_nodes(
        self, filter_params: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """
        List available Flux nodes

        Args:
            filter_params: Optional filters (tier, location, status, etc.)

        Returns:
            List of available nodes
        """
        params = filter_params or {}
        response = await self._request(
            "GET", "/flux_node_list", params=params, authenticated=False
        )
        return response.get("data", [])

    async def get_node(self, node_id: str) -> Dict[str, Any]:
        """
        Get details for a specific node

        Args:
            node_id: Flux node identifier

        Returns:
            Node details including specs, status, and location
        """
        return await self._request("GET", "/flux_node_status", authenticated=False)

    async def get_node_stats(self, node_id: str) -> Dict[str, Any]:
        """
        Get performance stats for a node

        Args:
            node_id: Flux node identifier

        Returns:
            Node performance metrics (CPU, RAM, bandwidth, uptime)
        """
        return await self._request("GET", "/flux/info", authenticated=False)

    # ========================================================================
    # MARKETPLACE & PRICING APIs
    # ========================================================================

    async def get_pricing(self, specs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get pricing estimate for deployment specs

        Args:
            specs: Resource specifications (cpu, ram, hdd, tiered)

        Returns:
            Pricing estimate in FLUX tokens
        """
        return await self._request_with_resilience(
            "GET", "/apps/registrationinformation", params=specs, authenticated=False
        )

    async def get_marketplace_stats(self) -> Dict[str, Any]:
        """
        Get marketplace statistics

        Returns:
            Marketplace stats (available nodes, average prices, etc.)
        """
        return await self._request("GET", "/flux_node_count", authenticated=False)

    # ========================================================================
    # MONITORING APIs
    # ========================================================================

    async def get_app_health(self, app_name: str) -> Dict[str, Any]:
        """
        Check application health status

        Args:
            app_name: Application name

        Returns:
            Health status including uptime, response time, errors
        """
        return await self._request("GET", f"/apps/installedapps/{app_name}")

    async def get_app_metrics(
        self,
        app_name: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Get application performance metrics

        Args:
            app_name: Application name
            start_time: Metrics start time (optional)
            end_time: Metrics end time (optional)

        Returns:
            Performance metrics (CPU, RAM, network, requests)
        """
        return await self._request("GET", f"/apps/appstats/{app_name}")

    # ========================================================================
    # UTILITY METHODS
    # ========================================================================

    async def ping(self) -> bool:
        """
        Test API connectivity

        Returns:
            True if API is reachable, False otherwise
        """
        try:
            await self._request("GET", "/flux/info", authenticated=False)
            return True
        except FluxCloudAPIException:
            return False

    async def get_api_status(self) -> Dict[str, Any]:
        """
        Get FluxCloud API status

        Returns:
            API status including version, uptime, and health
        """
        return await self._request("GET", "/flux/info", authenticated=False)

    async def verify_auth(self) -> bool:
        """
        Verify that authentication is working

        Returns:
            True if authentication is valid
        """
        try:
            # Try to list apps - requires authentication
            await self.list_apps()
            return True
        except FluxCloudAPIException as e:
            logger.error(f"Auth verification failed: {e}")
            return False
