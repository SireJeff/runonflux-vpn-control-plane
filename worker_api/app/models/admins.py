"""
Admin (Reseller) model for FluxVPN Reseller Platform
Manages reseller accounts, wallet balances, and approval workflow
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, TIMESTAMP, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func, text

from app.core.database import Base


class Admin(Base):
    """Admin/Reseller account - manages end users and VPN credentials"""

    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)  # bcrypt
    display_name: Mapped[Optional[str]] = mapped_column(String(100))
    telegram_id: Mapped[Optional[str]] = mapped_column(
        String(50)
    )  # For password delivery
    whatsapp_number: Mapped[Optional[str]] = mapped_column(String(20))
    phone_number: Mapped[Optional[str]] = mapped_column(String(20))
    wallet_balance: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 6), default=0.00
    )
    status: Mapped[Optional[str]] = mapped_column(
        String(20), default="pending"
    )  # pending/active/suspended/deleted
    broadcasts_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    assigned_password: Mapped[Optional[str]] = mapped_column(
        String(255)
    )  # Plain text for initial delivery
    notes: Mapped[Optional[str]] = mapped_column(Text)
    default_macro_region: Mapped[Optional[str]] = mapped_column(
        String(5), server_default="eu"
    )
    approved_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("admins.id"))
    approved_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    # Relationships
    users = relationship(
        "AdminUser", back_populates="admin", cascade="all, delete-orphan"
    )
    wire_orders = relationship(
        "WireOrder",
        back_populates="admin",
        foreign_keys="WireOrder.admin_id",
        cascade="all, delete-orphan",
    )
    wallet_transactions = relationship("WalletTransactionV2", back_populates="admin")
    traffic_logs_rel = relationship("TrafficLog", back_populates="admin")
    bot = relationship("AdminBot", back_populates="admin", uselist=False)
    packages = relationship(
        "AdminPackage", back_populates="admin", cascade="all, delete-orphan"
    )
    referral_config = relationship(
        "AdminReferralConfig",
        back_populates="admin",
        uselist=False,
        cascade="all, delete-orphan",
    )
    orders = relationship(
        "UserOrder",
        back_populates="admin",
        foreign_keys="UserOrder.admin_id",
    )

    def __repr__(self):
        return f"<Admin(id={self.id}, username={self.username}, status={self.status})>"
