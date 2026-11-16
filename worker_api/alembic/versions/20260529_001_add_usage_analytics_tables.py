"""Add usage analytics tables: protocol_daily_summaries and bandwidth_time_series

Revision ID: 20260529_001
Revises: 20260302_001
Create Date: 2026-05-29
"""
import sqlalchemy as sa
from alembic import op

revision = "20260529_001"
down_revision = "20260302_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "protocol_daily_summaries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("protocol_id", sa.Integer(), nullable=False),
        sa.Column("summary_date", sa.Date(), nullable=False),
        sa.Column("total_bytes_uploaded", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total_bytes_downloaded", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total_connections", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unique_users", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("protocol_id", "summary_date", name="uq_protocol_date"),
    )
    op.create_index("ix_protocol_daily_summaries_id", "protocol_daily_summaries", ["id"], unique=False)
    op.create_index("ix_protocol_daily_summaries_protocol_id", "protocol_daily_summaries", ["protocol_id"], unique=False)
    op.create_index("ix_protocol_daily_summaries_summary_date", "protocol_daily_summaries", ["summary_date"], unique=False)

    op.create_table(
        "bandwidth_time_series",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("period_type", sa.String(10), nullable=False),
        sa.Column("period_start", sa.TIMESTAMP(), nullable=False),
        sa.Column("total_bytes_uploaded", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total_bytes_downloaded", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bandwidth_time_series_id", "bandwidth_time_series", ["id"], unique=False)
    op.create_index("ix_bandwidth_time_series_period_type", "bandwidth_time_series", ["period_type"], unique=False)
    op.create_index("ix_bandwidth_time_series_period_start", "bandwidth_time_series", ["period_start"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_bandwidth_time_series_period_start", table_name="bandwidth_time_series")
    op.drop_index("ix_bandwidth_time_series_period_type", table_name="bandwidth_time_series")
    op.drop_index("ix_bandwidth_time_series_id", table_name="bandwidth_time_series")
    op.drop_table("bandwidth_time_series")

    op.drop_index("ix_protocol_daily_summaries_summary_date", table_name="protocol_daily_summaries")
    op.drop_index("ix_protocol_daily_summaries_protocol_id", table_name="protocol_daily_summaries")
    op.drop_index("ix_protocol_daily_summaries_id", table_name="protocol_daily_summaries")
    op.drop_table("protocol_daily_summaries")
