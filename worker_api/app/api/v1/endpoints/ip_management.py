"""
IP Change Management endpoints
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, desc
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models import (
    Credential,
    IPChangeRequest,
    Protocol,
    ProtocolInstance,
    Subscription,
    User,
)
from app.schemas import SuccessResponse
from app.tasks.ip_tasks import process_ip_change

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ip-management", tags=["IP Management"])


def _credential_data(credential: Credential) -> Dict[str, Any]:
    data: Dict[str, Any] = cast(Dict[str, Any], credential.credential_data or {})
    return data if isinstance(data, dict) else {}


def _credential_is_active(credential: Credential) -> bool:
    return bool(_credential_data(credential).get("is_active", True))


def _credential_instance_id(credential: Credential) -> Optional[int]:
    instance_id = _credential_data(credential).get("instance_id")
    try:
        return int(instance_id) if instance_id is not None else None
    except (TypeError, ValueError):
        return None


def _credential_server_ip(credential: Credential) -> Optional[str]:
    data = _credential_data(credential)
    value = data.get("server_ip") or data.get("server")
    return str(value) if value else None


def _serialize_ip_change_request(
    db: Session, request: IPChangeRequest, credential_id: Optional[int] = None
) -> "IPChangeRequestResponse":
    old_instance = None
    new_instance = None

    if request.old_instance_id:
        old_instance = (
            db.query(ProtocolInstance).filter_by(id=request.old_instance_id).first()
        )
    if request.new_instance_id:
        new_instance = (
            db.query(ProtocolInstance).filter_by(id=request.new_instance_id).first()
        )

    if credential_id is None:
        credential = (
            db.query(Credential)
            .filter_by(
                user_id=request.user_id,
                subscription_id=request.subscription_id,
                protocol_id=request.protocol_id,
            )
            .order_by(Credential.id.asc())
            .first()
        )
        credential_id = cast(int, credential.id) if credential else None

    return IPChangeRequestResponse(
        id=request.id,
        user_id=request.user_id,
        subscription_id=request.subscription_id,
        protocol_id=request.protocol_id,
        requested_country_code=request.requested_country_code,
        status=request.status,
        old_instance_id=request.old_instance_id,
        new_instance_id=request.new_instance_id,
        created_at=request.created_at,
        processed_at=request.processed_at,
        denial_reason=request.denial_reason,
        # Legacy compatibility fields used by old tests/clients.
        credential_id=credential_id,
        old_ip=str(old_instance.ip_address) if old_instance else None,
        new_ip=str(new_instance.ip_address) if new_instance else None,
        old_country=old_instance.country_code if old_instance else None,
        new_country=new_instance.country_code if new_instance else None,
        requested_at=request.created_at,
        completed_at=request.processed_at,
        failure_reason=request.denial_reason,
    )


# ============================================================================
# REQUEST/RESPONSE SCHEMAS
# ============================================================================


class IPChangeRequestCreate(BaseModel):
    """Request to change IP for a credential."""

    credential_id: int = Field(..., gt=0, description="Credential ID to change IP for")
    preferred_country: Optional[str] = Field(
        None, description="Preferred country code (NL, US, DE, SG, GB)"
    )
    reason: Optional[str] = Field(
        None, max_length=500, description="Optional reason for IP change"
    )


class IPChangeRequestResponse(BaseModel):
    """IP change request response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    subscription_id: int
    protocol_id: int
    requested_country_code: Optional[str] = None
    status: str  # pending, completed, failed, denied
    old_instance_id: Optional[int] = None
    new_instance_id: Optional[int] = None
    created_at: datetime
    processed_at: Optional[datetime] = None
    denial_reason: Optional[str] = None

    # Legacy compatibility fields
    credential_id: Optional[int] = None
    old_ip: Optional[str] = None
    new_ip: Optional[str] = None
    old_country: Optional[str] = None
    new_country: Optional[str] = None
    requested_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    failure_reason: Optional[str] = None


class CredentialWithIPInfo(BaseModel):
    """Credential with IP change information."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    protocol_id: int
    protocol_name: str
    server_ip: str
    country_code: str
    country_name: str
    port: int
    username: Optional[str]
    is_active: bool
    created_at: datetime
    last_ip_change: Optional[datetime]
    ip_changes_used: int
    ip_changes_remaining: int


class IPChangeStats(BaseModel):
    """IP change statistics for user."""

    total_ip_changes_allowed: int
    total_ip_changes_used: int
    ip_changes_remaining: int
    active_credentials: int
    last_ip_change: Optional[datetime]


# ============================================================================
# IP CHANGE REQUEST ENDPOINTS
# ============================================================================


@router.post(
    "/request",
    response_model=IPChangeRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def request_ip_change(
    request: IPChangeRequestCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Request IP change for a credential.
    """
    credential = (
        db.query(Credential)
        .filter_by(id=request.credential_id, user_id=current_user.id)
        .first()
    )
    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Credential not found",
        )

    if not _credential_is_active(credential):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change IP for inactive credential",
        )

    active_subscription = (
        db.query(Subscription)
        .filter(
            and_(
                Subscription.id == credential.subscription_id,
                Subscription.user_id == current_user.id,
                Subscription.is_active == True,
                Subscription.expires_at
                > datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
        .first()
    )
    if not active_subscription:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You need an active subscription to change IP",
        )

    thirty_days_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        days=30
    )
    recent_changes = (
        db.query(IPChangeRequest)
        .filter(
            and_(
                IPChangeRequest.subscription_id == credential.subscription_id,
                IPChangeRequest.protocol_id == credential.protocol_id,
                IPChangeRequest.status == "completed",
                IPChangeRequest.created_at > thirty_days_ago,
            )
        )
        .count()
    )
    max_changes_per_month = 3
    if recent_changes >= max_changes_per_month:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Maximum {max_changes_per_month} IP changes per month. "
                "You have used all your changes."
            ),
        )

    pending_request = (
        db.query(IPChangeRequest)
        .filter(
            and_(
                IPChangeRequest.subscription_id == credential.subscription_id,
                IPChangeRequest.protocol_id == credential.protocol_id,
                IPChangeRequest.status == "pending",
            )
        )
        .first()
    )
    if pending_request:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="There is already a pending IP change request for this credential",
        )

    current_instance_id = _credential_instance_id(credential)
    requested_country_code = (
        request.preferred_country.upper() if request.preferred_country else None
    )

    ip_change_request = IPChangeRequest(
        user_id=current_user.id,
        subscription_id=credential.subscription_id,
        protocol_id=credential.protocol_id,
        old_instance_id=current_instance_id,
        requested_country_code=requested_country_code,
        status="pending",
    )
    db.add(ip_change_request)
    db.commit()
    db.refresh(ip_change_request)

    logger.info(
        "Created IP change request %s for user %s and credential %s",
        ip_change_request.id,
        current_user.id,
        credential.id,
    )

    try:
        process_ip_change.delay(ip_change_request.id)
    except Exception as exc:
        logger.warning(
            "Failed to enqueue ip change request %s: %s",
            ip_change_request.id,
            exc,
        )

    return _serialize_ip_change_request(
        db=db,
        request=ip_change_request,
        credential_id=cast(int, credential.id),
    )


@router.get("/requests", response_model=List[IPChangeRequestResponse])
async def list_ip_change_requests(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    status_filter: Optional[str] = Query(
        None, description="Filter by status: pending, completed, failed, denied"
    ),
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
):
    query = db.query(IPChangeRequest).filter_by(user_id=current_user.id)
    if status_filter:
        query = query.filter(IPChangeRequest.status == status_filter)

    requests = (
        query.order_by(IPChangeRequest.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [_serialize_ip_change_request(db, req) for req in requests]


@router.get("/requests/{request_id}", response_model=IPChangeRequestResponse)
async def get_ip_change_request(
    request_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ip_request = (
        db.query(IPChangeRequest)
        .filter_by(id=request_id, user_id=current_user.id)
        .first()
    )
    if not ip_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="IP change request not found"
        )
    return _serialize_ip_change_request(db, ip_request)


@router.delete("/requests/{request_id}", response_model=SuccessResponse)
async def cancel_ip_change_request(
    request_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ip_request = (
        db.query(IPChangeRequest)
        .filter_by(id=request_id, user_id=current_user.id)
        .first()
    )
    if not ip_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="IP change request not found"
        )
    if ip_request.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel request with status: {ip_request.status}",
        )

    ip_request_obj = cast(Any, ip_request)
    ip_request_obj.status = "denied"
    ip_request_obj.denial_reason = "Cancelled by user"
    ip_request_obj.processed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()

    return SuccessResponse(
        message="IP change request cancelled successfully",
        data={"request_id": request_id},
    )


# ============================================================================
# IP CHANGE STATISTICS
# ============================================================================


@router.get("/stats", response_model=IPChangeStats)
async def get_ip_change_stats(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    credentials = db.query(Credential).filter_by(user_id=current_user.id).all()
    active_credentials = sum(
        1 for credential in credentials if _credential_is_active(credential)
    )

    thirty_days_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        days=30
    )
    ip_changes_used = (
        db.query(IPChangeRequest)
        .filter(
            and_(
                IPChangeRequest.user_id == current_user.id,
                IPChangeRequest.status == "completed",
                IPChangeRequest.created_at > thirty_days_ago,
            )
        )
        .count()
    )

    last_change = (
        db.query(IPChangeRequest)
        .filter(
            and_(
                IPChangeRequest.user_id == current_user.id,
                IPChangeRequest.status == "completed",
            )
        )
        .order_by(desc(IPChangeRequest.processed_at))
        .first()
    )

    total_allowed = active_credentials * 3
    return IPChangeStats(
        total_ip_changes_allowed=total_allowed,
        total_ip_changes_used=ip_changes_used,
        ip_changes_remaining=max(0, total_allowed - ip_changes_used),
        active_credentials=active_credentials,
        last_ip_change=last_change.processed_at if last_change else None,
    )


# ============================================================================
# CREDENTIAL IP INFORMATION
# ============================================================================


@router.get("/credentials", response_model=List[CredentialWithIPInfo])
async def list_credentials_with_ip_info(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    is_active: Optional[bool] = None,
):
    query = db.query(Credential).filter_by(user_id=current_user.id)
    credentials = query.order_by(Credential.created_at.desc()).all()

    result: List[CredentialWithIPInfo] = []
    thirty_days_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        days=30
    )

    for credential in credentials:
        active = _credential_is_active(credential)
        if is_active is not None and active != is_active:
            continue

        data = _credential_data(credential)
        instance = None
        instance_id = _credential_instance_id(credential)
        if instance_id:
            instance = db.query(ProtocolInstance).filter_by(id=instance_id).first()
        protocol = db.query(Protocol).filter_by(id=credential.protocol_id).first()

        ip_changes_used = (
            db.query(IPChangeRequest)
            .filter(
                and_(
                    IPChangeRequest.subscription_id == credential.subscription_id,
                    IPChangeRequest.protocol_id == credential.protocol_id,
                    IPChangeRequest.status == "completed",
                    IPChangeRequest.created_at > thirty_days_ago,
                )
            )
            .count()
        )

        last_change = (
            db.query(IPChangeRequest)
            .filter(
                and_(
                    IPChangeRequest.subscription_id == credential.subscription_id,
                    IPChangeRequest.protocol_id == credential.protocol_id,
                    IPChangeRequest.status == "completed",
                )
            )
            .order_by(desc(IPChangeRequest.processed_at))
            .first()
        )

        server_ip = (
            str(instance.ip_address)
            if instance
            else (_credential_server_ip(credential) or "Pending")
        )
        country_code = (
            instance.country_code if instance else str(data.get("country_code") or "XX")
        )
        country_name = instance.country_name if instance else "Unknown"

        result.append(
            CredentialWithIPInfo(
                id=credential.id,
                protocol_id=credential.protocol_id,
                protocol_name=protocol.name if protocol else "Unknown",
                server_ip=server_ip,
                country_code=country_code,
                country_name=country_name,
                port=int(data.get("port") or 0),
                username=data.get("username"),
                is_active=active,
                created_at=credential.created_at,
                last_ip_change=last_change.processed_at if last_change else None,
                ip_changes_used=ip_changes_used,
                ip_changes_remaining=max(0, 3 - ip_changes_used),
            )
        )

    return result


@router.get(
    "/credentials/{credential_id}/ip-history",
    response_model=List[IPChangeRequestResponse],
)
async def get_credential_ip_history(
    credential_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    credential = (
        db.query(Credential)
        .filter_by(id=credential_id, user_id=current_user.id)
        .first()
    )
    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found"
        )

    history = (
        db.query(IPChangeRequest)
        .filter(
            and_(
                IPChangeRequest.user_id == current_user.id,
                IPChangeRequest.subscription_id == credential.subscription_id,
                IPChangeRequest.protocol_id == credential.protocol_id,
            )
        )
        .order_by(IPChangeRequest.created_at.desc())
        .all()
    )

    credential_id = cast(int, credential.id)
    return [_serialize_ip_change_request(db, req, credential_id) for req in history]


# ============================================================================
# AVAILABLE COUNTRIES
# ============================================================================


@router.get("/countries")
async def list_available_countries(db: Session = Depends(get_db)):
    countries = (
        db.query(ProtocolInstance.country_code, ProtocolInstance.country_name)
        .filter(ProtocolInstance.is_active == True)
        .distinct()
        .all()
    )

    return [
        {
            "country_code": country.country_code,
            "country_name": country.country_name,
            "flag_emoji": _get_flag_emoji(country.country_code),
        }
        for country in countries
    ]


def _get_flag_emoji(country_code: str) -> str:
    flag_map = {
        "NL": "🇳🇱",
        "US": "🇺🇸",
        "DE": "🇩🇪",
        "SG": "🇸🇬",
        "GB": "🇬🇧",
        "FR": "🇫🇷",
        "CA": "🇨🇦",
        "JP": "🇯🇵",
        "AU": "🇦🇺",
    }
    return flag_map.get(country_code, "🌍")
