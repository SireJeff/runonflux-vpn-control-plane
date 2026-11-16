"""TrafficCounter — backend-authoritative last-seen cumulative counter per
(user, protocol, instance, boot_id). See spec 2026-07-27-traffic-authoritative-accounting.

boot_id is part of the key because one Flux app (one FLUXVPN_INSTANCE_ID) runs
MANY replicas that all report the same instance_id; each replica generates a
unique boot_id at start, so keying by boot_id gives each replica-boot its own
row (no cross-replica collision / thrashing)."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class TrafficCounter(Base):
    __tablename__ = "traffic_counters"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "protocol",
            "instance_id",
            "boot_id",
            name="uq_traffic_counter",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("admin_users.id"), nullable=False, index=True
    )
    protocol: Mapped[str] = mapped_column(String(20), nullable=False)
    instance_id: Mapped[str] = mapped_column(String(64), nullable=False)
    last_cumulative_in: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    last_cumulative_out: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    boot_id: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default="", default=""
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    def __repr__(self):
        return "<TrafficCounter(user=%s, proto=%s, inst=%s)>" % (
            self.user_id,
            self.protocol,
            self.instance_id,
        )
