"""
Operational observability models
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import TIMESTAMP, BigInteger, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class ApiRequestMetricHourly(Base):
    """Hourly aggregate API request metrics for admin health dashboards."""

    __tablename__ = "api_request_metrics_hourly"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    hour_start: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, index=True)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_response_time_ms: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    __table_args__ = (
        UniqueConstraint("hour_start", name="uq_api_request_metrics_hourly_hour_start"),
    )

    def __repr__(self):
        return (
            f"<ApiRequestMetricHourly(hour_start={self.hour_start}, "
            f"request_count={self.request_count})>"
        )
