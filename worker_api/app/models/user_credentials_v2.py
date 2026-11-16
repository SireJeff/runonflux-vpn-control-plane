"""
UserCredentialV2 model for FluxVPN Reseller Platform
Per-user VPN credentials with protocol-specific JSONB data
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import TIMESTAMP, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class UserCredentialV2(Base):
    """VPN credentials for an admin user - one record per protocol"""

    __tablename__ = "user_credentials_v2"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("admin_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    protocol: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # ssh/ss/vless/trojan/outline/http_proxy
    credential_data: Mapped[Any] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    # Relationships
    user = relationship("AdminUser", back_populates="credentials")

    __table_args__ = (UniqueConstraint("user_id", "protocol", name="uq_user_protocol"),)

    def __repr__(self):
        return f"<UserCredentialV2(id={self.id}, user_id={self.user_id}, protocol={self.protocol})>"
