"""FreeConfigService — per-reseller shared free public config.

kind='shared': one hidden system AdminUser (username '__free__<admin_id>') per reseller
holds the credentials everyone uses. Its ``subscription_token`` is stored in
``AdminFreeConfig.shared_credential_ref``.
"""

import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.core.constants import country_flag, get_country_name
from app.models.admin_free_config import AdminFreeConfig
from app.models.admin_users import AdminUser
from app.models.admins import Admin
from app.models.user_credentials_v2 import UserCredentialV2
from app.models.user_regions import UserRegion
from app.services.credentials.connection_string_service import ConnectionStringService
from app.services.credentials.reseller_credential_service import CredentialService
from app.services.regions.assignment import set_user_regions
from app.services.url_resolver import get_subscription_base_url

FREE_USERNAME_PREFIX = "__free__"


def free_username(admin_id: int) -> str:
    """Per-reseller name of the hidden free-config AdminUser.

    Must differ per reseller: usernames are a global namespace (VPN containers
    key Xray clients by username across ALL resellers), so a shared
    ``__free__`` would crash every VLESS/Trojan container once two resellers
    have one. See ``username_taken``.
    """
    return f"{FREE_USERNAME_PREFIX}{admin_id}"


class FreeConfigService:
    def __init__(self, db: Session):
        self.db = db

    def get_or_create(self, admin_id: int) -> AdminFreeConfig:
        """Return the admin's free config, creating a disabled default if absent."""
        config = (
            self.db.query(AdminFreeConfig)
            .filter(AdminFreeConfig.admin_id == admin_id)
            .first()
        )
        if config is None:
            config = AdminFreeConfig(admin_id=admin_id, is_enabled=False, kind="shared")
            self.db.add(config)
            self.db.commit()
            self.db.refresh(config)
        return config

    def update(
        self,
        admin_id: int,
        is_enabled: Optional[bool] = None,
        kind: Optional[str] = None,
        label: Optional[str] = None,
        region: Optional[str] = None,
        traffic_limit_gb: Optional[Decimal] = None,
        duration_days: Optional[int] = None,
        daily_limit_mb: Optional[int] = None,
        max_free_users: Optional[int] = None,
    ) -> AdminFreeConfig:
        """Patch the provided fields on the admin's free config, commit, return."""
        config = self.get_or_create(admin_id)
        if is_enabled is not None:
            config.is_enabled = is_enabled
        if kind is not None:
            config.kind = kind
        if label is not None:
            config.label = label
        if region is not None:
            config.region = region
        if traffic_limit_gb is not None:
            config.traffic_limit_gb = traffic_limit_gb
        if duration_days is not None:
            config.duration_days = duration_days
        if daily_limit_mb is not None:
            config.daily_limit_mb = daily_limit_mb
        if max_free_users is not None:
            config.max_free_users = max_free_users
        self.db.commit()
        self.db.refresh(config)
        return config

    def _get_or_create_free_user(self, admin_id: int) -> AdminUser:
        """Find/create the hidden system AdminUser (username '__free__<admin_id>')."""
        user = (
            self.db.query(AdminUser)
            .filter(
                AdminUser.admin_id == admin_id,
                AdminUser.username == free_username(admin_id),
            )
            .first()
        )
        if user is None:
            user = AdminUser(
                admin_id=admin_id,
                username=free_username(admin_id),
                status="active",
            )
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)
        return user

    def rotate(self, admin_id: int) -> AdminFreeConfig:
        """Refresh the shared credential: new token, limits, region, creds."""
        config = self.get_or_create(admin_id)
        user = self._get_or_create_free_user(admin_id)

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        user.subscription_token = secrets.token_hex(16)
        if config.traffic_limit_gb is not None:
            user.traffic_limit_bytes = int(
                Decimal(config.traffic_limit_gb) * (1024**3)
            )
        else:
            user.traffic_limit_bytes = None
        user.traffic_used_bytes = 0
        if config.duration_days is not None:
            user.expires_at = now + timedelta(days=int(config.duration_days))
        else:
            user.expires_at = None
        user.status = "active"

        region = config.region or (
            self.db.query(Admin.default_macro_region)
            .filter(Admin.id == admin_id)
            .scalar()
        )
        if region:
            set_user_regions(self.db, user, [region], now)

        CredentialService(self.db).generate_user_credentials(user)

        config.shared_credential_ref = user.subscription_token
        self.db.commit()
        self.db.refresh(config)
        return config

    def public_bundle(self, admin_id: int) -> Optional[dict]:
        """Return the public shared bundle, or None when disabled/unprovisioned."""
        config = self.get_or_create(admin_id)
        if not config.is_enabled or not config.shared_credential_ref:
            return None

        token = config.shared_credential_ref
        user = (
            self.db.query(AdminUser)
            .filter(
                AdminUser.admin_id == admin_id,
                AdminUser.username == free_username(admin_id),
            )
            .first()
        )

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if (
            user is None
            or user.status != "active"
            or user.subscription_token != token
            or (user.expires_at is not None and user.expires_at <= now)
            or (
                user.traffic_limit_bytes is not None
                and (user.traffic_used_bytes or 0) >= user.traffic_limit_bytes
            )
        ):
            return None
        if (
            not self.db.query(UserRegion.id)
            .filter(UserRegion.user_id == user.id, UserRegion.status == "active")
            .first()
        ):
            return None
        if (
            not self.db.query(UserCredentialV2.id)
            .filter(
                UserCredentialV2.user_id == user.id,
                UserCredentialV2.protocol.in_(["ss", "vless", "trojan", "outline"]),
            )
            .first()
        ):
            return None

        countries = []
        if user is not None:
            macro_region = config.region or (
                user.region.macro_region if user.region else "eu"
            )
            breakdown = ConnectionStringService(self.db).generate_country_breakdown(
                user, macro_region
            )
            countries = [
                (code, country_flag(code), get_country_name(code))
                for code in breakdown.keys()
            ]

        sub_url = (
            f"{get_subscription_base_url(self.db, admin_id)}"
            f"/api/v1/user/sub/{token}"
        )
        return {"sub_url": sub_url, "countries": countries, "label": config.label}
