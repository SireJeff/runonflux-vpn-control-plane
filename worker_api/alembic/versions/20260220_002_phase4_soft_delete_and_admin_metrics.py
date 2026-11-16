"""Add user soft-delete lifecycle fields and API request metrics table

Revision ID: 20260220_002
Revises: 20260220_001
Create Date: 2026-02-20 04:00:00.000000+00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260220_002"
down_revision: Union[str, None] = "20260220_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("users", sa.Column("deleted_at", sa.TIMESTAMP(), nullable=True))
    op.add_column(
        "users", sa.Column("deletion_scheduled_at", sa.TIMESTAMP(), nullable=True)
    )
    op.create_index("ix_users_is_deleted", "users", ["is_deleted"], unique=False)
    op.create_index("ix_users_deleted_at", "users", ["deleted_at"], unique=False)
    op.create_index(
        "ix_users_deletion_scheduled_at",
        "users",
        ["deletion_scheduled_at"],
        unique=False,
    )
    op.alter_column("users", "is_deleted", server_default=None)

    op.create_table(
        "api_request_metrics_hourly",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("hour_start", sa.TIMESTAMP(), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "total_response_time_ms",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            nullable=True,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(),
            nullable=True,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "hour_start", name="uq_api_request_metrics_hourly_hour_start"
        ),
    )
    op.create_index(
        "ix_api_request_metrics_hourly_id",
        "api_request_metrics_hourly",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_api_request_metrics_hourly_hour_start",
        "api_request_metrics_hourly",
        ["hour_start"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_api_request_metrics_hourly_hour_start",
        table_name="api_request_metrics_hourly",
    )
    op.drop_index("ix_api_request_metrics_hourly_id", table_name="api_request_metrics_hourly")
    op.drop_table("api_request_metrics_hourly")

    op.drop_index("ix_users_deletion_scheduled_at", table_name="users")
    op.drop_index("ix_users_deleted_at", table_name="users")
    op.drop_index("ix_users_is_deleted", table_name="users")
    op.drop_column("users", "deletion_scheduled_at")
    op.drop_column("users", "deleted_at")
    op.drop_column("users", "is_deleted")
