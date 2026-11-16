"""Reseller-driven manual subscription adjustments. Every method records one
UserAdjustment audit row. Methods mutate + db.add(audit) but do NOT commit —
the calling endpoint owns the transaction.
"""
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.admin_packages import AdminPackage
from app.models.admin_users import AdminUser
from app.models.user_adjustments import UserAdjustment
from app.models.user_credentials_v2 import (  # noqa: F401 (kept for parity)
    UserCredentialV2,
)
from app.services.credentials.reseller_credential_service import CredentialService
from app.services.credentials.username_generator import username_taken
from app.services.regions.assignment import set_user_regions
from app.services.subscriptions.renewal_service import compute_new_expiry

_GB = 1024**3
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,50}$")


class AdjustmentService:
    def __init__(self, db: Session):
        self.db = db

    def _now(self) -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    def _audit(self, user_id, admin_id, action, details, reason) -> UserAdjustment:
        adj = UserAdjustment(
            user_id=user_id,
            admin_id=admin_id,
            action=action,
            details=details,
            reason=reason,
        )
        self.db.add(adj)
        return adj

    def extend_days(
        self, user: AdminUser, admin_id: int, days: int, reason=None
    ) -> UserAdjustment:
        before = user.expires_at
        user.expires_at = compute_new_expiry(user.expires_at, days, self._now())
        return self._audit(
            user.id,
            admin_id,
            "extend_days",
            {
                "days": days,
                "from": before.isoformat() if before else None,
                "to": user.expires_at.isoformat(),
            },
            reason,
        )

    def topup_gb(
        self, user: AdminUser, admin_id: int, gb, reason=None
    ) -> UserAdjustment:
        current = user.traffic_limit_bytes or 0
        added = int(float(gb) * _GB)
        user.traffic_limit_bytes = current + added
        return self._audit(
            user.id,
            admin_id,
            "topup_gb",
            {
                "gb": float(gb),
                "new_limit_bytes": user.traffic_limit_bytes,
            },
            reason,
        )

    def set_expiry(
        self, user: AdminUser, admin_id: int, when: datetime, reason=None
    ) -> UserAdjustment:
        before = user.expires_at
        if when is not None and when.tzinfo is not None:
            when = when.astimezone(timezone.utc).replace(tzinfo=None)
        user.expires_at = when
        return self._audit(
            user.id,
            admin_id,
            "set_expiry",
            {
                "from": before.isoformat() if before else None,
                "to": when.isoformat() if when else None,
            },
            reason,
        )

    def reapply_plan(
        self, user: AdminUser, admin_id: int, package: AdminPackage, reason=None
    ) -> UserAdjustment:
        now = self._now()
        user.expires_at = compute_new_expiry(
            user.expires_at, package.duration_days, now
        )
        user.traffic_limit_bytes = int(float(package.traffic_limit_gb) * _GB)
        user.traffic_used_bytes = 0
        user.status = "active"
        return self._audit(
            user.id,
            admin_id,
            "reapply_plan",
            {
                "package_id": package.id,
                "duration_days": package.duration_days,
                "traffic_gb": float(package.traffic_limit_gb),
            },
            reason,
        )

    def edit_regions(
        self, user: AdminUser, admin_id: int, macro_regions: list[str], reason=None
    ) -> UserAdjustment:
        set_user_regions(self.db, user, macro_regions, self._now())
        return self._audit(
            user.id,
            admin_id,
            "edit_regions",
            {
                "regions": macro_regions,
            },
            reason,
        )

    def set_username(
        self, user: AdminUser, admin_id: int, new_username: str, reason=None
    ) -> UserAdjustment:
        old = user.username
        new_username = (new_username or "").strip()
        if new_username == old:
            raise ValueError("username_unchanged")
        if not _USERNAME_RE.match(new_username):
            raise ValueError("username_invalid")
        # Global, case-insensitive namespace (any reseller), excluding the user
        # being renamed.
        if username_taken(self.db, new_username, exclude_user_id=user.id):
            raise ValueError("username_taken")
        user.username = new_username
        reprovisioned = CredentialService(self.db).reprovision_username(user)
        return self._audit(
            user.id,
            admin_id,
            "set_username",
            {
                "from": old,
                "to": new_username,
                "reprovisioned": reprovisioned,
            },
            reason,
        )

    def set_telegram(
        self, user: AdminUser, admin_id: int, telegram_id, telegram_chat_id, reason=None
    ) -> UserAdjustment:
        before = {
            "telegram_id": user.telegram_id,
            "telegram_chat_id": user.telegram_chat_id,
        }
        if telegram_id is not None:
            clash = (
                self.db.query(AdminUser)
                .filter(
                    AdminUser.admin_id == user.admin_id,
                    AdminUser.telegram_id == telegram_id,
                    AdminUser.id != user.id,
                )
                .first()
            )
            if clash is not None:
                raise ValueError("telegram_taken")
        user.telegram_id = telegram_id
        user.telegram_chat_id = telegram_chat_id
        return self._audit(
            user.id,
            admin_id,
            "set_telegram",
            {
                "from": before,
                "to": {
                    "telegram_id": telegram_id,
                    "telegram_chat_id": telegram_chat_id,
                },
            },
            reason,
        )

    def reset_used_traffic(
        self, user: AdminUser, admin_id: int, reason=None
    ) -> UserAdjustment:
        before = user.traffic_used_bytes or 0
        user.traffic_used_bytes = 0
        return self._audit(
            user.id,
            admin_id,
            "reset_traffic",
            {"from_bytes": before, "to_bytes": 0},
            reason,
        )

    def set_traffic_limit(
        self, user: AdminUser, admin_id: int, gb, reason=None
    ) -> UserAdjustment:
        before = user.traffic_limit_bytes
        user.traffic_limit_bytes = None if gb is None else int(float(gb) * _GB)
        return self._audit(
            user.id,
            admin_id,
            "set_traffic_limit",
            {
                "from_bytes": before,
                "to_bytes": user.traffic_limit_bytes,
            },
            reason,
        )

    def set_status(
        self, user: AdminUser, admin_id: int, active: bool, reason=None
    ) -> UserAdjustment:
        before = user.status
        if active:
            CredentialService(self.db).generate_user_credentials(user, commit=False)
        else:
            from app.models.free_config_enrollment import FreeConfigEnrollment

            enrollment = (
                self.db.query(FreeConfigEnrollment)
                .filter(FreeConfigEnrollment.user_id == user.id)
                .first()
            )
            if enrollment is not None:
                enrollment.suspended_reason = "manual"
        user.status = "active" if active else "suspended"
        return self._audit(
            user.id,
            admin_id,
            "activate" if active else "suspend",
            {
                "from": before,
                "to": user.status,
            },
            reason,
        )

    def record_password_reset(
        self, user: AdminUser, admin_id: int, reason=None
    ) -> UserAdjustment:
        return self._audit(
            user.id, admin_id, "reset_password", {"changed": True}, reason
        )
