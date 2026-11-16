from datetime import datetime
from typing import Optional

from sqlalchemy import TIMESTAMP, Boolean, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class FreeConfigGlobal(Base):
    """Superadmin singleton: global toggle, ceiling, cap, verification bot token."""

    __tablename__ = "free_config_global"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    default_daily_limit_mb: Mapped[int] = mapped_column(Integer, nullable=False, server_default="200")
    default_max_free_users: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_referral_bonus_mb: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1000"
    )
    verification_bot_token_enc: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    verification_bot_username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )
