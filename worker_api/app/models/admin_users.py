"""
AdminUser model for FluxVPN Reseller Platform
End users created and managed by admin resellers
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class AdminUser(Base):
    """End user managed by an admin reseller"""

    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    admin_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("admins.id", ondelete="CASCADE"), nullable=False, index=True
    )
    username: Mapped[str] = mapped_column(String(50), nullable=False)
    password_hash: Mapped[Optional[str]] = mapped_column(
        String(255)
    )  # For read-only portal
    password_enc: Mapped[Optional[bytes]] = mapped_column(
        LargeBinary
    )  # AES-GCM encrypted plaintext, for display
    display_name: Mapped[Optional[str]] = mapped_column(String(100))
    remark: Mapped[Optional[str]] = mapped_column(Text)  # Admin's note
    status: Mapped[Optional[str]] = mapped_column(
        String(20), default="active"
    )  # active/suspended/deleted
    traffic_used_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, default=0)
    traffic_limit_bytes: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True, default=None
    )  # NULL = unlimited
    subscription_token: Mapped[Optional[str]] = mapped_column(
        String(64), unique=True, index=True, nullable=True
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    last_connection_refresh_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, nullable=True
    )
    assigned_domain_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("fdm_domains.id", ondelete="SET NULL"), nullable=True
    )
    telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    telegram_chat_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    registered_bot_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("admin_bots.id", ondelete="SET NULL"),
        nullable=True,
    )
    current_order_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        # admin_users <-> user_orders form a mutual FK cycle (user_orders.user_id
        # -> admin_users.id, and this back-pointer -> user_orders.id). use_alter
        # makes SQLAlchemy emit this constraint as a separate ALTER TABLE after
        # both tables exist, so Base.metadata.create_all/drop_all (used by the
        # test conftest) can topologically order the tables instead of raising
        # CircularDependencyError. Prod DDL comes from alembic, so this only
        # affects create_all/drop_all ordering, not the live schema.
        ForeignKey(
            "user_orders.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_admin_users_current_order_id",
        ),
        nullable=True,
    )
    current_order = relationship("UserOrder", foreign_keys=[current_order_id])
    language: Mapped[str] = mapped_column(
        String(5), server_default="fa", nullable=False
    )
    referral_code: Mapped[Optional[str]] = mapped_column(String(50))
    referred_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    wallet_credit_tomans: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), server_default="0", nullable=False
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    # Relationships
    admin = relationship("Admin", back_populates="users")
    credentials = relationship(
        "UserCredentialV2", back_populates="user", cascade="all, delete-orphan"
    )
    regions = relationship(
        "UserRegion",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="UserRegion.id",
    )
    # Back-compat scalar: the single primary region (or None). Read-only view.
    region = relationship(
        "UserRegion",
        primaryjoin="and_(AdminUser.id == UserRegion.user_id, UserRegion.is_primary == True)",
        uselist=False,
        viewonly=True,
    )
    traffic_logs = relationship("TrafficLog", back_populates="user")
    referred_by = relationship("AdminUser", remote_side=[id], backref="referred_users")

    __table_args__ = (
        UniqueConstraint("admin_id", "username", name="uq_admin_user"),
        UniqueConstraint("admin_id", "telegram_id", name="uq_admin_users_admin_tg"),
        UniqueConstraint(
            "admin_id", "referral_code", name="uq_admin_users_referral_code"
        ),
        # Usernames are GLOBAL and case-insensitive among non-deleted users:
        # VPN containers key Xray clients by username across all resellers and
        # one collision crash-loops every VLESS/Trojan container.
        Index(
            "uq_admin_users_username_ci",
            func.lower(username),
            unique=True,
            postgresql_where=text("status IS DISTINCT FROM 'deleted'"),
        ),
    )

    def __repr__(self):
        return f"<AdminUser(id={self.id}, username={self.username}, admin_id={self.admin_id}, status={self.status})>"
