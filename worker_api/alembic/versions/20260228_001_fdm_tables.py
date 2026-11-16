"""Add FDM tables for Flux DNS Manager

Revision ID: 20260228_001
Revises: 20260220_002
Create Date: 2026-02-28 00:01:00.000000+00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260228_001"
down_revision: Union[str, None] = "20260220_002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create fdm_deployments table
    op.create_table(
        "fdm_deployments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("flux_app_name", sa.String(255), nullable=False),
        sa.Column("region", sa.String(2), nullable=False),
        sa.Column("domain_pool_size", sa.Integer(), server_default="25"),
        sa.Column("base_domain", sa.String(255), server_default="operator6.example.invalid"),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("last_sync_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("last_sync_status", sa.String(50), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("flux_app_name"),
    )
    op.create_index("ix_fdm_deployments_id", "fdm_deployments", ["id"], unique=False)
    op.create_index("ix_fdm_deployments_flux_app_name", "fdm_deployments", ["flux_app_name"], unique=True)
    op.create_index("ix_fdm_deployments_is_active", "fdm_deployments", ["is_active"], unique=False)

    # Create fdm_domains table
    op.create_table(
        "fdm_domains",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("deployment_id", sa.Integer(), nullable=False),
        sa.Column("domain_name", sa.String(255), nullable=False),
        sa.Column("domain_id", sa.String(5), nullable=False),
        sa.Column("current_ip", postgresql.INET(), nullable=True),
        sa.Column("current_instance_id", sa.Integer(), nullable=True),
        sa.Column("arvan_record_id", sa.String(255), nullable=True),
        sa.Column("health_status", sa.String(50), server_default="unknown"),
        sa.Column("last_health_check", sa.TIMESTAMP(), nullable=True),
        sa.Column("assigned_users_count", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["deployment_id"], ["fdm_deployments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["current_instance_id"], ["protocol_instances.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("domain_name"),
    )
    op.create_index("ix_fdm_domains_id", "fdm_domains", ["id"], unique=False)
    op.create_index("idx_fdm_domains_deployment", "fdm_domains", ["deployment_id"], unique=False)
    op.create_index("idx_fdm_domains_health", "fdm_domains", ["health_status"], unique=False)
    op.create_index("idx_fdm_domains_load", "fdm_domains", ["assigned_users_count"], unique=False)

    # Create fdm_sync_logs table
    op.create_table(
        "fdm_sync_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("deployment_id", sa.Integer(), nullable=False),
        sa.Column("sync_started_at", sa.TIMESTAMP(), nullable=False),
        sa.Column("sync_completed_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("instances_found", sa.Integer(), server_default="0"),
        sa.Column("instances_healthy", sa.Integer(), server_default="0"),
        sa.Column("domains_updated", sa.Integer(), server_default="0"),
        sa.Column("errors", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(50), server_default="running"),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["deployment_id"], ["fdm_deployments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fdm_sync_logs_id", "fdm_sync_logs", ["id"], unique=False)
    op.create_index("idx_fdm_sync_logs_deployment", "fdm_sync_logs", ["deployment_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_fdm_sync_logs_deployment", table_name="fdm_sync_logs")
    op.drop_index("ix_fdm_sync_logs_id", table_name="fdm_sync_logs")
    op.drop_table("fdm_sync_logs")

    op.drop_index("idx_fdm_domains_load", table_name="fdm_domains")
    op.drop_index("idx_fdm_domains_health", table_name="fdm_domains")
    op.drop_index("idx_fdm_domains_deployment", table_name="fdm_domains")
    op.drop_index("ix_fdm_domains_id", table_name="fdm_domains")
    op.drop_table("fdm_domains")

    op.drop_index("ix_fdm_deployments_is_active", table_name="fdm_deployments")
    op.drop_index("ix_fdm_deployments_flux_app_name", table_name="fdm_deployments")
    op.drop_index("ix_fdm_deployments_id", table_name="fdm_deployments")
    op.drop_table("fdm_deployments")
