"""Broadcast model — one row per reseller broadcast, with aggregate counts."""

from datetime import datetime
from typing import Optional

from sqlalchemy import TIMESTAMP, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class Broadcast(Base):
    """A one-off message a reseller sends to a segment of their end-users."""

    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    admin_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("admins.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    segment: Mapped[str] = mapped_column(String(20), nullable=False)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    button_label: Mapped[Optional[str]] = mapped_column(String(64))
    button_url: Mapped[Optional[str]] = mapped_column(String(2048))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="queued")
    audience_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    sent_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    blocked_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
