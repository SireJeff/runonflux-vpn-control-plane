"""
Flux App Registration model
Super admin registered Flux applications with per-protocol port mappings
"""
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import TIMESTAMP, Boolean, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class FluxAppRegistration(Base):
    """Registered Flux application managed by super admin."""

    __tablename__ = "flux_app_registrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    app_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    protocol_ports: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[Optional[bool]] = mapped_column(Boolean, default=True, index=True)
    registered_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_discovery_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    last_discovery_ips: Mapped[Optional[Any]] = mapped_column(JSONB)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    # FDM Hardening Phase 3.1: Flux appspecifications snapshot for spec-aware
    # domain-pool sizing + expected-vs-actual gap detection (Goal 1). Populated
    # each cycle by FluxSpecFetcher (Phase 3.2/3.3).
    expected_instances: Mapped[Optional[int]] = mapped_column(
        Integer
    )  # declared instance count
    spec_components: Mapped[Optional[Any]] = mapped_column(
        JSONB
    )  # [{name, ram, cpu, hdd, ports}]
    spec_geolocation: Mapped[Optional[Any]] = mapped_column(JSONB)  # continent pins
    last_spec_fetched_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    last_spec_status: Mapped[Optional[str]] = mapped_column(
        String(50)
    )  # "ok" | "fetch_failed" | "gap"
