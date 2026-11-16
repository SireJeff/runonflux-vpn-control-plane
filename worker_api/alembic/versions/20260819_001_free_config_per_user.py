"""Per-user daily-quota free config: columns + channels/global/enrollments tables.

Revision ID: 20260819_001
Revises: 20260818_002
Create Date: 2026-08-19
"""
from alembic import op
import sqlalchemy as sa

revision = "20260819_001"
down_revision = "20260818_002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("admin_free_configs", sa.Column("daily_limit_mb", sa.Integer, nullable=True))
    op.add_column("admin_free_configs", sa.Column("max_free_users", sa.Integer, nullable=True))

    op.create_table(
        "free_config_channels",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("admin_id", sa.Integer, sa.ForeignKey("admins.id", ondelete="CASCADE"), nullable=True),
        sa.Column("chat_id", sa.BigInteger, nullable=True),
        sa.Column("username", sa.String(100), nullable=True),
        sa.Column("title", sa.String(200), nullable=False, server_default=""),
        sa.Column("invite_url", sa.String(300), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.TIMESTAMP, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_free_config_channels_admin_id", "free_config_channels", ["admin_id"])

    op.create_table(
        "free_config_global",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("is_enabled", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("default_daily_limit_mb", sa.Integer, nullable=False, server_default="200"),
        sa.Column("default_max_free_users", sa.Integer, nullable=True),
        sa.Column("verification_bot_token_enc", sa.LargeBinary, nullable=True),
        sa.Column("verification_bot_username", sa.String(100), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP, server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "free_config_enrollments",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("admin_id", sa.Integer, sa.ForeignKey("admins.id", ondelete="CASCADE"), nullable=False),
        sa.Column("claimed_at", sa.TIMESTAMP, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("last_membership_check_at", sa.TIMESTAMP, nullable=True),
        sa.Column("membership_ok", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("suspended_reason", sa.String(20), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("user_id", name="uq_free_config_enrollments_user_id"),
    )
    op.create_index("ix_free_config_enrollments_admin_id", "free_config_enrollments", ["admin_id"])


def downgrade():
    op.drop_table("free_config_enrollments")
    op.drop_table("free_config_global")
    op.drop_index("ix_free_config_channels_admin_id", table_name="free_config_channels")
    op.drop_table("free_config_channels")
    op.drop_column("admin_free_configs", "max_free_users")
    op.drop_column("admin_free_configs", "daily_limit_mb")
