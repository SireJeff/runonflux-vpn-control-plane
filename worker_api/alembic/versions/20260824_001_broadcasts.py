"""Reseller broadcasts: broadcasts table + admins.broadcasts_enabled.

Revision ID: 20260824_001
Revises: 20260819_001
Create Date: 2026-08-24
"""
from alembic import op
import sqlalchemy as sa

revision = "20260824_001"
down_revision = "20260819_001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "broadcasts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "admin_id",
            sa.Integer,
            sa.ForeignKey("admins.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_by", sa.Integer, nullable=True),
        sa.Column("segment", sa.String(20), nullable=False),
        sa.Column("message_text", sa.Text, nullable=False),
        sa.Column("button_label", sa.String(64), nullable=True),
        sa.Column("button_url", sa.String(2048), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("audience_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("sent_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("blocked_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("started_at", sa.TIMESTAMP, nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP, nullable=True),
    )
    op.create_index("ix_broadcasts_admin_id", "broadcasts", ["admin_id"])
    op.add_column(
        "admins",
        sa.Column(
            "broadcasts_enabled",
            sa.Boolean,
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade():
    op.drop_column("admins", "broadcasts_enabled")
    op.drop_index("ix_broadcasts_admin_id", table_name="broadcasts")
    op.drop_table("broadcasts")
