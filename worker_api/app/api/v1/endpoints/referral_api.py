"""Reseller-facing API: referral config + earnings stats."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth.role_dependencies import RoleChecker
from app.core.database import get_db
from app.models.admin_referral import AdminReferralConfig, AdminReferralEarning
from app.models.admin_users import AdminUser
from app.models.admins import Admin
from app.models.free_config_global import FreeConfigGlobal
from app.schemas.referral import (
    ReferralConfigResponse,
    ReferralConfigUpdate,
    ReferralEarningResponse,
    ReferralStatsResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/referral", tags=["Referral"])


def _get_or_create_config(db: Session, admin_id: int) -> AdminReferralConfig:
    cfg = (
        db.query(AdminReferralConfig)
        .filter(AdminReferralConfig.admin_id == admin_id)
        .first()
    )
    if not cfg:
        cfg = AdminReferralConfig(admin_id=admin_id)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


@router.get("/config", response_model=ReferralConfigResponse)
def get_config(
    current: dict = Depends(RoleChecker(["admin", "super_admin"])),
    db: Session = Depends(get_db),
):
    return _get_or_create_config(db, current["id"])


@router.put("/config", response_model=ReferralConfigResponse)
def update_config(
    req: ReferralConfigUpdate,
    current: dict = Depends(RoleChecker(["admin"])),
    db: Session = Depends(get_db),
):
    cfg = _get_or_create_config(db, current["id"])
    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(cfg, field, value)
    # Clamp the reseller's max bonus to the superadmin global ceiling.
    g = db.query(FreeConfigGlobal).first()
    ceiling = (
        g.max_referral_bonus_mb if g and g.max_referral_bonus_mb is not None else None
    )
    if ceiling is not None and cfg.traffic_max_bonus_mb > ceiling:
        cfg.traffic_max_bonus_mb = ceiling
    db.commit()
    db.refresh(cfg)
    return cfg


@router.get("/stats", response_model=ReferralStatsResponse)
def get_stats(
    current: dict = Depends(RoleChecker(["admin"])),
    db: Session = Depends(get_db),
):
    admin_id = current["id"]
    total_referrals = (
        db.query(func.count(AdminUser.id))
        .filter(
            AdminUser.admin_id == admin_id,
            AdminUser.referred_by_user_id != None,  # noqa: E711
        )
        .scalar()
        or 0
    )
    total_earned = (
        db.query(func.coalesce(func.sum(AdminReferralEarning.amount_tomans), 0))
        .filter(AdminReferralEarning.admin_id == admin_id)
        .scalar()
    )
    admin: Admin = current["entity"]
    return ReferralStatsResponse(
        my_referral_code=f"ADMIN-{admin.username}",
        total_referrals=total_referrals,
        total_earned_tomans=total_earned,
        wallet_credit_tomans=admin.wallet_balance or 0,
    )


@router.get("/earnings", response_model=list[ReferralEarningResponse])
def list_earnings(
    current: dict = Depends(RoleChecker(["admin"])),
    db: Session = Depends(get_db),
    limit: int = 50,
):
    rows = (
        db.query(AdminReferralEarning)
        .filter(AdminReferralEarning.admin_id == current["id"])
        .order_by(AdminReferralEarning.created_at.desc())
        .limit(limit)
        .all()
    )
    return rows
