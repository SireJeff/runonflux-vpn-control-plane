"""
JWT (JSON Web Token) utilities for authentication
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, cast

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models import User

logger = logging.getLogger(__name__)

# Security scheme for Swagger UI
security = HTTPBearer()


def create_access_token(
    data: Dict[str, Any], expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create JWT access token

    Args:
        data: Payload data to encode (typically {"sub": user_id})
        expires_delta: Token expiration time (default: from settings)

    Returns:
        Encoded JWT token string

    Example:
        >>> token = create_access_token({"sub": str(user.id)})
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc).replace(tzinfo=None) + expires_delta
    else:
        expire = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
            hours=settings.JWT_EXPIRATION_HOURS
        )

    to_encode.update(
        {"exp": expire, "iat": datetime.now(timezone.utc).replace(tzinfo=None)}
    )

    encoded_jwt = jwt.encode(
        to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )

    return encoded_jwt


def verify_token(token: str) -> Dict[str, Any]:
    """
    Verify and decode JWT token

    Args:
        token: JWT token string

    Returns:
        Decoded payload dictionary

    Raises:
        HTTPException: If token is invalid or expired
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )

        return payload

    except JWTError as e:
        logger.error(f"JWT verification failed: {str(e)}")
        raise credentials_exception


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """
    Get current authenticated user from JWT token

    This is a FastAPI dependency that can be used in route functions.

    Args:
        credentials: HTTP Bearer credentials (JWT token)
        db: Database session

    Returns:
        User model instance

    Raises:
        HTTPException: If authentication fails

    Usage in routes:
        @app.get("/protected")
        async def protected_route(current_user: User = Depends(get_current_user)):
            return {"user_id": current_user.id}
    """
    token = credentials.credentials

    # Verify token
    payload = verify_token(token)

    # Extract user ID from payload
    user_id: Optional[str] = payload.get("sub")

    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get user from database
    user = db.query(User).filter(User.id == int(user_id)).first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is scheduled for deletion",
        )

    return user


async def get_current_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Get current authenticated admin user

    This dependency ensures the user is an admin.

    Args:
        current_user: Current authenticated user

    Returns:
        User model instance (admin)

    Raises:
        HTTPException: If user is not an admin

    Usage:
        @app.get("/admin/stats")
        async def admin_stats(admin: User = Depends(get_current_admin_user)):
            return {"stats": "admin_data"}
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required"
        )

    return current_user


def create_telegram_token(telegram_user_id: int) -> str:
    """
    Create JWT token for Telegram bot authentication

    Args:
        telegram_user_id: Telegram user ID

    Returns:
        JWT token for Telegram authentication
    """
    data = {"sub": str(telegram_user_id), "type": "telegram"}

    return create_access_token(data, expires_delta=timedelta(days=365))


def verify_telegram_token(token: str) -> int:
    """
    Verify Telegram authentication token and extract user ID

    Args:
        token: Telegram JWT token

    Returns:
        Telegram user ID

    Raises:
        HTTPException: If token is invalid
    """
    payload = verify_token(token)

    if payload.get("type") != "telegram":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type"
        )

    telegram_user_id = payload.get("sub")

    if telegram_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload"
        )

    return int(telegram_user_id)


# ============================================================================
# REFRESH TOKEN FUNCTIONS
# ============================================================================


def create_refresh_token(user_id: int, db: Session) -> str:
    """
    Create a refresh token for long-term authentication

    Args:
        user_id: User ID
        db: Database session for storing token metadata

    Returns:
        Refresh token JWT string

    Note:
        Refresh tokens are stored in the database for revocation capability.
        The JTI (JWT ID) is stored and used to validate refresh tokens.
    """
    # Generate unique JTI (JWT ID) for refresh token
    jti = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
        days=settings.JWT_REFRESH_EXPIRATION_DAYS
    )

    # Store in database for validation and revocation
    user = db.query(User).filter_by(id=user_id).first()
    if user:
        user_obj = cast(Any, user)
        user_obj.refresh_token_jti = jti
        user_obj.refresh_token_expires_at = expires_at
        db.commit()

    # Create JWT with jti claim
    token_data = {
        "sub": str(user_id),
        "type": "refresh",
        "jti": jti,
        "exp": expires_at,
        "iat": datetime.now(timezone.utc).replace(tzinfo=None),
    }

    return jwt.encode(
        token_data, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def verify_refresh_token(token: str, db: Session) -> Optional[int]:
    """
    Verify refresh token and return user ID if valid

    Args:
        token: Refresh token string
        db: Database session for validation

    Returns:
        User ID if valid, None otherwise

    Note:
        This function validates:
        1. Token signature and expiration
        2. Token type is "refresh"
        3. JTI matches database record
        4. Database expiration hasn't been revoked
    """
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )

        # Verify it's a refresh token
        if payload.get("type") != "refresh":
            logger.warning("Token is not a refresh token")
            return None

        # Verify JTI matches database
        jti = payload.get("jti")
        user_id = int(payload.get("sub"))

        user = db.query(User).filter_by(id=user_id).first()
        if not user or user.refresh_token_jti != jti:
            logger.warning(
                f"Refresh token JTI not found in database for user {user_id}"
            )
            return None

        if user.is_deleted:
            logger.warning(f"Refresh token rejected for soft-deleted user {user_id}")
            return None

        # Check database expiration (allows token revocation)
        if (
            user.refresh_token_expires_at
            and user.refresh_token_expires_at
            < datetime.now(timezone.utc).replace(tzinfo=None)
        ):
            logger.warning(f"Refresh token expired in database for user {user_id}")
            return None

        return user_id

    except JWTError as e:
        logger.error(f"Refresh token verification failed: {str(e)}")
        return None
