"""Add notification_enabled column to users table

Revision ID: 20260529_002
Revises: 20260529_001
Create Date: 2026-05-29
"""
import sqlalchemy as sa
from alembic import op

revision = "20260529_002"
down_revision = "20260529_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "notification_enabled",
            sa.Boolean(),
            nullable=True,
            server_default="true",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "notification_enabled")
