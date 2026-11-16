"""Referral traffic bonus: count qualifying referrals and apply the derived limit."""

from datetime import datetime

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.models.admin_referral import AdminReferralConfig
from app.models.admin_users import AdminUser
from app.models.free_config_enrollment import FreeConfigEnrollment
from app.models.free_config_global import FreeConfigGlobal
from app.services.free_config.policy import MIB, resolve_free_config_policy

_TRAFFIC_MODES = ("traffic", "both")


class ReferralBonusService:
    def __init__(self, db: Session):
        self.db = db

    def count_qualifying(self, referrer_id: int, admin_id: int) -> int:
        now_naive = datetime.utcnow()
        free_branch = and_(
            FreeConfigEnrollment.id.isnot(None),
            FreeConfigEnrollment.membership_ok.is_(True),
            AdminUser.status != "suspended",
        )
        paid_branch = and_(
            AdminUser.status == "active",
            AdminUser.expires_at.isnot(None),
            AdminUser.expires_at > now_naive,
        )
        return (
            self.db.query(func.count(AdminUser.id))
            .outerjoin(
                FreeConfigEnrollment,
                FreeConfigEnrollment.user_id == AdminUser.id,
            )
            .filter(
                AdminUser.admin_id == admin_id,
                AdminUser.referred_by_user_id == referrer_id,
                or_(free_branch, paid_branch),
            )
            .scalar()
            or 0
        )

    def compute_bonus_mb(self, user: AdminUser) -> int:
        cfg = (
            self.db.query(AdminReferralConfig)
            .filter(AdminReferralConfig.admin_id == user.admin_id)
            .first()
        )
        if not cfg or not cfg.is_enabled or cfg.reward_type not in _TRAFFIC_MODES:
            return 0
        per = cfg.traffic_per_referral_mb or 0
        max_bonus = cfg.traffic_max_bonus_mb or 0
        if per <= 0 or max_bonus <= 0:
            return 0

        g = self.db.query(FreeConfigGlobal).first()
        ceiling = (
            g.max_referral_bonus_mb
            if g and g.max_referral_bonus_mb is not None
            else max_bonus
        )
        capped_max = min(max_bonus, ceiling)

        count = self.count_qualifying(user.id, user.admin_id)
        return min(count * per, capped_max)

    def apply_effective_limit(self, user: AdminUser) -> None:
        """Set traffic_limit_bytes = base + bonus for a current free-config user."""
        enr = (
            self.db.query(FreeConfigEnrollment)
            .filter(FreeConfigEnrollment.user_id == user.id)
            .first()
        )
        if enr is None:
            return  # not a free-config user; nothing to boost
        exp = user.expires_at
        if exp is not None:
            if exp.tzinfo is not None:
                exp = exp.replace(tzinfo=None)
            if exp > datetime.utcnow():
                return  # active paid plan governs the limit
        policy = resolve_free_config_policy(self.db, user.admin_id)
        bonus_bytes = self.compute_bonus_mb(user) * MIB
        user.traffic_limit_bytes = policy.daily_limit_bytes + bonus_bytes
        self.db.flush()
