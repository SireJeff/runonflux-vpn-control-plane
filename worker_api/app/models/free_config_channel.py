from datetime import datetime
from typing import Optional

from sqlalchemy import (
    TIMESTAMP, BigInteger, Boolean, ForeignKey, Integer, String,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class FreeConfigChannel(Base):
    """A required Telegram channel for per-user free config.

    admin_id NULL => global (superadmin) channel; else reseller-scoped.
    """

    __tablename__ = "free_config_channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    admin_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("admins.id", ondelete="CASCADE"), nullable=True, index=True
    )
    chat_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False, server_default="")
    invite_url: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )
