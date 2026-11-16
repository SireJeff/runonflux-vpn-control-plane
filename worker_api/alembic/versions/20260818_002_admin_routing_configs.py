"""Per-reseller routing rules (ban list + website allow/direct).

Creates admin_routing_configs (one row per admin).

Revision ID: 20260818_002
Revises: 20260818_001
Create Date: 2026-08-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260818_002"
down_revision = "20260818_001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "admin_routing_configs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("admin_id", sa.Integer,
                  sa.ForeignKey("admins.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_enabled", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("rules", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.TIMESTAMP, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.TIMESTAMP, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("admin_id", name="uq_admin_routing_configs_admin_id"),
    )


def downgrade():
    op.drop_table("admin_routing_configs")
