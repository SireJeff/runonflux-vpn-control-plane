"""phase 5.1: tld_usage_daily table (analytics time-series)

Revision ID: 20260626_001
Revises: 20260625_002
Create Date: 2026-06-26

Idempotent: create_table + both indexes are guarded with an
information_schema check (migrations re-run on container rebuild; an
unguarded re-run crash-loops with DuplicateTable).
"""
from alembic import op
import sqlalchemy as sa

revision = "20260626_001"
down_revision = "20260625_002"
branch_labels = None
depends_on = None


def _table_exists(conn, table):
    return conn.execute(
        sa.text("SELECT 1 FROM information_schema.tables WHERE table_name = :t"),
        {"t": table},
    ).fetchone() is not None


def upgrade():
    conn = op.get_bind()
    if not _table_exists(conn, "tld_usage_daily"):
        op.create_table(
            "tld_usage_daily",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("snapshot_date", sa.Date(), nullable=False),
            sa.Column("purpose", sa.String(length=20), nullable=False),
            sa.Column(
                "tld_id",
                sa.Integer(),
                sa.ForeignKey("registered_tlds.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("domain_snapshot", sa.String(length=255), nullable=False),
            sa.Column("active_user_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column(
                "created_at", sa.TIMESTAMP(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.UniqueConstraint(
                "snapshot_date", "purpose", "tld_id",
                name="uq_tld_usage_daily_date_purpose_tld",
            ),
        )
        op.create_index("ix_tld_usage_daily_snapshot_date", "tld_usage_daily", ["snapshot_date"])
        op.create_index("ix_tld_usage_daily_tld_id", "tld_usage_daily", ["tld_id"])


def downgrade():
    conn = op.get_bind()
    if _table_exists(conn, "tld_usage_daily"):
        op.drop_index("ix_tld_usage_daily_tld_id", table_name="tld_usage_daily")
        op.drop_index("ix_tld_usage_daily_snapshot_date", table_name="tld_usage_daily")
        op.drop_table("tld_usage_daily")
