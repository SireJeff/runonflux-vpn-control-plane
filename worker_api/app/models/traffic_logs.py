"""
TrafficLog model for FluxVPN Reseller Platform
Traffic consumption tracking per user session
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import TIMESTAMP, BigInteger, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class TrafficLog(Base):
    """Per-session traffic consumption record"""

    __tablename__ = "traffic_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("admin_users.id"), nullable=False, index=True
    )
    admin_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("admins.id"), nullable=False, index=True
    )
    protocol: Mapped[str] = mapped_column(String(20), nullable=False)
    region_code: Mapped[str] = mapped_column(String(5), nullable=False)
    bytes_in: Mapped[Optional[int]] = mapped_column(BigInteger, default=0)
    bytes_out: Mapped[Optional[int]] = mapped_column(BigInteger, default=0)
    session_started_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    session_ended_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    instance_ip: Mapped[Optional[str]] = mapped_column(String(45))
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), index=True
    )

    # Relationships
    user = relationship("AdminUser", back_populates="traffic_logs")
    admin = relationship("Admin", back_populates="traffic_logs_rel")

    def __repr__(self):
        return f"<TrafficLog(id={self.id}, user_id={self.user_id}, protocol={self.protocol}, region={self.region_code})>"
