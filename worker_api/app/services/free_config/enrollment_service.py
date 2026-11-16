from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.constants import MACRO_REGIONS
from app.models.admin_users import AdminUser
from app.models.free_config_enrollment import FreeConfigEnrollment
from app.models.user_regions import UserRegion
from app.services.credentials.reseller_credential_service import CredentialService
from app.services.free_config.policy import EffectivePolicy
from app.services.referral.bonus_service import ReferralBonusService
from app.services.referral.codes import ensure_referral_code
from app.services.regions.assignment import set_user_regions


class FreeSlotsFullError(Exception):
    """Raised when a reseller is at its max_free_users cap."""


class FreeConfigUnavailableError(ValueError):
    """A claim cannot safely provision this account under the current policy."""


class FreeConfigEnrollmentService:
    def __init__(self, db: Session):
        self.db = db

    def count_for_admin(self, admin_id: int) -> int:
        return (
            self.db.query(FreeConfigEnrollment)
            .filter(FreeConfigEnrollment.admin_id == admin_id)
            .count()
        )

    def get_enrollment(self, user_id: int):
        return (
            self.db.query(FreeConfigEnrollment)
            .filter(FreeConfigEnrollment.user_id == user_id)
            .first()
        )

    def _reactivate(self, user: AdminUser, enr: FreeConfigEnrollment) -> None:
        if enr.suspended_reason == "membership":
            user.status = "active"
            enr.membership_ok = True
            enr.suspended_reason = None

    def provision(
        self, user: AdminUser, policy: EffectivePolicy
    ) -> FreeConfigEnrollment:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if not policy.enabled or policy.region not in MACRO_REGIONS:
            raise FreeConfigUnavailableError(
                "Free config requires an enabled policy and region"
            )
        # Serialize repeat button presses before looking up the enrollment.
        user = (
            self.db.query(AdminUser)
            .filter(AdminUser.id == user.id)
            .with_for_update()
            .populate_existing()
            .one()
        )
        existing = self.get_enrollment(user.id)
        # A claim is not an entitlement conversion or an operator unsuspend.
        # Paid/manual plans (including expired ones) require explicit handling.
        if user.current_order_id is not None or user.expires_at is not None:
            raise FreeConfigUnavailableError("Existing subscription must be preserved")
        if existing:
            if user.status != "active" and not (
                user.status == "suspended" and existing.suspended_reason == "membership"
            ):
                raise FreeConfigUnavailableError(
                    "Account is not available for a free claim"
                )
            region = (
                self.db.query(UserRegion)
                .filter(UserRegion.user_id == user.id, UserRegion.status == "active")
                .first()
            )
            if region is None:
                set_user_regions(self.db, user, [policy.region], now)
            CredentialService(self.db).generate_user_credentials(user, commit=False)
            self._reactivate(user, existing)
            self.db.commit()
            return existing

        if user.status != "lead":
            raise FreeConfigUnavailableError("Existing account must be preserved")

        if (
            policy.max_free_users is not None
            and self.count_for_admin(user.admin_id) >= policy.max_free_users
        ):
            raise FreeSlotsFullError()

        user.traffic_limit_bytes = policy.daily_limit_bytes
        user.traffic_used_bytes = 0
        user.status = "active"
        ensure_referral_code(user)
        if not user.subscription_token:
            import secrets

            user.subscription_token = secrets.token_hex(16)
        set_user_regions(self.db, user, [policy.region], now)
        self.db.flush()

        CredentialService(self.db).generate_user_credentials(user, commit=False)

        enr = FreeConfigEnrollment(
            user_id=user.id,
            admin_id=user.admin_id,
            claimed_at=now,
            membership_ok=True,
        )
        self.db.add(enr)
        self.db.commit()
        self.db.refresh(enr)

        # This new active free user now counts toward their referrer's traffic bonus.
        if user.referred_by_user_id:
            referrer = (
                self.db.query(AdminUser)
                .filter(AdminUser.id == user.referred_by_user_id)
                .first()
            )
            if referrer is not None:
                ReferralBonusService(self.db).apply_effective_limit(referrer)
                self.db.commit()
        return enr
