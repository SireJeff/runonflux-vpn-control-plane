"""
User management endpoints
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_admin_user, get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models import AdminAlert, Subscription, User, WalletTransaction
from app.schemas import (
    ReferralStats,
    SubscriptionWithDetails,
    SuccessResponse,
    UserProfile,
    UserResponse,
    UserUpdate,
    WalletBalance,
    WalletHistory,
    WalletTransactionResponse,
)
from app.services.compliance.user_deletion import (
    get_pending_soft_deleted_users,
    schedule_user_soft_delete,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["Users"])


def _as_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


# ============================================================================
# CURRENT USER ENDPOINTS
# ============================================================================


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(current_user: User = Depends(get_current_user)):
    """
    Get current authenticated user's profile

    Returns complete user data including wallet balance, referrals, and trial status.
    """
    return UserResponse.model_validate(current_user)


@router.put("/me", response_model=UserResponse)
async def update_current_user(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update current user's profile

    Allows updating:
    - telegram_username
    - email
    - flux_wallet_address
    - language preference
    """
    logger.info(f"Updating user {current_user.id}")

    # Update fields if provided
    update_data = user_update.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(current_user, field, value)

    db.commit()
    db.refresh(current_user)

    logger.info(f"User {current_user.id} updated successfully")

    return UserResponse.model_validate(current_user)


@router.delete("/me", response_model=SuccessResponse)
async def delete_current_user(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """
    Delete current user account

    This is a soft delete - marks user as inactive.
    Actual data deletion happens after 30 days (GDPR compliance).
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    already_scheduled = bool(
        current_user.is_deleted and current_user.deletion_scheduled_at
    )
    scheduled_cleanup_at = schedule_user_soft_delete(
        current_user,
        requested_at=now,
        retention_days=settings.USER_DELETION_RETENTION_DAYS,
    )

    if not already_scheduled:
        logger.warning(
            f"User {current_user.id} requested account deletion. "
            f"Scheduled cleanup at {scheduled_cleanup_at.isoformat()}."
        )
        db.add(
            AdminAlert(
                alert_type="user_soft_delete_requested",
                priority="medium",
                title="User account deletion requested",
                message=(
                    f"User {current_user.id} requested account deletion. "
                    f"Scheduled cleanup: {scheduled_cleanup_at.isoformat()} UTC."
                ),
                acknowledged=False,
                extra_data={
                    "user_id": current_user.id,
                    "deleted_at": now.isoformat(),
                    "scheduled_cleanup_at": scheduled_cleanup_at.isoformat(),
                },
            )
        )
    else:
        logger.info(
            f"User {current_user.id} repeated account deletion request; "
            f"existing cleanup schedule retained at {scheduled_cleanup_at.isoformat()}."
        )

    db.commit()

    return SuccessResponse(
        message=(
            "Account deletion already scheduled."
            if already_scheduled
            else "Account deletion requested. Your data will be removed after the retention period."
        ),
        data={
            "user_id": current_user.id,
            "scheduled_cleanup_at": scheduled_cleanup_at.isoformat(),
            "retention_days": settings.USER_DELETION_RETENTION_DAYS,
        },
    )


# ============================================================================
# NOTIFICATION PREFERENCES ENDPOINTS
# ============================================================================


@router.put("/me/notifications")
async def toggle_notifications(
    enabled: bool = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Toggle user notification preferences"""
    current_user.notification_enabled = enabled
    db.commit()
    return {"notification_enabled": enabled}


@router.get("/me/notifications")
async def get_notification_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get user notification preferences"""
    return {"notification_enabled": current_user.notification_enabled}


# ============================================================================
# WALLET ENDPOINTS
# ============================================================================


@router.get("/me/wallet", response_model=WalletBalance)
async def get_wallet_balance(current_user: User = Depends(get_current_user)):
    """
    Get current user's wallet balance
    """
    return WalletBalance(
        user_id=current_user.id, wallet_balance=current_user.wallet_balance
    )


@router.get("/me/wallet/history", response_model=WalletHistory)
async def get_wallet_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
):
    """
    Get wallet transaction history

    Returns paginated list of wallet transactions including:
    - Deposits
    - Purchases
    - Withdrawals
    - Refunds
    - Referral commissions
    """
    # Get transactions
    transactions = (
        db.query(WalletTransaction)
        .filter_by(user_id=current_user.id)
        .order_by(WalletTransaction.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    # Calculate totals
    all_transactions = (
        db.query(WalletTransaction).filter_by(user_id=current_user.id).all()
    )

    total_deposits = sum(
        _as_decimal(t.amount_usd)
        for t in all_transactions
        if t.transaction_type == "deposit" and _as_decimal(t.amount_usd) > Decimal("0")
    )

    total_withdrawals = abs(
        sum(
            _as_decimal(t.amount_usd)
            for t in all_transactions
            if t.transaction_type == "withdrawal"
            and _as_decimal(t.amount_usd) < Decimal("0")
        )
    )

    total_spent = abs(
        sum(
            _as_decimal(t.amount_usd)
            for t in all_transactions
            if t.transaction_type == "purchase"
            and _as_decimal(t.amount_usd) < Decimal("0")
        )
    )

    return WalletHistory(
        current_balance=current_user.wallet_balance,
        total_deposits=Decimal(str(total_deposits)),
        total_withdrawals=Decimal(str(total_withdrawals)),
        total_spent=Decimal(str(total_spent)),
        transactions=[
            WalletTransactionResponse.model_validate(t) for t in transactions
        ],
    )


# ============================================================================
# USAGE ENDPOINTS
# ============================================================================


@router.get("/me/usage")
async def get_my_usage(
    days: int = Query(default=30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current user's bandwidth usage summary"""
    from app.services.usage.metrics_service import get_user_usage_summary

    summary = get_user_usage_summary(db, current_user.id, days)
    total_bytes = summary["bytes_uploaded"] + summary["bytes_downloaded"]
    return {
        "period_days": days,
        "bytes_uploaded": summary["bytes_uploaded"],
        "bytes_downloaded": summary["bytes_downloaded"],
        "total_bytes": total_bytes,
        "total_gb": round(total_bytes / (1024**3), 2),
        "connection_count": summary["connection_count"],
    }


@router.get(
    "/me/subscriptions/with-usage", response_model=List[SubscriptionWithDetails]
)
async def get_my_subscriptions_with_usage(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current user's subscriptions with usage data populated"""
    from app.services.usage.metrics_service import get_user_usage_summary

    subscriptions = (
        db.query(Subscription).filter_by(user_id=current_user.id, status="active").all()
    )

    results: List[SubscriptionWithDetails] = []
    for sub in subscriptions:
        # Calculate days elapsed since subscription started
        started_at = sub.started_at
        # started_at is always populated via server_default on insert; only
        # already-created (active) subscriptions reach this point.
        assert started_at is not None
        elapsed = (datetime.now(timezone.utc).replace(tzinfo=None) - started_at).days
        days = max(elapsed, 1)

        usage = get_user_usage_summary(db, current_user.id, days)
        total_bytes = usage["bytes_uploaded"] + usage["bytes_downloaded"]
        data_used_gb = Decimal(str(round(total_bytes / (1024**3), 2)))

        sub_dict = SubscriptionWithDetails.model_validate(sub).model_dump()
        sub_dict["data_used_gb"] = data_used_gb
        sub_dict["data_limit_gb"] = sub.plan.data_limit_gb if sub.plan else None

        results.append(SubscriptionWithDetails(**sub_dict))

    return results


# ============================================================================
# REFERRAL ENDPOINTS
# ============================================================================


@router.get("/me/referrals", response_model=ReferralStats)
async def get_referral_stats(current_user: User = Depends(get_current_user)):
    """
    Get referral program statistics

    Returns:
    - Referral code
    - Current tier (bronze, silver, gold, platinum)
    - Total referrals count
    - Total earnings from referrals
    - Current commission rate
    """
    # Commission rates by tier
    commission_rates = {
        "bronze": Decimal("10.00"),
        "silver": Decimal("15.00"),
        "gold": Decimal("20.00"),
        "platinum": Decimal("25.00"),
    }

    return ReferralStats(
        referral_code=current_user.referral_code,
        referral_tier=current_user.referral_tier,
        total_referrals=current_user.total_referrals,
        referral_earnings_usd=current_user.referral_earnings_usd,
        commission_rate=commission_rates.get(
            cast(str, current_user.referral_tier), Decimal("10.00")
        ),
    )


@router.get("/me/referrals/users", response_model=List[UserProfile])
async def get_referred_users(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
):
    """
    Get list of users referred by current user

    Returns paginated list of user profiles (public data only).
    """
    referred_users = (
        db.query(User)
        .filter_by(referred_by=current_user.id)
        .order_by(User.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [UserProfile.model_validate(user) for user in referred_users]


@router.post("/me/referrals/apply", response_model=SuccessResponse)
async def apply_referral_code(
    referral_code: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Apply a referral code to current user

    Can only be applied once per user.
    User must not have made any purchases yet.
    """
    # Check if user already has a referrer
    if current_user.referred_by is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You have already applied a referral code",
        )

    # Find referrer by code
    referrer = db.query(User).filter_by(referral_code=referral_code).first()

    if not referrer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invalid referral code"
        )

    # Can't refer yourself
    if referrer.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot refer yourself"
        )

    # Apply referral
    current_user.referred_by = referrer.id
    referrer.total_referrals = (referrer.total_referrals or 0) + 1

    db.commit()

    logger.info(f"User {current_user.id} applied referral code from user {referrer.id}")

    return SuccessResponse(
        message=f"Referral code applied successfully! You were referred by {referrer.telegram_username or 'User'}",
        data={"referrer_id": referrer.id},
    )


# ============================================================================
# ADMIN ENDPOINTS
# ============================================================================


class PendingDeletionStatus(BaseModel):
    """Admin view of users pending retention-expiry cleanup."""

    user_id: int
    telegram_user_id: int
    telegram_username: Optional[str]
    deleted_at: datetime
    deletion_scheduled_at: datetime
    retention_days_remaining: int


@router.get("/deletions/pending", response_model=List[PendingDeletionStatus])
async def list_pending_account_deletions(
    admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
):
    """
    List users in soft-deleted state awaiting retention-expiry cleanup.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    pending_users = get_pending_soft_deleted_users(db, now=now, limit=limit)

    response: List[PendingDeletionStatus] = []
    for user in pending_users:
        if user.deleted_at is None or user.deletion_scheduled_at is None:
            continue

        remaining_seconds = (user.deletion_scheduled_at - now).total_seconds()
        remaining_days = max(int(remaining_seconds // 86400), 0)

        response.append(
            PendingDeletionStatus(
                user_id=user.id,
                telegram_user_id=user.telegram_user_id,
                telegram_username=user.telegram_username,
                deleted_at=user.deleted_at,
                deletion_scheduled_at=user.deletion_scheduled_at,
                retention_days_remaining=remaining_days,
            )
        )

    logger.info(
        f"Admin {admin.id} requested pending deletion list ({len(response)} users)"
    )
    return response


@router.get("", response_model=List[UserResponse])
async def list_users(
    admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=100),
    search: Optional[str] = None,
):
    """
    List all users (Admin only)

    Supports search by:
    - Telegram username
    - Email
    - Referral code
    """
    query = db.query(User)

    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            (User.telegram_username.ilike(search_filter))
            | (User.email.ilike(search_filter))
            | (User.referral_code.ilike(search_filter))
        )

    users = query.order_by(User.created_at.desc()).offset(skip).limit(limit).all()

    return [UserResponse.model_validate(user) for user in users]


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Get specific user by ID (Admin only)
    """
    user = db.query(User).filter_by(id=user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    return UserResponse.model_validate(user)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_update: UserUpdate,
    admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Update specific user (Admin only)
    """
    user = db.query(User).filter_by(id=user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # Update fields
    update_data = user_update.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)

    logger.info(f"Admin {admin.id} updated user {user.id}")

    return UserResponse.model_validate(user)


@router.delete("/{user_id}", response_model=SuccessResponse)
async def delete_user(
    user_id: int,
    admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Delete specific user (Admin only)

    This permanently deletes the user and all related data.
    """
    user = db.query(User).filter_by(id=user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # Delete user (cascade will handle related records)
    db.delete(user)
    db.commit()

    logger.warning(f"Admin {admin.id} deleted user {user_id}")

    return SuccessResponse(
        message="User deleted successfully", data={"user_id": user_id}
    )
