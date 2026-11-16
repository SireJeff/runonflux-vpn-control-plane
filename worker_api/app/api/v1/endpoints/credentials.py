"""
VPN Credential Generation and Management endpoints
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models import Protocol, ProtocolInstance, Subscription, User, UserCredential
from app.schemas import SuccessResponse
from app.services.credentials import CredentialService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/credentials", tags=["Credentials"])


# ============================================================================
# REQUEST/RESPONSE SCHEMAS
# ============================================================================


class CredentialCreate(BaseModel):
    """Request to generate new credential"""

    subscription_id: int = Field(
        ..., gt=0, description="Subscription ID to create credential for"
    )
    preferred_country: Optional[str] = Field(
        None, description="Preferred country code (NL, US, DE, SG, GB)"
    )


class CredentialResponse(BaseModel):
    """VPN credential response"""

    id: int
    user_id: int
    protocol_id: int
    protocol_name: str
    subscription_id: int
    server: str
    server_domain: Optional[str] = None
    port: int
    server_location: Optional[str] = None
    country_code: Optional[str] = None
    credential_data: Dict[str, Any]
    created_at: datetime
    updated_at: Optional[datetime] = None

    # Connection info
    connection_uri: Optional[str] = None
    qr_code_data: Optional[str] = None
    download_links: Optional[Dict[str, str]] = None

    model_config = ConfigDict(from_attributes=True)


class CredentialConfigResponse(BaseModel):
    """Credential configuration file response"""

    credential_id: int
    protocol: str
    config_type: str  # clash, v2ray, ssh, etc.
    config_content: str
    filename: str


class ConnectionGuideResponse(BaseModel):
    """Connection guide for a credential"""

    credential_id: int
    protocol: str
    platform: str  # windows, macos, linux, android, ios
    steps: List[str]
    app_download_url: Optional[str]
    config_instructions: str


# ============================================================================
# CREDENTIAL GENERATION
# ============================================================================


@router.post("", response_model=CredentialResponse, status_code=status.HTTP_201_CREATED)
async def generate_credential(
    request: CredentialCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generate VPN credential for a subscription

    **Flow:**
    1. Verify subscription belongs to user and is active
    2. Select optimal protocol instance (based on preferred country or load balancing)
    3. Generate protocol-specific credentials
    4. Create credential record with JSONB data
    5. Return connection details

    **Automatic Features:**
    - Load balancing across instances
    - Geographic preference support
    - Protocol-specific credential generation (URIs, configs)
    """
    logger.info(
        f"User {current_user.id} generating credential for subscription {request.subscription_id}"
    )

    # Get subscription
    subscription = (
        db.query(Subscription)
        .filter_by(id=request.subscription_id, user_id=current_user.id)
        .first()
    )

    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found"
        )

    # Use CredentialService for generation
    service = CredentialService(db)

    try:
        credential = service.generate_credential(
            user=current_user,
            subscription=subscription,
            preferred_country=request.preferred_country,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Get full credential details
    cred_details = service.get_credential_with_details(credential)

    logger.info(
        f"Credential {credential.id} generated successfully for user {current_user.id}"
    )

    return CredentialResponse(
        id=credential.id,
        user_id=credential.user_id,
        protocol_id=credential.protocol_id,
        protocol_name=cred_details["protocol_name"],
        subscription_id=credential.subscription_id,
        server=cred_details["server"],
        server_domain=cred_details.get("server_domain"),
        port=cred_details["port"],
        server_location=credential.server_location,
        country_code=cred_details.get("country_code"),
        credential_data=credential.credential_data,
        created_at=credential.created_at,
        updated_at=credential.updated_at,
        connection_uri=cred_details.get("connection_uri"),
        qr_code_data=cred_details.get("qr_code_data"),
        download_links=cred_details.get("download_links"),
    )


@router.get("", response_model=List[CredentialResponse])
async def list_credentials(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    protocol_id: Optional[int] = None,
):
    """
    List user's VPN credentials

    Filter by protocol if specified.
    """
    query = db.query(UserCredential).filter_by(user_id=current_user.id)

    if protocol_id:
        query = query.filter(UserCredential.protocol_id == protocol_id)

    credentials = query.order_by(UserCredential.created_at.desc()).all()

    service = CredentialService(db)
    result = []

    for cred in credentials:
        try:
            cred_details = service.get_credential_with_details(cred)
            result.append(
                CredentialResponse(
                    id=cred.id,
                    user_id=cred.user_id,
                    protocol_id=cred.protocol_id,
                    protocol_name=cred_details["protocol_name"],
                    subscription_id=cred.subscription_id,
                    server=cred_details["server"],
                    server_domain=cred_details.get("server_domain"),
                    port=cred_details["port"],
                    server_location=cred.server_location,
                    country_code=cred_details.get("country_code"),
                    credential_data=cred.credential_data,
                    created_at=cred.created_at,
                    updated_at=cred.updated_at,
                    connection_uri=cred_details.get("connection_uri"),
                    qr_code_data=cred_details.get("qr_code_data"),
                    download_links=cred_details.get("download_links"),
                )
            )
        except Exception as e:
            logger.warning(f"Error building details for credential {cred.id}: {e}")
            # Still include basic info even if details fail
            protocol = db.query(Protocol).filter_by(id=cred.protocol_id).first()
            result.append(
                CredentialResponse(
                    id=cred.id,
                    user_id=cred.user_id,
                    protocol_id=cred.protocol_id,
                    protocol_name=protocol.name if protocol else "unknown",
                    subscription_id=cred.subscription_id,
                    server=cred.credential_data.get("server", ""),
                    port=cred.credential_data.get("port", 0),
                    server_location=cred.server_location,
                    country_code=cred.credential_data.get("country_code"),
                    credential_data=cred.credential_data,
                    created_at=cred.created_at,
                    updated_at=cred.updated_at,
                )
            )

    return result


@router.get("/{credential_id}", response_model=CredentialResponse)
async def get_credential(
    credential_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get detailed credential information
    """
    credential = (
        db.query(UserCredential)
        .filter_by(id=credential_id, user_id=current_user.id)
        .first()
    )

    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found"
        )

    service = CredentialService(db)
    cred_details = service.get_credential_with_details(credential)

    return CredentialResponse(
        id=credential.id,
        user_id=credential.user_id,
        protocol_id=credential.protocol_id,
        protocol_name=cred_details["protocol_name"],
        subscription_id=credential.subscription_id,
        server=cred_details["server"],
        server_domain=cred_details.get("server_domain"),
        port=cred_details["port"],
        server_location=credential.server_location,
        country_code=cred_details.get("country_code"),
        credential_data=credential.credential_data,
        created_at=credential.created_at,
        updated_at=credential.updated_at,
        connection_uri=cred_details.get("connection_uri"),
        qr_code_data=cred_details.get("qr_code_data"),
        download_links=cred_details.get("download_links"),
    )


@router.delete("/{credential_id}", response_model=SuccessResponse)
async def delete_credential(
    credential_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Delete a credential

    This removes the credential entirely.
    User can generate a new credential for the same subscription after deletion.
    """
    credential = (
        db.query(UserCredential)
        .filter_by(id=credential_id, user_id=current_user.id)
        .first()
    )

    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found"
        )

    service = CredentialService(db)
    service.delete_credential(credential)

    logger.info(f"Credential {credential_id} deleted by user {current_user.id}")

    return SuccessResponse(
        message="Credential deleted successfully", data={"credential_id": credential_id}
    )


# ============================================================================
# CONFIGURATION FILES
# ============================================================================


@router.get(
    "/{credential_id}/config/{config_type}", response_model=CredentialConfigResponse
)
async def get_credential_config(
    credential_id: int,
    config_type: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get configuration file for credential

    **Supported config types:**
    - clash: Clash configuration YAML
    - v2ray/json: V2Ray JSON configuration
    - ssh/config: OpenSSH config format
    - default/url: Connection URL/URI
    - pac: Proxy Auto-Config file (HTTP Proxy)
    - env: Environment variables (HTTP Proxy)
    """
    credential = (
        db.query(UserCredential)
        .filter_by(id=credential_id, user_id=current_user.id)
        .first()
    )

    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found"
        )

    protocol = db.query(Protocol).filter_by(id=credential.protocol_id).first()
    if not protocol:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Protocol not found"
        )

    service = CredentialService(db)

    try:
        config_content = service.get_config_file(credential, config_type)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Determine file extension
    ext_map = {
        "clash": "yaml",
        "v2ray": "json",
        "json": "json",
        "ssh": "conf",
        "config": "conf",
        "pac": "pac",
        "env": "sh",
        "default": "txt",
        "url": "txt",
    }
    extension = ext_map.get(config_type, "txt")
    filename = f"fluxvpn_{protocol.name.lower()}_{config_type}.{extension}"

    return CredentialConfigResponse(
        credential_id=credential.id,
        protocol=protocol.name,
        config_type=config_type,
        config_content=config_content,
        filename=filename,
    )


@router.get("/{credential_id}/guide/{platform}", response_model=ConnectionGuideResponse)
async def get_connection_guide(
    credential_id: int,
    platform: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get connection guide for specific platform

    **Supported platforms:**
    - windows
    - macos
    - linux
    - android
    - ios
    """
    credential = (
        db.query(UserCredential)
        .filter_by(id=credential_id, user_id=current_user.id)
        .first()
    )

    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found"
        )

    service = CredentialService(db)
    guide_data = service.get_connection_guide(credential, platform)

    return ConnectionGuideResponse(
        credential_id=guide_data["credential_id"],
        protocol=guide_data["protocol"],
        platform=guide_data["platform"],
        steps=guide_data.get("steps", []),
        app_download_url=guide_data.get("app_download_url"),
        config_instructions=guide_data.get("config_instructions", ""),
    )


# Note: All helper functions have been moved to CredentialService
# See: app/services/credentials/credential_service.py
