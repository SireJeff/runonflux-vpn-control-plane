"""
Node Management and Deployment Validation Endpoints

Handles FluxCloud node operations and container deployment authentication.
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.auth.deployment_tokens import (
    DeploymentTokenError,
    DeploymentTokenService,
    TokenExpiredError,
    TokenInvalidError,
    TokenMalformedError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nodes", tags=["Nodes"])


# ============================================================================
# REQUEST/RESPONSE SCHEMAS
# ============================================================================


class ValidateDeploymentRequest(BaseModel):
    """Request to validate a deployment token"""

    token: str = Field(..., description="Deployment bootstrap token")
    instance_id: str = Field(..., description="FluxCloud instance identifier")


class ValidateDeploymentResponse(BaseModel):
    """Response for successful deployment validation"""

    valid: bool
    protocol: str
    instance_id: str
    deployment_id: str
    config: Dict[str, Any]
    internal_api_key: str = ""


class ValidationErrorResponse(BaseModel):
    """Response for failed deployment validation"""

    valid: bool = False
    error: str


# ============================================================================
# DEPLOYMENT VALIDATION ENDPOINTS
# ============================================================================


@router.post(
    "/validate-deployment",
    response_model=ValidateDeploymentResponse,
    responses={
        400: {
            "model": ValidationErrorResponse,
            "description": "Invalid or expired token",
        },
        401: {
            "model": ValidationErrorResponse,
            "description": "Token signature invalid",
        },
        503: {
            "model": ValidationErrorResponse,
            "description": "Token service unavailable",
        },
    },
)
async def validate_deployment(request: ValidateDeploymentRequest):
    """
    Validate a deployment bootstrap token

    Called by FluxCloud containers at startup to verify they are
    authorized FluxVPN deployments. Returns protocol configuration
    if the token is valid.

    **Security:**
    - Token must be signed with FLUXVPN_SECRET_KEY
    - Token must not be expired (default: 1 hour window)
    - Instance ID must match token payload

    **Used by:**
    - Container entrypoint scripts (entrypoint-wrapper.sh)
    - Protocol-specific Docker images

    **Returns:**
    - Protocol configuration if valid
    - Error message if invalid/expired
    """
    logger.info(f"Validating deployment token for instance: {request.instance_id}")

    # Check if deployment tokens are configured
    if not settings.FLUXVPN_SECRET_KEY:
        logger.error("FLUXVPN_SECRET_KEY not configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "valid": False,
                "error": "Deployment validation service not configured",
            },
        )

    try:
        service = DeploymentTokenService()
        payload = service.validate_token(request.token, request.instance_id)

        # Get protocol-specific configuration
        config = service.get_protocol_config(
            payload["protocol"],
            payload["instance_id"],
            deployment_id=payload["deployment_id"],
        )

        logger.info(
            f"Deployment validated: {payload['instance_id']} "
            f"(protocol={payload['protocol']}, deployment={payload['deployment_id']})"
        )

        return ValidateDeploymentResponse(
            valid=True,
            protocol=payload["protocol"],
            instance_id=payload["instance_id"],
            deployment_id=payload["deployment_id"],
            config=config,
            internal_api_key=settings.INTERNAL_API_KEY or "",
        )

    except TokenExpiredError as e:
        logger.warning(f"Token expired for instance {request.instance_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"valid": False, "error": f"Token expired: {str(e)}"},
        )

    except TokenInvalidError as e:
        logger.warning(f"Invalid token for instance {request.instance_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"valid": False, "error": f"Token invalid: {str(e)}"},
        )

    except TokenMalformedError as e:
        logger.warning(f"Malformed token for instance {request.instance_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"valid": False, "error": f"Token malformed: {str(e)}"},
        )

    except DeploymentTokenError as e:
        logger.error(f"Token validation error for instance {request.instance_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"valid": False, "error": str(e)},
        )

    except Exception as e:
        logger.exception(f"Unexpected error validating deployment: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"valid": False, "error": "Internal server error"},
        )


@router.get("/health")
async def nodes_health():
    """
    Health check endpoint for the nodes service

    Used by monitoring systems to verify the deployment
    validation service is operational.
    """
    token_service_available = bool(settings.FLUXVPN_SECRET_KEY)

    return {
        "status": "healthy" if token_service_available else "degraded",
        "token_service": "available" if token_service_available else "not_configured",
        "message": (
            "Nodes service operational"
            if token_service_available
            else "FLUXVPN_SECRET_KEY not set"
        ),
    }
