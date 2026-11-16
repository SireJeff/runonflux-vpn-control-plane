from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.models.admin_free_config import AdminFreeConfig
from app.models.admins import Admin
from app.models.free_config_channel import FreeConfigChannel
from app.models.free_config_global import FreeConfigGlobal

MIB = 1024 * 1024
_DEFAULT_CEILING_MB = 200


@dataclass
class EffectivePolicy:
    enabled: bool
    required_channels: list  # of FreeConfigChannel
    daily_limit_mb: int
    daily_limit_bytes: int
    max_free_users: Optional[int]
    region: Optional[str]


def _channel_key(ch: FreeConfigChannel):
    if ch.chat_id is not None:
        return ("id", ch.chat_id)
    return ("user", (ch.username or "").lower().lstrip("@"))


def resolve_free_config_policy(db: Session, admin_id: int) -> EffectivePolicy:
    """Compose global + reseller free-config settings into one effective policy."""
    g = db.query(FreeConfigGlobal).first()
    reseller = (
        db.query(AdminFreeConfig).filter(AdminFreeConfig.admin_id == admin_id).first()
    )
    admin = db.query(Admin).filter(Admin.id == admin_id).first()

    ceiling = g.default_daily_limit_mb if g else _DEFAULT_CEILING_MB
    token_present = bool(g and g.verification_bot_token_enc)
    enabled = bool(
        g and g.is_enabled
        and reseller and reseller.is_enabled and reseller.kind == "per_user"
        and token_present
    )

    reseller_limit = reseller.daily_limit_mb if (reseller and reseller.daily_limit_mb is not None) else None
    daily_limit_mb = min(reseller_limit if reseller_limit is not None else ceiling, ceiling)

    max_free_users = None
    if reseller and reseller.max_free_users is not None:
        max_free_users = reseller.max_free_users
    elif g and g.default_max_free_users is not None:
        max_free_users = g.default_max_free_users

    region = (reseller.region if reseller and reseller.region else None) or (
        admin.default_macro_region if admin else None
    )

    channels = (
        db.query(FreeConfigChannel)
        .filter(
            FreeConfigChannel.is_active.is_(True),
            (FreeConfigChannel.admin_id.is_(None)) | (FreeConfigChannel.admin_id == admin_id),
        )
        .all()
    )
    seen, deduped = set(), []
    for ch in channels:
        k = _channel_key(ch)
        if k in seen:
            continue
        seen.add(k)
        deduped.append(ch)

    return EffectivePolicy(
        enabled=enabled,
        required_channels=deduped,
        daily_limit_mb=daily_limit_mb,
        daily_limit_bytes=daily_limit_mb * MIB,
        max_free_users=max_free_users,
        region=region,
    )
