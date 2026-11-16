"""Add subscription_token and expires_at to admin_users

Revision ID: 20260611_001
Revises: 20260610_001
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "20260611_001"
down_revision = "20260610_001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "admin_users",
        sa.Column("subscription_token", sa.String(64), nullable=True),
    )
    op.add_column(
        "admin_users",
        sa.Column("expires_at", sa.TIMESTAMP, nullable=True),
    )
    op.create_index(
        "ix_admin_users_subscription_token",
        "admin_users",
        ["subscription_token"],
        unique=True,
    )

    # Generate tokens for all existing users
    import secrets
    conn = op.get_bind()
    users = conn.execute(text("SELECT id FROM admin_users")).fetchall()
    for (user_id,) in users:
        token = secrets.token_hex(16)
        conn.execute(
            text("UPDATE admin_users SET subscription_token = :token WHERE id = :id"),
            {"token": token, "id": user_id},
        )


def downgrade():
    op.drop_index("ix_admin_users_subscription_token")
    op.drop_column("admin_users", "expires_at")
    op.drop_column("admin_users", "subscription_token")
