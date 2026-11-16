"""Usage metrics models for hourly and daily aggregates."""

from datetime import date, datetime

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Date,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class UsageMetricHourly(Base):
    """Hourly usage aggregates for dashboard and quota checks."""

    __tablename__ = "usage_metrics_hourly"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    protocol_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("protocols.id", ondelete="CASCADE"), nullable=False
    )
    hour_start: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False)
    bytes_uploaded: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    bytes_downloaded: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    connection_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "protocol_id",
            "hour_start",
            name="uq_usage_hourly_user_protocol_hour",
        ),
        Index("idx_usage_hourly_hour_start", "hour_start"),
    )


class UsageMetricDaily(Base):
    """Daily usage aggregates for reporting and admin analytics."""

    __tablename__ = "usage_metrics_daily"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    protocol_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("protocols.id", ondelete="CASCADE"), nullable=False
    )
    usage_date: Mapped[date] = mapped_column(Date, nullable=False)
    bytes_uploaded: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    bytes_downloaded: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    connection_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "protocol_id",
            "usage_date",
            name="uq_usage_daily_user_protocol_date",
        ),
        Index("idx_usage_daily_usage_date", "usage_date"),
    )
