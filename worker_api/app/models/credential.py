"""
Credential models
User credentials and protocol assignments
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import TIMESTAMP, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class UserCredential(Base):
    """Protocol-specific credentials (JSONB for flexibility)"""

    __tablename__ = "user_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subscription_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    protocol_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("protocols.id", ondelete="CASCADE"), nullable=False
    )
    credential_data: Mapped[Any] = mapped_column(
        JSONB, nullable=False
    )  # Protocol-specific credentials
    server_location: Mapped[Optional[str]] = mapped_column(
        String(100)
    )  # e.g., "Netherlands (Amsterdam)"
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    # Relationships
    user = relationship("User", back_populates="credentials")
    subscription = relationship("Subscription", back_populates="credentials")
    protocol = relationship("Protocol", back_populates="credentials")

    __table_args__ = (
        UniqueConstraint(
            "subscription_id", "protocol_id", name="uq_subscription_protocol"
        ),
    )

    def __repr__(self):
        return f"<UserCredential(id={self.id}, user_id={self.user_id}, protocol_id={self.protocol_id})>"


class UserProtocolAssignment(Base):
    """Maps users to specific protocol instances"""

    __tablename__ = "user_protocol_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subscription_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    protocol_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("protocols.id", ondelete="CASCADE"), nullable=False
    )
    instance_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("protocol_instances.id"), nullable=False, index=True
    )
    assigned_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )

    # Relationships
    user = relationship("User", back_populates="protocol_assignments")
    subscription = relationship("Subscription", back_populates="protocol_assignments")
    protocol = relationship("Protocol", back_populates="protocol_assignments")
    instance = relationship("ProtocolInstance", back_populates="user_assignments")

    __table_args__ = (
        UniqueConstraint(
            "subscription_id", "protocol_id", name="uq_assignment_subscription_protocol"
        ),
    )

    def __repr__(self):
        return f"<UserProtocolAssignment(id={self.id}, user_id={self.user_id}, instance_id={self.instance_id})>"
