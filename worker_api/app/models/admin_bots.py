"""
AdminBot model — one Telegram bot per reseller admin.
Stores AES-GCM-encrypted bot token (LargeBinary).
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Boolean,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class AdminBot(Base):
    """A Telegram bot configured by a reseller to serve their end-users."""

    __tablename__ = "admin_bots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    admin_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("admins.id", ondelete="CASCADE"),
        nullable=False,
    )
    bot_token_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    bot_username: Mapped[str] = mapped_column(String(100), nullable=False)
    bot_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    bot_display_name: Mapped[Optional[str]] = mapped_column(String(100))
    welcome_message_fa: Mapped[Optional[str]] = mapped_column(Text)
    welcome_message_en: Mapped[Optional[str]] = mapped_column(Text)
    card_number: Mapped[Optional[str]] = mapped_column(String(20))
    card_holder_name: Mapped[Optional[str]] = mapped_column(String(100))
    # Per-reseller crypto receiving address for their end-users' plan payments.
    crypto_address: Mapped[Optional[str]] = mapped_column(String(255))
    crypto_network: Mapped[Optional[str]] = mapped_column(String(50))
    crypto_memo: Mapped[Optional[str]] = mapped_column(String(255))
    min_topup_tomans: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    support_phone: Mapped[Optional[str]] = mapped_column(String(20))
    support_telegram: Mapped[Optional[str]] = mapped_column(String(50))
    default_macro_region: Mapped[str] = mapped_column(
        String(5), nullable=False, server_default="eu"
    )
    webhook_secret: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    webhook_registered_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    last_update_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )

    # Relationships
    admin = relationship("Admin", back_populates="bot")

    __table_args__ = (
        UniqueConstraint("admin_id", name="uq_admin_bots_admin_id"),
        UniqueConstraint("bot_user_id", name="uq_admin_bots_bot_user_id"),
    )

    def __repr__(self):
        return f"<AdminBot(id={self.id}, admin_id={self.admin_id}, bot_username={self.bot_username})>"
