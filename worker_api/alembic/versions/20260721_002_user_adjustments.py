"""User adjustments audit table

Revision ID: 20260721_002
Revises: 20260721_001
Create Date: 2026-07-21

Idempotent: guarded table create (re-runs on container rebuild).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260721_002"
down_revision = "20260721_001"
branch_labels = None
depends_on = None


def _table_exists(conn, table):
    return conn.execute(
        sa.text("SELECT 1 FROM information_schema.tables WHERE table_name = :t"),
        {"t": table},
    ).fetchone() is not None


def upgrade():
    conn = op.get_bind()
    if _table_exists(conn, "user_adjustments"):
        return
    op.create_table(
        "user_adjustments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("admin_id", sa.Integer(), sa.ForeignKey("admins.id"), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("details", JSONB(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_user_adjustments_user_id", "user_adjustments", ["user_id"])
    op.create_index("ix_user_adjustments_created_at", "user_adjustments", ["created_at"])


def downgrade():
    conn = op.get_bind()
    if _table_exists(conn, "user_adjustments"):
        op.drop_table("user_adjustments")
