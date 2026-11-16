"""
Authentication V2 endpoints for the Reseller Platform.

Provides username+password login, registration (pending approval), token
refresh, and a /me introspection endpoint.  JWT tokens now carry a ``role``
claim (``super_admin``, ``admin``, or ``end_user``) which is enforced by
:mod:`app.core.auth.role_dependencies`.

This module is deliberately kept separate from the original
``auth.py`` (Telegram-based auth) to avoid disrupting existing flows.
"""

import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth.jwt import create_access_token, verify_token
from app.core.auth.password import hash_password, verify_password
from app.core.auth.role_dependencies import RoleChecker
from app.core.config import settings
from app.core.database import get_db
from app.models.admin_users import AdminUser
from app.models.admins import Admin

router = APIRouter(prefix="/auth", tags=["Authentication V2"])

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    display_name: str | None = Field(None, max_length=100)
    telegram_id: str = Field(..., min_length=1, max_length=50)
    whatsapp_number: str | None = Field(None, max_length=20)
    phone_number: str | None = Field(None, max_length=20)
    notes: str | None = None

    @field_validator("telegram_id")
    @classmethod
    def _telegram_id_must_be_numeric(cls, v: str) -> str:
        """Reject non-numeric telegram_id at the write path.

        ``admins.telegram_id`` is a free-text ``String(50)``, but the bot
        matches admins by the numeric Telegram user id. Historically a handle
        (e.g. ``"fixture-user.invalid"``) could be stored here, silently making that admin
        unrecognisable. Enforce digits-only so new registrations can never
        recreate that broken state.
        """
        v = (v or "").strip().lstrip("@")
        if not v.isdigit():
            raise ValueError(
                "telegram_id must be your numeric Telegram user id (digits only). "
                "Open the bot and press Start to see it."
            )
        return v


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    role: str
    username: str
    display_name: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class UserInfo(BaseModel):
    id: int
    username: str
    role: str
    display_name: str | None = None
    status: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED
)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    """Register a new admin account (pending approval).

    The account is created with ``status=pending`` and no password hash.
    A super admin must approve the account and assign a password before
    the registrant can log in.
    """
    existing = db.query(Admin).filter(Admin.username == req.username).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Username already taken"
        )

    admin = Admin(
        username=req.username,
        password_hash="",  # Set on approval by super admin
        display_name=req.display_name,
        telegram_id=req.telegram_id,
        whatsapp_number=req.whatsapp_number,
        phone_number=req.phone_number,
        notes=req.notes,
        status="pending",
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)

    # --- Notify superadmin ---
    try:
        from app.core.config import settings as app_settings
        from app.services.notifications.send_alert import send_telegram_alert
        from app.services.notifications.templates import format_new_registration_pending

        super_admin = (
            db.query(Admin)
            .filter(Admin.username == app_settings.SUPER_ADMIN_USERNAME)
            .first()
        )
        if (
            super_admin
            and super_admin.telegram_id
            and str(super_admin.telegram_id).isdigit()
        ):
            msg = format_new_registration_pending(
                username=admin.username,
                display_name=admin.display_name or "",
                telegram_id=int(admin.telegram_id)
                if admin.telegram_id and str(admin.telegram_id).isdigit()
                else 0,
            )
            send_telegram_alert(int(super_admin.telegram_id), msg)
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning(
            f"Failed to send registration notification: {e}"
        )

    return TokenResponse(
        access_token="",
        role="pending",
        username=admin.username,
        display_name=admin.display_name,
    )


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    """Login for all 3 roles (super_admin, admin, end_user).

    Lookup strategy:
    * Admin table first -- ``username`` is globally unique.
    * AdminUser table second -- username is only unique *per admin*.
      For now we fall back to a simple first-match lookup, but callers
      that want admin-scoped login should add a ``login_code`` or similar
      disambiguation mechanism in the future.
    """
    # --- Try Admin table (super_admin and admin roles) ---
    admin = db.query(Admin).filter(Admin.username == req.username).first()
    if admin:
        if not admin.password_hash:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account pending approval",
            )
        if not verify_password(req.password, admin.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
            )
        if admin.status == "pending":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Account pending approval"
            )
        if admin.status == "suspended":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Account suspended"
            )
        if admin.status == "deleted":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Account deactivated"
            )

        role = (
            "super_admin"
            if admin.username == settings.SUPER_ADMIN_USERNAME
            else "admin"
        )
        access_token = create_access_token({"sub": str(admin.id), "role": role})
        # For admin refresh tokens we use a second JWT with a longer TTL
        # and a type marker so we can distinguish it.
        refresh_token = create_access_token(
            {"sub": str(admin.id), "role": f"{role}_refresh", "type": "refresh"},
            expires_delta=timedelta(days=30),
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            role=role,
            username=admin.username,
            display_name=admin.display_name,
        )

    # --- Try AdminUser table (end_user role) ---
    user = db.query(AdminUser).filter(AdminUser.username == req.username).first()
    if user:
        if not user.password_hash or not verify_password(
            req.password, user.password_hash
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
            )
        if user.status != "active":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Account is {user.status}",
            )

        access_token = create_access_token(
            {"sub": str(user.id), "role": "end_user", "admin_id": str(user.admin_id)}
        )
        refresh_token = create_access_token(
            {"sub": str(user.id), "role": "end_user_refresh", "type": "refresh"},
            expires_delta=timedelta(days=30),
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            role="end_user",
            username=user.username,
            display_name=user.display_name,
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(req: RefreshRequest, db: Session = Depends(get_db)):
    """Refresh an access token using a valid refresh token."""
    payload = verify_token(req.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )

    user_id = int(payload["sub"])
    raw_role: str = payload.get("role", "")
    role = raw_role.replace("_refresh", "")

    access_token = create_access_token({"sub": str(user_id), "role": role})

    username = ""
    display_name = None
    if role in ("super_admin", "admin"):
        admin = db.query(Admin).filter(Admin.id == user_id).first()
        if admin:
            username = admin.username
            display_name = admin.display_name
    elif role == "end_user":
        user = db.query(AdminUser).filter(AdminUser.id == user_id).first()
        if user:
            username = user.username
            display_name = user.display_name

    return TokenResponse(
        access_token=access_token,
        role=role,
        username=username,
        display_name=display_name,
    )


@router.get("/me", response_model=UserInfo)
def get_me(
    current_user: dict = Depends(RoleChecker(["super_admin", "admin", "end_user"]))
):
    """Return the authenticated user's profile."""
    entity = current_user["entity"]
    return UserInfo(
        id=current_user["id"],
        role=current_user["role"],
        username=entity.username,
        display_name=entity.display_name,
        status=getattr(entity, "status", "active"),
    )


@router.put("/change-password")
def change_password(
    req: ChangePasswordRequest,
    current_user: dict = Depends(RoleChecker(["super_admin", "admin", "end_user"])),
    db: Session = Depends(get_db),
):
    """Change the authenticated user's password.

    Verifies the current password before updating.  Works for all three roles.
    """
    entity = current_user["entity"]

    if not verify_password(req.current_password, entity.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    entity.password_hash = hash_password(req.new_password[:72])
    db.commit()

    return {"success": True, "message": "Password changed successfully"}


def _resolve_admin_by_telegram(
    db: Session, telegram_id: int, username: str | None
) -> Admin | None:
    """Resolve an Admin by numeric Telegram id, with a scoped @username self-heal.

    Primary match: ``Admin.telegram_id == str(telegram_id)`` (numeric, exact) —
    unchanged behaviour, and it always wins.

    Fallback (applies ONLY to rows whose stored ``telegram_id`` is NON-numeric):
    if the caller supplies the user's Telegram ``username`` and it equals a
    stored non-numeric ``telegram_id`` (case-insensitive, ignoring a leading
    ``@``), that row is a mis-entered handle. Backfill the real numeric id and
    return the row. This is a one-shot migration: after the backfill the row
    matches numerically forever, so the mutable-username match never applies to
    a valid (numeric) admin and never applies twice to the same row.
    """
    admin = db.query(Admin).filter(Admin.telegram_id == str(telegram_id)).first()
    if admin:
        return admin

    handle = (username or "").strip().lstrip("@").lower()
    if not handle:
        return None

    candidate = db.query(Admin).filter(func.lower(Admin.telegram_id) == handle).first()
    # Only self-heal rows whose stored value is a handle, never a numeric id.
    if candidate and candidate.telegram_id and not str(candidate.telegram_id).isdigit():
        old = candidate.telegram_id
        candidate.telegram_id = str(telegram_id)
        db.commit()
        db.refresh(candidate)
        logger.info(
            "Backfilled telegram_id for admin id=%s username=%s: %r -> %s",
            candidate.id,
            candidate.username,
            old,
            telegram_id,
        )
        return candidate

    return None


@router.get("/check-telegram")
def check_telegram_id(
    telegram_id: int = Query(..., description="Telegram user ID"),
    username: str
    | None = Query(
        None, description="Telegram @username (for one-shot handle self-heal)"
    ),
    db: Session = Depends(get_db),
):
    """Check if a telegram_id is linked to an admin account. Used by the Telegram bot."""
    admin = _resolve_admin_by_telegram(db, telegram_id, username)
    if not admin:
        return {"found": False}

    role = "admin"
    if admin.username == settings.SUPER_ADMIN_USERNAME:
        role = "super_admin"

    return {
        "found": True,
        "id": admin.id,
        "username": admin.username,
        "display_name": admin.display_name or admin.username,
        "role": role,
        "status": admin.status,
    }


@router.post("/bot-login")
def bot_login(
    telegram_id: int = Query(..., description="Telegram user ID"),
    username: str
    | None = Query(
        None, description="Telegram @username (for one-shot handle self-heal)"
    ),
    db: Session = Depends(get_db),
):
    """Generate a JWT for an admin identified by telegram_id. Called by the bot."""
    admin = _resolve_admin_by_telegram(db, telegram_id, username)
    if not admin or admin.status != "active":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active admin not found for this telegram_id",
        )

    role = "super_admin" if admin.username == settings.SUPER_ADMIN_USERNAME else "admin"
    token = create_access_token({"sub": str(admin.id), "role": role})

    return {
        "access_token": token,
        "role": role,
        "username": admin.username,
        "display_name": admin.display_name,
    }
