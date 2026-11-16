"""
Deployment Token Service
Generates and validates bootstrap tokens for FluxCloud container deployments

This service ensures only FluxVPN-authorized deployments can run our Docker containers,
even though the images are public on Docker Hub.
"""

import base64
import hashlib
import hmac
import json
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class DeploymentTokenError(Exception):
    """Base exception for deployment token errors"""

    pass


class TokenExpiredError(DeploymentTokenError):
    """Token has expired"""

    pass


class TokenInvalidError(DeploymentTokenError):
    """Token signature is invalid"""

    pass


class TokenMalformedError(DeploymentTokenError):
    """Token format is invalid"""

    pass


@dataclass
class DeploymentTokenPayload:
    """Token payload structure"""

    deployment_id: str
    protocol: str
    instance_id: str
    created_at: str
    expires_at: str
    nonce: str


class DeploymentTokenService:
    """
    Service for generating and validating deployment bootstrap tokens

    Token Format:
        BASE64(JSON_PAYLOAD).HMAC_SHA256_SIGNATURE

    Token Payload:
        {
            "deployment_id": "uuid",
            "protocol": "shadowsocks",
            "instance_id": "fluxvpn-ss-nl-01",
            "created_at": "2024-01-15T10:30:00Z",
            "expires_at": "2024-01-15T11:30:00Z",
            "nonce": "random-32-bytes"
        }
    """

    def __init__(self, secret_key: Optional[str] = None):
        """
        Initialize the token service

        Args:
            secret_key: HMAC secret key. If not provided, uses FLUXVPN_SECRET_KEY from settings.
        """
        configured_secret_key = secret_key or getattr(
            settings, "FLUXVPN_SECRET_KEY", None
        )
        if not configured_secret_key:
            raise ValueError(
                "FLUXVPN_SECRET_KEY must be configured for deployment tokens"
            )
        self.secret_key: str = configured_secret_key

        # Default token expiry (1 hour for bootstrap)
        self.default_expiry_seconds = getattr(settings, "DEPLOYMENT_TOKEN_EXPIRY", 3600)

    def generate_token(
        self,
        deployment_id: str,
        protocol: str,
        instance_id: str,
        expiry_seconds: Optional[int] = None,
    ) -> str:
        """
        Generate a signed deployment token

        Args:
            deployment_id: Unique deployment identifier
            protocol: Protocol type (shadowsocks, trojan, vless, etc.)
            instance_id: FluxCloud instance identifier
            expiry_seconds: Token validity period (default: 1 hour)

        Returns:
            Signed token string (BASE64.SIGNATURE format)
        """
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        expiry = expiry_seconds or self.default_expiry_seconds

        payload = {
            "deployment_id": deployment_id,
            "protocol": protocol,
            "instance_id": instance_id,
            "created_at": now.isoformat() + "Z",
            "expires_at": (now + timedelta(seconds=expiry)).isoformat() + "Z",
            "nonce": secrets.token_hex(16),  # 32 hex chars = 16 bytes
        }

        # Encode payload
        payload_json = json.dumps(payload, separators=(",", ":"))
        payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode()

        # Generate HMAC signature
        signature = self._sign(payload_b64)

        token = f"{payload_b64}.{signature}"

        logger.info(
            f"Generated deployment token for {instance_id} "
            f"(protocol={protocol}, expires_at={payload['expires_at']})"
        )

        return token

    def validate_token(
        self, token: str, expected_instance_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validate a deployment token

        Args:
            token: The token to validate
            expected_instance_id: Optional instance ID to verify

        Returns:
            Token payload if valid

        Raises:
            TokenMalformedError: If token format is invalid
            TokenInvalidError: If signature verification fails
            TokenExpiredError: If token has expired
        """
        # Split token into payload and signature
        try:
            parts = token.split(".")
            if len(parts) != 2:
                raise TokenMalformedError(
                    "Token must contain exactly one period separator"
                )

            payload_b64, signature = parts
        except Exception as e:
            raise TokenMalformedError(f"Invalid token format: {e}")

        # Verify signature
        expected_signature = self._sign(payload_b64)
        if not hmac.compare_digest(signature, expected_signature):
            logger.warning("Token signature verification failed")
            raise TokenInvalidError("Token signature is invalid")

        # Decode payload
        try:
            payload_json = base64.urlsafe_b64decode(payload_b64.encode()).decode()
            payload = json.loads(payload_json)
        except Exception as e:
            raise TokenMalformedError(f"Invalid payload encoding: {e}")

        # Validate required fields
        required_fields = [
            "deployment_id",
            "protocol",
            "instance_id",
            "created_at",
            "expires_at",
            "nonce",
        ]
        for field in required_fields:
            if field not in payload:
                raise TokenMalformedError(f"Missing required field: {field}")

        # Check expiration
        try:
            expires_at = datetime.fromisoformat(payload["expires_at"].rstrip("Z"))
            if datetime.now(timezone.utc).replace(tzinfo=None) > expires_at:
                raise TokenExpiredError(f"Token expired at {payload['expires_at']}")
        except ValueError as e:
            raise TokenMalformedError(f"Invalid expiration timestamp: {e}")

        # Verify instance ID if provided
        if expected_instance_id and payload["instance_id"] != expected_instance_id:
            logger.warning(
                f"Instance ID mismatch: expected={expected_instance_id}, "
                f"got={payload['instance_id']}"
            )
            raise TokenInvalidError("Instance ID does not match")

        logger.info(f"Successfully validated token for {payload['instance_id']}")

        return payload

    def _sign(self, data: str) -> str:
        """
        Generate HMAC-SHA256 signature

        Args:
            data: Data to sign

        Returns:
            Base64-encoded signature
        """
        signature = hmac.new(
            self.secret_key.encode(), data.encode(), hashlib.sha256
        ).digest()

        return base64.urlsafe_b64encode(signature).decode().rstrip("=")

    def _derive_secret(self, protocol: str, instance_id: str, length: int = 32) -> str:
        """
        Derive a deterministic per-instance secret.

        The value is stable across restarts while keeping instance-level isolation.
        """
        seed = f"{protocol}:{instance_id}".encode()
        digest = hmac.new(self.secret_key.encode(), seed, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).decode().rstrip("=")[:length]

    def _normalize_protocol(self, protocol: str) -> str:
        """
        Normalize protocol aliases used across deployment and credential paths.
        """
        normalized = protocol.lower().replace("-", "_")
        aliases = {
            "httpproxy": "http_proxy",
        }
        return aliases.get(normalized, normalized)

    def get_protocol_config(
        self, protocol: str, instance_id: str, deployment_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get protocol-specific configuration for a validated deployment

        Args:
            protocol: Protocol type
            instance_id: Instance identifier
            deployment_id: Deployment identifier (used for shared password derivation)

        Returns:
            Configuration dictionary for the protocol
        """
        protocol_key = self._normalize_protocol(protocol)

        # Base configuration common to all protocols
        base_config: Dict[str, Any] = {
            "log_level": "info",
            "health_check_port": 8080,
            "metrics_enabled": True,
        }

        # Protocol-specific configurations
        protocol_configs: Dict[str, Dict[str, Any]] = {
            "shadowsocks": {
                "method": "chacha20-ietf-poly1305",
                "timeout": 300,
                "fast_open": True,
                "mode": "tcp_and_udp",
            },
            "trojan": {
                "ssl": True,
                "alpn": ["h2", "http/1.1"],
                "tcp_fast_open": True,
            },
            "vless": {
                "encryption": "none",
                "network": "ws",
                "flow": "",
            },
            "ssh": {
                "permit_root_login": False,
                "password_auth": True,
                "max_auth_tries": 3,
            },
            "outline": {
                "method": "chacha20-ietf-poly1305",
                "metrics_port": 8081,
            },
            "http_proxy": {
                "cache_enabled": False,
                "max_connections": 256,
                "timeout": 60,
            },
        }

        # Runtime service parameters expected by protocol start scripts.
        # SS/Outline: deployment-level shared password (protocol only supports one password per port)
        # Other protocols: per-instance derived credentials
        if protocol_key in ("shadowsocks", "outline") and deployment_id:
            seed = f"shared:{protocol_key}:{deployment_id}".encode()
            digest = hmac.new(self.secret_key.encode(), seed, hashlib.sha256).digest()
            derived_password = (
                base64.urlsafe_b64encode(digest).decode().rstrip("=")[:32]
            )
        else:
            derived_password = self._derive_secret(protocol_key, instance_id, length=32)

        derived_username = (
            f"user_{self._derive_secret(protocol_key, instance_id, length=10).lower()}"
        )
        derived_uuid = str(
            uuid.uuid5(uuid.NAMESPACE_DNS, f"{self.secret_key}:{instance_id}:vless")
        )
        runtime_params: Dict[str, Dict[str, Any]] = {
            "shadowsocks": {
                "password": derived_password,
                "port": 8388,
            },
            "trojan": {
                "password": derived_password,
                "port": 8443,
                "sni": "operator7.example.invalid",
            },
            "vless": {
                "uuid": derived_uuid,
                "port": 443,
                "path": "/vless",
            },
            "ssh": {
                "username": derived_username,
                "password": derived_password,
                "port": 2222,
            },
            "outline": {
                "password": derived_password,
                "port": 9443,
            },
            "http_proxy": {
                "username": derived_username,
                "password": derived_password,
                "port": 3128,
            },
        }

        config = {
            **base_config,
            **protocol_configs.get(protocol_key, {}),
            **runtime_params.get(protocol_key, {}),
            "protocol": protocol_key,
            "instance_id": instance_id,
        }

        return config


# Convenience functions for direct usage
def generate_deployment_token(
    deployment_id: str,
    protocol: str,
    instance_id: str,
    expiry_seconds: Optional[int] = None,
) -> str:
    """
    Generate a deployment token (convenience wrapper)

    See DeploymentTokenService.generate_token for details.
    """
    service = DeploymentTokenService()
    return service.generate_token(deployment_id, protocol, instance_id, expiry_seconds)


def validate_deployment_token(
    token: str, expected_instance_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Validate a deployment token (convenience wrapper)

    See DeploymentTokenService.validate_token for details.
    """
    service = DeploymentTokenService()
    return service.validate_token(token, expected_instance_id)
