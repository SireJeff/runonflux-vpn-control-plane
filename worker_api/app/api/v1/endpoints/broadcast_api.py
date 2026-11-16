"""Reseller + superadmin API for broadcast messaging."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.auth.role_dependencies import RoleChecker
from app.core.database import get_db
from app.models.admins import Admin
from app.models.broadcast import Broadcast
from app.schemas.broadcast import (
    AudienceCountRequest,
    AudienceCountResponse,
    BroadcastCreateRequest,
    BroadcastEnabledRequest,
    BroadcastEnabledResponse,
    BroadcastResponse,
)
from app.services.broadcasts.broadcast_service import (
    VALID_SEGMENTS,
    can_broadcast,
    count_audience,
    validate_content,
)
from app.tasks.broadcast_tasks import send_broadcast

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/broadcasts", tags=["Broadcasts"])

_REASON_STATUS = {
    "rate_limited": status.HTTP_429_TOO_MANY_REQUESTS,
    "disabled": status.HTTP_409_CONFLICT,
    "no_bot": status.HTTP_409_CONFLICT,
    "in_flight": status.HTTP_409_CONFLICT,
}


def _require_segment(segment: str) -> None:
    if segment not in VALID_SEGMENTS:
        raise HTTPException(status_code=422, detail=f"Invalid segment: {segment}")


@router.post("/audience-count", response_model=AudienceCountResponse)
def audience_count(
    req: AudienceCountRequest,
    current: dict = Depends(RoleChecker(["admin"])),
    db: Session = Depends(get_db),
):
    _require_segment(req.segment)
    return AudienceCountResponse(count=count_audience(db, current["id"], req.segment))


@router.post("", response_model=BroadcastResponse, status_code=status.HTTP_201_CREATED)
def create_broadcast(
    req: BroadcastCreateRequest,
    current: dict = Depends(RoleChecker(["admin"])),
    db: Session = Depends(get_db),
):
    _require_segment(req.segment)
    try:
        validate_content(req.message_text, req.button_label, req.button_url)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    elig = can_broadcast(db, current["id"])
    if not elig.ok:
        raise HTTPException(
            status_code=_REASON_STATUS.get(elig.reason or "", status.HTTP_409_CONFLICT),
            detail=elig.reason,
        )

    bc = Broadcast(
        admin_id=current["id"],
        created_by=current["id"],
        segment=req.segment,
        message_text=req.message_text,
        button_label=req.button_label,
        button_url=req.button_url,
        status="queued",
    )
    db.add(bc)
    db.commit()
    db.refresh(bc)
    send_broadcast.delay(bc.id)
    return bc


@router.get("", response_model=list[BroadcastResponse])
def list_broadcasts(
    current: dict = Depends(RoleChecker(["admin"])),
    db: Session = Depends(get_db),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
):
    return (
        db.query(Broadcast)
        .filter(Broadcast.admin_id == current["id"])
        .order_by(Broadcast.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )


@router.get("/{broadcast_id}", response_model=BroadcastResponse)
def get_broadcast(
    broadcast_id: int,
    current: dict = Depends(RoleChecker(["admin"])),
    db: Session = Depends(get_db),
):
    bc = (
        db.query(Broadcast)
        .filter(Broadcast.id == broadcast_id, Broadcast.admin_id == current["id"])
        .first()
    )
    if bc is None:
        raise HTTPException(status_code=404, detail="Broadcast not found")
    return bc


superadmin_router = APIRouter(
    prefix="/super-admin", tags=["Broadcasts (Superadmin)"]
)


@superadmin_router.get("/broadcasts", response_model=list[BroadcastResponse])
def sa_list_broadcasts(
    current: dict = Depends(RoleChecker(["super_admin"])),
    db: Session = Depends(get_db),
    admin_id: int | None = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
):
    q = db.query(Broadcast)
    if admin_id is not None:
        q = q.filter(Broadcast.admin_id == admin_id)
    return q.order_by(Broadcast.created_at.desc()).limit(limit).offset(offset).all()


@superadmin_router.patch(
    "/admins/{admin_id}/broadcasts-enabled",
    response_model=BroadcastEnabledResponse,
)
def sa_toggle_broadcasts_enabled(
    admin_id: int,
    req: BroadcastEnabledRequest,
    current: dict = Depends(RoleChecker(["super_admin"])),
    db: Session = Depends(get_db),
):
    admin = db.query(Admin).filter(Admin.id == admin_id).first()
    if admin is None:
        raise HTTPException(status_code=404, detail="Admin not found")
    admin.broadcasts_enabled = req.enabled
    db.commit()
    return BroadcastEnabledResponse(
        admin_id=admin_id, broadcasts_enabled=admin.broadcasts_enabled
    )
