"""
Authentication endpoints for user login and registration
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Optional, cast

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import create_access_token, create_telegram_token, get_current_user
from app.core.auth.jwt import create_refresh_token, verify_refresh_token
from app.core.database import get_db
from app.core.security import verify_internal_api_key
from app.models import User
from app.schemas import TokenPairResponse, UserResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


# Request/Response schemas
class TelegramAuthRequest(BaseModel):
    """Telegram bot authentication request"""

    telegram_user_id: int = Field(..., gt=0)
    telegram_username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    language_code: Optional[str] = "en"


class AuthResponse(BaseModel):
    """Authentication response with access token"""

    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class RefreshTokenRequest(BaseModel):
    """Refresh token request"""

    refresh_token: str


# ============================================================================
# TELEGRAM BOT AUTHENTICATION
# ============================================================================


@router.post(
    "/telegram", response_model=TokenPairResponse, status_code=status.HTTP_200_OK
)
async def telegram_auth(
    request: TelegramAuthRequest,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_internal_api_key),  # Requires X-Internal-API-Key header
):
    """
    Authenticate user via Telegram

    This endpoint is called by the Telegram bot when a user starts interaction.
    If the user doesn't exist, they are automatically registered.

    **Security:** Requires X-Internal-API-Key header (internal service auth)

    **Flow:**
    1. Check if user exists by telegram_user_id
    2. If not, create new user with unique referral code
    3. Generate JWT access token
    4. Return token and user data
    """
    logger.info(f"Telegram auth attempt for user: {request.telegram_user_id}")

    # Check if user exists
    user = db.query(User).filter_by(telegram_user_id=request.telegram_user_id).first()

    if not user:
        # Auto-register new user
        logger.info(f"Creating new user for Telegram ID: {request.telegram_user_id}")

        # Generate unique referral code
        import random
        import string

        referral_code = "".join(
            random.choices(string.ascii_uppercase + string.digits, k=8)
        )

        # Ensure referral code is unique
        while db.query(User).filter_by(referral_code=referral_code).first():
            referral_code = "".join(
                random.choices(string.ascii_uppercase + string.digits, k=8)
            )

        # Map language code to supported languages
        language_map = {"en": "en", "fa": "fa", "ar": "ar", "ru": "ru", "zh": "zh"}
        language_key = request.language_code or "en"
        language = language_map.get(language_key, "en")

        user = User(
            telegram_user_id=request.telegram_user_id,
            telegram_username=request.telegram_username,
            referral_code=referral_code,
            language=language,
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        logger.info(f"User created successfully: {user.id}")

    else:
        if user.is_deleted:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is scheduled for deletion",
            )

        # Update username if changed
        if (
            request.telegram_username
            and request.telegram_username != user.telegram_username
        ):
            cast(Any, user).telegram_username = request.telegram_username
            db.commit()

    # Create access token
    access_token = create_access_token({"sub": str(user.id)})

    # Create refresh token
    refresh_token = create_refresh_token(cast(int, user.id), db)

    logger.info(f"Authentication successful for user: {user.id}")

    return TokenPairResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse.model_validate(user),
    )


# ============================================================================
# ADMIN DASHBOARD LOGIN (Public - no API key required)
# ============================================================================


@router.post(
    "/admin/login", response_model=TokenPairResponse, status_code=status.HTTP_200_OK
)
async def admin_login(
    request: TelegramAuthRequest,
    db: Session = Depends(get_db),
):
    """
    Admin dashboard login via Telegram ID

    This endpoint is for the admin dashboard to authenticate users.
    Only users with is_admin=True can access admin features after login.

    **No API key required** - public endpoint for admin dashboard
    """
    logger.info(f"Admin login attempt for Telegram ID: {request.telegram_user_id}")

    # Check if user exists
    user = db.query(User).filter_by(telegram_user_id=request.telegram_user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found. Please start the Telegram bot first.",
        )

    if user.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is scheduled for deletion",
        )

    # Create access token
    access_token = create_access_token({"sub": str(user.id)})

    # Create refresh token
    refresh_token = create_refresh_token(cast(int, user.id), db)

    logger.info(
        f"Admin login successful for user: {user.id} (is_admin: {user.is_admin})"
    )

    return TokenPairResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse.model_validate(user),
    )


@router.post("/telegram/token", status_code=status.HTTP_200_OK)
async def create_telegram_auth_token(
    telegram_user_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_internal_api_key),  # Requires X-Internal-API-Key header
):
    """
    Create long-lived Telegram authentication token

    This endpoint creates a long-lived JWT token for Telegram bot authentication.
    The token is valid for 1 year and can be used for persistent authentication.

    **Security:** Requires X-Internal-API-Key header (internal service auth)

    **Use case:** Telegram Web App or Mini App authentication
    """
    # Verify user exists
    user = db.query(User).filter_by(telegram_user_id=telegram_user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    if user.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is scheduled for deletion",
        )

    # Create long-lived token
    token = create_telegram_token(telegram_user_id)

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 365 * 24 * 60 * 60,  # 1 year in seconds
        "user_id": user.id,
    }


# ============================================================================
# TOKEN REFRESH
# ============================================================================


@router.post(
    "/refresh", response_model=TokenPairResponse, status_code=status.HTTP_200_OK
)
async def refresh_token(request: RefreshTokenRequest, db: Session = Depends(get_db)):
    """
    Refresh access token with rotation

    Implements refresh token rotation:
    - Old refresh token is invalidated via database update
    - New access and refresh tokens are issued

    This improves security by:
    1. Preventing token reuse attacks
    2. Allowing token revocation via database
    3. Detecting suspicious token reuse attempts
    """
    # Verify refresh token using database validation
    user_id = verify_refresh_token(request.refresh_token, db)

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    # Get user
    user = db.query(User).filter_by(id=user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
        )

    if user.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is scheduled for deletion",
        )

    # Create new access token
    access_token = create_access_token({"sub": str(user.id)})

    # Create new refresh token (invalidates old one via database update)
    new_refresh_token = create_refresh_token(cast(int, user.id), db)

    logger.info(f"Token refresh successful for user: {user.id}")

    return TokenPairResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        user=UserResponse.model_validate(user),
    )


# ============================================================================
# TOKEN VALIDATION
# ============================================================================


@router.get("/verify", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def verify_auth(current_user: User = Depends(get_current_user)):
    """
    Verify authentication token and return current user

    This endpoint can be used to validate a token and get current user data.

    **Headers required:**
    - Authorization: Bearer {access_token}
    """
    return UserResponse.model_validate(current_user)


# ============================================================================
# LOGOUT
# ============================================================================


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(current_user: User = Depends(get_current_user)):
    """
    Logout user

    **Note:** JWT tokens are stateless, so logout is client-side only.
    Client should discard the token. In production, implement token blacklisting
    for enhanced security.
    """
    logger.info(f"User logout: {current_user.id}")

    return {"message": "Logged out successfully", "user_id": current_user.id}
