"""
Logging models
Connection and authentication logs (7-day retention)
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import TIMESTAMP, BigInteger, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class ConnectionLog(Base):
    """Connection metadata (7-day retention, no browsing history)"""

    __tablename__ = "connection_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    protocol_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("protocols.id"), nullable=False
    )
    instance_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("protocol_instances.id")
    )
    connected_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False)
    disconnected_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    bytes_uploaded: Mapped[Optional[int]] = mapped_column(BigInteger, default=0)
    bytes_downloaded: Mapped[Optional[int]] = mapped_column(BigInteger, default=0)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), index=True
    )

    # Relationships
    user = relationship("User", back_populates="connection_logs")
    instance = relationship("ProtocolInstance", back_populates="connection_logs")

    def __repr__(self):
        return f"<ConnectionLog(id={self.id}, user_id={self.user_id}, protocol_id={self.protocol_id})>"


class AuthLog(Base):
    """Authentication events (7-day retention)"""

    __tablename__ = "auth_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL")
    )
    event_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # login, logout, failed_attempt
    success: Mapped[Optional[bool]] = mapped_column(Boolean, default=True)
    ip_address: Mapped[Optional[str]] = mapped_column(
        INET
    )  # Only for fraud detection, deleted after 7 days
    user_agent: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), index=True
    )

    def __repr__(self):
        return f"<AuthLog(id={self.id}, user_id={self.user_id}, event={self.event_type}, success={self.success})>"
