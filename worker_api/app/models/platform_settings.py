"""
PlatformSetting model for FluxVPN Reseller Platform
Key-value configuration store for platform-wide settings
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import TIMESTAMP, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class PlatformSetting(Base):
    """Platform-wide key-value configuration setting"""

    __tablename__ = "platform_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    def __repr__(self):
        return f"<PlatformSetting(id={self.id}, key={self.key})>"
