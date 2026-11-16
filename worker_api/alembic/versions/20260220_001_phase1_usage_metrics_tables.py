"""Add usage metrics hourly and daily tables

Revision ID: 20260220_001
Revises: d8e8d7b42e47
Create Date: 2026-02-20 00:01:00.000000+00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260220_001"
down_revision: Union[str, None] = "d8e8d7b42e47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "usage_metrics_hourly",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("protocol_id", sa.Integer(), nullable=False),
        sa.Column("hour_start", sa.TIMESTAMP(), nullable=False),
        sa.Column("bytes_uploaded", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("bytes_downloaded", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("connection_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.TIMESTAMP(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["protocol_id"], ["protocols.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "protocol_id", "hour_start", name="uq_usage_hourly_user_protocol_hour"),
    )
    op.create_index("ix_usage_metrics_hourly_id", "usage_metrics_hourly", ["id"], unique=False)
    op.create_index("idx_usage_hourly_hour_start", "usage_metrics_hourly", ["hour_start"], unique=False)

    op.create_table(
        "usage_metrics_daily",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("protocol_id", sa.Integer(), nullable=False),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("bytes_uploaded", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("bytes_downloaded", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("connection_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.TIMESTAMP(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["protocol_id"], ["protocols.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "protocol_id", "usage_date", name="uq_usage_daily_user_protocol_date"),
    )
    op.create_index("ix_usage_metrics_daily_id", "usage_metrics_daily", ["id"], unique=False)
    op.create_index("idx_usage_daily_usage_date", "usage_metrics_daily", ["usage_date"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_usage_daily_usage_date", table_name="usage_metrics_daily")
    op.drop_index("ix_usage_metrics_daily_id", table_name="usage_metrics_daily")
    op.drop_table("usage_metrics_daily")

    op.drop_index("idx_usage_hourly_hour_start", table_name="usage_metrics_hourly")
    op.drop_index("ix_usage_metrics_hourly_id", table_name="usage_metrics_hourly")
    op.drop_table("usage_metrics_hourly")
