"""
Flux DNS Manager (FDM) models
Deployment configurations, domain records, and sync history
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import TIMESTAMP, Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class FdmDeployment(Base):
    """Flux DNS Manager deployment configuration - one per Flux app per protocol"""

    __tablename__ = "fdm_deployments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    flux_app_name: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )  # e.g., 'fluxvpn-nl-01'
    region: Mapped[str] = mapped_column(
        String(2), nullable=False
    )  # ISO 3166-1 alpha-2 (e.g., 'NL', 'US')
    domain_pool_size: Mapped[Optional[int]] = mapped_column(
        Integer, default=25
    )  # Number of domains to manage
    base_domain: Mapped[Optional[str]] = mapped_column(
        String(255), default="operator3.example.invalid"
    )  # Base for subdomains
    protocol_name: Mapped[Optional[str]] = mapped_column(
        String(50), default=None
    )  # e.g., 'ssh', 'shadowsocks', 'vless'
    health_check_port: Mapped[Optional[int]] = mapped_column(
        Integer, default=443
    )  # External port to health-check
    socks5_port: Mapped[Optional[int]] = mapped_column(
        Integer, default=None
    )  # External SOCKS5 port (for Telegram proxy)
    is_active: Mapped[Optional[bool]] = mapped_column(Boolean, default=True, index=True)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP
    )  # Last successful sync completion
    last_sync_status: Mapped[Optional[str]] = mapped_column(
        String(50)
    )  # success, failed, partial, never
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )  # Auto-deactivation counter
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    # Relationships
    domains = relationship(
        "FdmDomain",
        back_populates="deployment",
        cascade="all, delete-orphan",
    )
    sync_logs = relationship(
        "FdmSyncLog",
        back_populates="deployment",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("flux_app_name", "region", name="uq_deployment_app_region"),
    )

    def __repr__(self):
        return f"<FdmDeployment(id={self.id}, flux_app_name={self.flux_app_name}, protocol={self.protocol_name}, region={self.region})>"


class FdmDomain(Base):
    """Individual domain records managed by FDM"""

    __tablename__ = "fdm_domains"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    deployment_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("fdm_deployments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tld_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("registered_tlds.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )  # Phase 4: which registered fdm TLD this subdomain belongs to.
    # Nullable during the 4a->4b transition (legacy rows + sync rows
    # created before 4b sets it). Read-side filter treats NULL as
    # "belongs to the admin's effective fdm TLD" under single-active.
    domain_name: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True
    )  # e.g., 'ch-ssh-01-a1.operator3.example.invalid'
    domain_id: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # Short ID e.g., 'abc01'
    current_ip: Mapped[Optional[str]] = mapped_column(
        INET
    )  # Current IP address pointed to by domain
    current_instance_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("protocol_instances.id", ondelete="SET NULL")
    )  # Linked protocol instance
    dns_record_id: Mapped[Optional[str]] = mapped_column(
        String(255)
    )  # DNS provider API record ID (Cloudflare, Arvan, etc.)
    health_status: Mapped[Optional[str]] = mapped_column(
        String(50), default="unknown"
    )  # healthy, unhealthy, unknown
    last_health_check: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    assigned_users_count: Mapped[Optional[int]] = mapped_column(
        Integer, default=0
    )  # Users using this domain
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    # Relationships
    deployment = relationship("FdmDeployment", back_populates="domains")
    instance = relationship("ProtocolInstance", foreign_keys=[current_instance_id])

    def __repr__(self):
        return f"<FdmDomain(id={self.id}, domain_name={self.domain_name}, status={self.health_status})>"


class FdmSyncLog(Base):
    """Flux DNS Manager sync history and status tracking"""

    __tablename__ = "fdm_sync_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    deployment_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("fdm_deployments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sync_started_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False)
    sync_completed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP)
    instances_found: Mapped[Optional[int]] = mapped_column(
        Integer, default=0
    )  # Protocol instances discovered
    instances_healthy: Mapped[Optional[int]] = mapped_column(
        Integer, default=0
    )  # Instances passing health checks
    domains_updated: Mapped[Optional[int]] = mapped_column(
        Integer, default=0
    )  # DNS records updated
    errors: Mapped[Optional[Any]] = mapped_column(JSONB)  # Error details as JSON array
    status: Mapped[Optional[str]] = mapped_column(
        String(50), default="running"
    )  # running, completed, failed
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )

    # Relationships
    deployment = relationship("FdmDeployment", back_populates="sync_logs")

    def __repr__(self):
        return f"<FdmSyncLog(id={self.id}, deployment_id={self.deployment_id}, status={self.status})>"
