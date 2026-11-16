"""
IP Management models
Protocol instances, IP change requests, and quotas
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    Date,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class ProtocolInstance(Base):
    """Protocol instances deployed on FluxCloud - supports multi-component apps"""

    __tablename__ = "protocol_instances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    protocol_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("protocols.id", ondelete="CASCADE"), nullable=False
    )
    flux_app_name: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )  # e.g., 'fluxvpn-nl-01'
    component_name: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # e.g., 'vless', 'ssh' - for multi-component apps
    instance_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-40
    flux_node_name: Mapped[Optional[str]] = mapped_column(
        String(255)
    )  # e.g., 'nl-ams-01.flux.io'
    ip_address: Mapped[str] = mapped_column(INET, nullable=False, index=True)
    country_code: Mapped[str] = mapped_column(
        String(2), nullable=False, index=True
    )  # ISO 3166-1 alpha-2 (e.g., 'NL', 'US')
    country_name: Mapped[str] = mapped_column(String(100), nullable=False)
    city: Mapped[Optional[str]] = mapped_column(String(100))
    last_health_check: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    health_status: Mapped[Optional[str]] = mapped_column(
        String(50), default="unknown"
    )  # healthy, unhealthy, unknown
    is_active: Mapped[Optional[bool]] = mapped_column(Boolean, default=True, index=True)
    current_connections: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    max_connections: Mapped[Optional[int]] = mapped_column(Integer, default=100)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    # Relationships
    protocol = relationship("Protocol", back_populates="instances")
    user_assignments = relationship("UserProtocolAssignment", back_populates="instance")
    connection_logs = relationship("ConnectionLog", back_populates="instance")

    __table_args__ = (
        UniqueConstraint(
            "flux_app_name",
            "component_name",
            "instance_number",
            name="uq_app_component_instance",
        ),
    )

    def __repr__(self):
        return f"<ProtocolInstance(id={self.id}, protocol_id={self.protocol_id}, instance={self.instance_number}, country={self.country_code})>"


class IPChangeRequest(Base):
    """User requests to change server location"""

    __tablename__ = "ip_change_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    subscription_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False
    )
    protocol_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("protocols.id", ondelete="CASCADE"), nullable=False
    )
    old_instance_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("protocol_instances.id")
    )
    new_instance_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("protocol_instances.id")
    )
    requested_country_code: Mapped[Optional[str]] = mapped_column(String(2))
    status: Mapped[Optional[str]] = mapped_column(
        String(50), default="pending", index=True
    )  # pending, completed, failed, denied
    denial_reason: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)

    # Relationships
    user = relationship("User", back_populates="ip_change_requests")
    old_instance = relationship("ProtocolInstance", foreign_keys=[old_instance_id])
    new_instance = relationship("ProtocolInstance", foreign_keys=[new_instance_id])

    def __repr__(self):
        return f"<IPChangeRequest(id={self.id}, user_id={self.user_id}, status={self.status})>"


class IPChangeQuota(Base):
    """Daily IP change limits by subscription tier"""

    __tablename__ = "ip_change_quota"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(
        Date, nullable=False, server_default=func.current_date()
    )
    changes_used: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    daily_limit: Mapped[int] = mapped_column(Integer, nullable=False)

    # Relationships
    user = relationship("User", back_populates="ip_change_quotas")

    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_user_date"),)

    def __repr__(self):
        return f"<IPChangeQuota(id={self.id}, user_id={self.user_id}, used={self.changes_used}/{self.daily_limit})>"
