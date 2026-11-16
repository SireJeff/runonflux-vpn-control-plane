"""
Subscription management endpoints
"""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, List, Optional, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models import Protocol, Subscription, SubscriptionPlan, User, WalletTransaction
from app.schemas import (
    ProtocolResponse,
    SubscriptionResponse,
    SubscriptionUpdate,
    SuccessResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


class SubscriptionPurchaseRequest(BaseModel):
    """Request body for wallet-based subscription purchases."""

    plan_id: int = Field(..., gt=0)
    auto_renew: bool = True


def _as_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _plan_duration_delta(plan: SubscriptionPlan) -> timedelta:
    months = int(plan.duration_months or 1)
    return timedelta(days=30 * max(months, 1))


# ============================================================================
# SUBSCRIPTION PLANS
# ============================================================================


@router.get("/plans", response_model=List[ProtocolResponse])
async def list_subscription_plans(
    db: Session = Depends(get_db), is_active: bool = Query(default=True)
):
    """List available protocol plans."""
    query = db.query(Protocol)
    if is_active is not None:
        query = query.filter(Protocol.is_active == is_active)
    protocols = query.order_by(Protocol.id).all()
    return [ProtocolResponse.model_validate(protocol) for protocol in protocols]


@router.get("/plans/{protocol_id}", response_model=ProtocolResponse)
async def get_subscription_plan(protocol_id: int, db: Session = Depends(get_db)):
    """Get details of a specific protocol plan."""
    protocol = db.query(Protocol).filter_by(id=protocol_id).first()
    if not protocol:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Subscription plan not found"
        )
    return ProtocolResponse.model_validate(protocol)


# ============================================================================
# USER SUBSCRIPTIONS
# ============================================================================


@router.get("", response_model=List[SubscriptionResponse])
async def list_user_subscriptions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    is_active: Optional[bool] = None,
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
):
    """List current user's subscriptions."""
    query = db.query(Subscription).filter_by(user_id=current_user.id)
    if is_active is not None:
        query = query.filter(Subscription.is_active == is_active)

    subscriptions = (
        query.order_by(Subscription.created_at.desc()).offset(offset).limit(limit).all()
    )
    return [SubscriptionResponse.model_validate(sub) for sub in subscriptions]


@router.get("/{subscription_id}", response_model=SubscriptionResponse)
async def get_subscription(
    subscription_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get details of a specific subscription."""
    subscription = (
        db.query(Subscription)
        .filter_by(id=subscription_id, user_id=current_user.id)
        .first()
    )
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found"
        )
    return SubscriptionResponse.model_validate(subscription)


# ============================================================================
# SUBSCRIPTION PURCHASE
# ============================================================================


@router.post(
    "/purchase",
    response_model=SubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def purchase_subscription(
    subscription_data: SubscriptionPurchaseRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Purchase a subscription plan using wallet balance."""
    plan = db.query(SubscriptionPlan).filter_by(id=subscription_data.plan_id).first()
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription plan not found",
        )

    price = _as_decimal(plan.price_usd)
    wallet_balance = _as_decimal(current_user.wallet_balance)
    if wallet_balance < price:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Insufficient balance. Required: ${price}, "
                f"Available: ${wallet_balance}"
            ),
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    expires_at = now + _plan_duration_delta(plan)

    subscription = Subscription(
        user_id=current_user.id,
        plan_id=plan.id,
        status="active",
        is_active=True,
        is_trial=False,
        started_at=now,
        expires_at=expires_at,
        auto_renew=subscription_data.auto_renew,
    )
    db.add(subscription)

    current_user.wallet_balance = wallet_balance - price

    db.flush()
    db.add(
        WalletTransaction(
            user_id=current_user.id,
            amount_usd=-price,
            transaction_type="purchase",
            subscription_id=subscription.id,
            status="completed",
            description=f"Subscription purchase: {plan.name}",
            reference_id=f"sub_{subscription.id}_{int(now.timestamp())}",
        )
    )

    db.commit()
    db.refresh(subscription)

    logger.info(
        "Subscription %s created for user %s using plan %s",
        subscription.id,
        current_user.id,
        plan.id,
    )

    return SubscriptionResponse.model_validate(subscription)


# ============================================================================
# SUBSCRIPTION MANAGEMENT
# ============================================================================


@router.put("/{subscription_id}", response_model=SubscriptionResponse)
async def update_subscription(
    subscription_id: int,
    subscription_update: SubscriptionUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update mutable subscription settings."""
    subscription = (
        db.query(Subscription)
        .filter_by(id=subscription_id, user_id=current_user.id)
        .first()
    )
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found"
        )

    update_data = subscription_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(subscription, field, value)

    db.commit()
    db.refresh(subscription)

    return SubscriptionResponse.model_validate(subscription)


@router.post("/{subscription_id}/renew", response_model=SubscriptionResponse)
async def renew_subscription(
    subscription_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Manually renew a subscription using wallet balance."""
    subscription = (
        db.query(Subscription)
        .filter_by(id=subscription_id, user_id=current_user.id)
        .first()
    )
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found"
        )

    plan = subscription.plan
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subscription plan is missing",
        )

    price = _as_decimal(plan.price_usd)
    wallet_balance = _as_decimal(current_user.wallet_balance)
    if wallet_balance < price:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Insufficient balance. Required: ${price}, "
                f"Available: ${wallet_balance}"
            ),
        )

    current_user.wallet_balance = wallet_balance - price

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    renewal_delta = _plan_duration_delta(plan)
    subscription_obj = cast(Any, subscription)
    current_expires_at = subscription.expires_at
    if current_expires_at is None or current_expires_at < now:
        subscription_obj.started_at = now
        subscription_obj.expires_at = now + renewal_delta
    else:
        subscription_obj.expires_at = current_expires_at + renewal_delta

    subscription_obj.status = "active"
    subscription_obj.is_active = True

    db.add(
        WalletTransaction(
            user_id=current_user.id,
            amount_usd=-price,
            transaction_type="purchase",
            subscription_id=subscription.id,
            status="completed",
            description=f"Subscription renewal: {plan.name}",
            reference_id=f"renew_{subscription.id}_{int(now.timestamp())}",
        )
    )

    db.commit()
    db.refresh(subscription)

    return SubscriptionResponse.model_validate(subscription)


@router.delete("/{subscription_id}", response_model=SuccessResponse)
async def cancel_subscription(
    subscription_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cancel auto-renewal for a subscription."""
    subscription = (
        db.query(Subscription)
        .filter_by(id=subscription_id, user_id=current_user.id)
        .first()
    )
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found"
        )

    subscription_obj = cast(Any, subscription)
    subscription_obj.auto_renew = False
    if subscription.status == "active":
        subscription_obj.status = "cancelled"

    db.commit()

    end_date = subscription.expires_at
    return SuccessResponse(
        message=(
            "Subscription cancelled successfully. "
            f"Access continues until {end_date.strftime('%Y-%m-%d %H:%M UTC')}"
        ),
        data={
            "subscription_id": subscription_id,
            "end_date": end_date.isoformat(),
        },
    )


# ============================================================================
# TRIAL ACTIVATION
# ============================================================================


@router.post(
    "/trial/activate",
    response_model=SubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def activate_trial(
    protocol_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Activate a one-time free trial subscription."""
    if current_user.trial_used:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You have already used your free trial",
        )

    active_sub = (
        db.query(Subscription)
        .filter(
            Subscription.user_id == current_user.id,
            Subscription.is_active == True,
            Subscription.expires_at > datetime.now(timezone.utc).replace(tzinfo=None),
        )
        .first()
    )
    if active_sub:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot activate trial while you have an active subscription",
        )

    protocol = db.query(Protocol).filter_by(id=protocol_id, is_active=True).first()
    if not protocol:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Protocol not found or is not active",
        )

    trial_plan = (
        db.query(SubscriptionPlan)
        .filter(
            SubscriptionPlan.duration_months == 0,
            cast(Any, SubscriptionPlan.price_usd) == Decimal("0.00"),
        )
        .order_by(SubscriptionPlan.id.asc())
        .first()
    )
    if not trial_plan:
        trial_plan = SubscriptionPlan(
            name="Trial Plan",
            tier="bronze",
            duration_months=0,
            price_usd=Decimal("0.00"),
            max_protocols=1,
            max_connections=1,
            data_limit_gb=10,
            daily_ip_changes=1,
        )
        db.add(trial_plan)
        db.flush()

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    subscription = Subscription(
        user_id=current_user.id,
        plan_id=trial_plan.id,
        status="active",
        is_active=True,
        is_trial=True,
        started_at=now,
        expires_at=now + timedelta(days=max(settings.TRIAL_DURATION_DAYS, 1)),
        auto_renew=False,
    )

    current_user_obj = cast(Any, current_user)
    current_user_obj.trial_used = True
    current_user_obj.trial_started_at = now
    current_user_obj.trial_expires_at = subscription.expires_at

    db.add(subscription)
    db.commit()
    db.refresh(subscription)

    logger.info(
        "Trial subscription %s activated for user %s (protocol hint %s)",
        subscription.id,
        current_user.id,
        protocol_id,
    )

    return SubscriptionResponse.model_validate(subscription)
