"""Superadmin global free-config API (Task 9).

Exposes the platform-wide free-config singleton (global toggle, per-user
daily ceiling, max-free-users cap), a WRITE-ONLY verification-bot token,
and the GLOBAL required-channels CRUD (admin_id=None). All endpoints are
guarded by `require_super_admin`.

Mirrors the reseller-side free_config_api.py channel resolve+admin-check
pattern, but scopes channels to admin_id=None instead of the current admin.
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth.role_dependencies import require_super_admin
from app.core.database import get_db
from app.models.free_config_channel import FreeConfigChannel
from app.schemas.free_config import ChannelCreate, ChannelOut
from app.schemas.free_config_global import (
    GlobalConfigResponse,
    GlobalConfigUpdate,
    GlobalTokenUpdate,
)
from app.services.free_config.global_service import GlobalConfigService

router = APIRouter(prefix="/super/free-config", tags=["Super Admin Free Config"])


def _to_response(row) -> GlobalConfigResponse:
    """Map a FreeConfigGlobal row to its write-safe response (no token blob)."""
    return GlobalConfigResponse(
        is_enabled=row.is_enabled,
        default_daily_limit_mb=row.default_daily_limit_mb,
        default_max_free_users=row.default_max_free_users,
        has_token=bool(row.verification_bot_token_enc),
        verification_bot_username=row.verification_bot_username,
    )


# ---------------------------------------------------------------------------
# Global settings
# ---------------------------------------------------------------------------


@router.get("/global", response_model=GlobalConfigResponse)
def get_global(
    current: dict = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    """Return the global free-config singleton, creating a disabled default."""
    row = GlobalConfigService(db).get_or_create()
    return _to_response(row)


@router.put("/global", response_model=GlobalConfigResponse)
def update_global(
    payload: GlobalConfigUpdate,
    current: dict = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    """Patch the provided fields on the global free-config singleton."""
    if (
        payload.default_daily_limit_mb is not None
        and payload.default_daily_limit_mb < 0
    ):
        raise HTTPException(422, "default_daily_limit_mb must be >= 0")
    if payload.default_max_free_users is not None and payload.default_max_free_users < 0:
        raise HTTPException(422, "default_max_free_users must be >= 0")

    row = GlobalConfigService(db).update(
        is_enabled=payload.is_enabled,
        default_daily_limit_mb=payload.default_daily_limit_mb,
        default_max_free_users=payload.default_max_free_users,
    )
    return _to_response(row)


@router.put("/global/token", response_model=GlobalConfigResponse)
def set_global_token(
    payload: GlobalTokenUpdate,
    current: dict = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    """Validate a verification-bot token via getMe and store it (write-only)."""
    try:
        GlobalConfigService(db).set_token(payload.token)
    except Exception as exc:
        raise HTTPException(400, f"Invalid verification bot token: {exc}")

    row = GlobalConfigService(db).get_or_create()
    return _to_response(row)


# ---------------------------------------------------------------------------
# Global required-channels CRUD (admin_id=None)
# ---------------------------------------------------------------------------


@router.get("/channels", response_model=list[ChannelOut])
def list_channels(
    current: dict = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    """List the platform-wide (global) required channels."""
    return (
        db.query(FreeConfigChannel)
        .filter(FreeConfigChannel.admin_id.is_(None))
        .all()
    )


@router.post("/channels", response_model=ChannelOut)
def add_channel(
    payload: ChannelCreate,
    current: dict = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    """Resolve a channel via the verification bot and store it globally."""
    from app.services.free_config.membership_verifier import (
        MembershipVerifier,
        resolve_channel,
    )

    verifier = MembershipVerifier.from_global(db)
    if verifier is None:
        raise HTTPException(400, "Verification bot not configured")
    try:
        info = asyncio.run(resolve_channel(verifier._bot, payload.identifier))
    except Exception as exc:
        raise HTTPException(400, f"Cannot use this channel: {exc}")

    row = FreeConfigChannel(
        admin_id=None,
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
    current: dict = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    """Delete one global channel."""
    row = (
        db.query(FreeConfigChannel)
        .filter(
            FreeConfigChannel.id == channel_id,
            FreeConfigChannel.admin_id.is_(None),
        )
        .first()
    )
    if not row:
        raise HTTPException(404, "Channel not found")
    db.delete(row)
    db.commit()
    return {"ok": True}
