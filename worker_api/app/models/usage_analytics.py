"""Usage analytics models for protocol-level and bandwidth time-series aggregates."""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import TIMESTAMP, BigInteger, Date, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class ProtocolDailySummary(Base):
    """Per-protocol daily usage summary for admin dashboard analytics."""

    __tablename__ = "protocol_daily_summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    protocol_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    summary_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    total_bytes_uploaded: Mapped[Optional[int]] = mapped_column(BigInteger, default=0)
    total_bytes_downloaded: Mapped[Optional[int]] = mapped_column(BigInteger, default=0)
    total_connections: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    unique_users: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("protocol_id", "summary_date", name="uq_protocol_date"),
    )


class BandwidthTimeSeries(Base):
    """Time-series bandwidth metrics for admin dashboard charts."""

    __tablename__ = "bandwidth_time_series"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    period_type: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    period_start: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, index=True
    )
    total_bytes_uploaded: Mapped[Optional[int]] = mapped_column(BigInteger, default=0)
    total_bytes_downloaded: Mapped[Optional[int]] = mapped_column(BigInteger, default=0)
    total_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), nullable=False
    )
