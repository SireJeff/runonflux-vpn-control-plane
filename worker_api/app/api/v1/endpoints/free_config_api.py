"""Reseller-facing free-config API (Task 13).

Exposes the per-reseller shared free public config (Task 12's
FreeConfigService) via three admin-only REST endpoints, plus the
per-user free-config fields (Task 8) and a required-channels CRUD.
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth.role_dependencies import RoleChecker
from app.core.database import get_db
from app.models.admin_free_config import AdminFreeConfig
from app.models.free_config_channel import FreeConfigChannel
from app.models.free_config_global import FreeConfigGlobal
from app.schemas.free_config import (
    ChannelCreate,
    ChannelOut,
    FreeConfigResponse,
    FreeConfigUpdate,
)
from app.services.free_config.free_config_service import FreeConfigService

router = APIRouter(prefix="/admin/free-config", tags=["Admin Free Config"])

# Module-level dependency instance so it can be targeted by
# app.dependency_overrides in tests.
_require_admin = RoleChecker(["admin"])

_DEFAULT_CEILING_MB = 200


def _global_ceiling(db: Session) -> int:
    g = db.query(FreeConfigGlobal).first()
    return g.default_daily_limit_mb if g else _DEFAULT_CEILING_MB


def _to_response(config: AdminFreeConfig, db: Session) -> FreeConfigResponse:
    """Map an AdminFreeConfig row to its public response shape."""
    global_channels = (
        db.query(FreeConfigChannel)
        .filter(
            FreeConfigChannel.admin_id.is_(None),
            FreeConfigChannel.is_active.is_(True),
        )
        .all()
    )
    return FreeConfigResponse(
        is_enabled=config.is_enabled,
        kind=config.kind,
        label=config.label,
        region=config.region,
        traffic_limit_gb=config.traffic_limit_gb,
        duration_days=config.duration_days,
        has_credential=bool(config.shared_credential_ref),
        daily_limit_mb=config.daily_limit_mb,
        max_free_users=config.max_free_users,
        global_ceiling_mb=_global_ceiling(db),
        global_channels=[ChannelOut.model_validate(c) for c in global_channels],
    )


@router.get("", response_model=FreeConfigResponse)
def get_free_config(
    current: dict = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    """Return the reseller's free config, creating a disabled default if absent."""
    config = FreeConfigService(db).get_or_create(current["id"])
    return _to_response(config, db)


@router.put("", response_model=FreeConfigResponse)
def update_free_config(
    payload: FreeConfigUpdate,
    current: dict = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    """Patch the provided fields on the reseller's free config."""
    ceiling = _global_ceiling(db)
    if payload.daily_limit_mb is not None and payload.daily_limit_mb > ceiling:
        raise HTTPException(
            422,
            f"daily_limit_mb ({payload.daily_limit_mb}) exceeds global "
            f"ceiling ({ceiling})",
        )
    if payload.max_free_users is not None and payload.max_free_users < 0:
        raise HTTPException(422, "max_free_users must be >= 0")

    config = FreeConfigService(db).update(
        current["id"],
        is_enabled=payload.is_enabled,
        kind=payload.kind,
        label=payload.label,
        region=payload.region,
        traffic_limit_gb=payload.traffic_limit_gb,
        duration_days=payload.duration_days,
        daily_limit_mb=payload.daily_limit_mb,
        max_free_users=payload.max_free_users,
    )
    return _to_response(config, db)


@router.post("/rotate", response_model=FreeConfigResponse)
def rotate_free_config(
    current: dict = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    """Provision/rotate the shared credential for the reseller's free config."""
    config = FreeConfigService(db).rotate(current["id"])
    return _to_response(config, db)


# ---------------------------------------------------------------------------
# Required-channels CRUD (reseller-scoped: admin_id == current["id"])
# ---------------------------------------------------------------------------


@router.get("/channels", response_model=list[ChannelOut])
def list_channels(
    current: dict = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    """List the reseller's own required channels."""
    return (
        db.query(FreeConfigChannel)
        .filter(FreeConfigChannel.admin_id == current["id"])
        .all()
    )


@router.post("/channels", response_model=ChannelOut)
def add_channel(
    payload: ChannelCreate,
    current: dict = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    """Resolve a channel via the verification bot and store it for the reseller."""
    from app.services.free_config.membership_verifier import (
        MembershipVerifier,
        resolve_channel,
    )

    verifier = MembershipVerifier.from_global(db)
    if verifier is None:
        raise HTTPException(400, "Verification bot not configured by superadmin")
    try:
        info = asyncio.run(resolve_channel(verifier._bot, payload.identifier))
    except Exception as exc:
        raise HTTPException(400, f"Cannot use this channel: {exc}")

    row = FreeConfigChannel(
        admin_id=current["id"],
        chat_id=info["chat_id"],
        username=info["username"],
        title=info["title"],
        invite_url=payload.invite_url or info["invite_url"],
        is_active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/channels/{channel_id}")
def delete_channel(
    channel_id: int,
    current: dict = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    """Delete one of the reseller's own channels."""
    row = (
        db.query(FreeConfigChannel)
        .filter(
            FreeConfigChannel.id == channel_id,
            FreeConfigChannel.admin_id == current["id"],
        )
        .first()
    )
    if not row:
        raise HTTPException(404, "Channel not found")
    db.delete(row)
    db.commit()
    return {"ok": True}
