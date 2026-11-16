"""
Security utilities for FluxVPN Worker API

Provides authentication dependencies for FastAPI routes:
- Internal API key auth (for service-to-service communication)
- JWT auth (for user authentication)
"""

import logging
from typing import Optional

from fastapi import Depends, Header, HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)


async def verify_internal_api_key(
    x_internal_api_key: Optional[str] = Header(None, alias="X-Internal-API-Key")
) -> bool:
    """
    Verify internal API key for service-to-service authentication.

    This protects internal endpoints from unauthorized access when
    the Docker image is deployed publicly.

    Usage in routes:
        @router.post("/internal/endpoint")
        async def internal_endpoint(
            _: bool = Depends(verify_internal_api_key)
        ):
            ...

    Headers required:
        X-Internal-API-Key: <your-internal-api-key>

    Raises:
        HTTPException 401: If INTERNAL_API_KEY is not configured
        HTTPException 403: If the provided key doesn't match
    """
    # If INTERNAL_API_KEY is not set, reject all requests
    if not settings.INTERNAL_API_KEY:
        if settings.ENVIRONMENT != "development":
            logger.error("INTERNAL_API_KEY not configured in non-dev environment!")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Internal authentication not configured",
            )
        # In development, allow requests without key (for easier testing)
        logger.warning("INTERNAL_API_KEY not set - allowing request in dev mode")
        return True

    # Verify the key
    if not x_internal_api_key:
        logger.warning("Request missing X-Internal-API-Key header")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Missing internal API key"
        )

    if x_internal_api_key != settings.INTERNAL_API_KEY:
        logger.warning("Invalid internal API key provided")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid internal API key"
        )

    return True


async def verify_internal_api_key_optional(
    x_internal_api_key: Optional[str] = Header(None, alias="X-Internal-API-Key")
) -> bool:
    """
    Optional internal API key verification.

    Returns True if:
    - Key is valid
    - Key is not configured (development mode)

    Returns False if:
    - Key is configured but not provided/invalid

    Use this for endpoints that should work both internally and externally
    but with different behavior.
    """
    if not settings.INTERNAL_API_KEY:
        return True

    if not x_internal_api_key:
        return False

    return x_internal_api_key == settings.INTERNAL_API_KEY
