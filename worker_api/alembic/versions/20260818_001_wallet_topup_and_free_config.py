"""Wallet top-up + free public config.

Adds user_orders.kind, admin_bots.min_topup_tomans, relaxes
user_orders.macro_region/package_snapshot to nullable, and creates
admin_user_wallet_txns + admin_free_configs.

Revision ID: 20260818_001
Revises: 20260801_001
Create Date: 2026-08-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260818_001"
down_revision = "20260801_001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "user_orders",
        sa.Column("kind", sa.String(20), nullable=False, server_default="subscription"),
    )
    op.alter_column("user_orders", "macro_region", existing_type=sa.String(5), nullable=True)
    op.alter_column("user_orders", "package_snapshot", existing_type=JSONB, nullable=True)

    op.add_column(
        "admin_bots", sa.Column("min_topup_tomans", sa.Numeric(12, 2), nullable=True)
    )

    op.create_table(
        "admin_user_wallet_txns",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer,
                  sa.ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("admin_id", sa.Integer,
                  sa.ForeignKey("admins.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount_tomans", sa.Numeric(12, 2), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("order_id", sa.Integer,
                  sa.ForeignKey("user_orders.id", ondelete="SET NULL")),
        sa.Column("balance_after", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_admin_user_wallet_txns_user_id", "admin_user_wallet_txns", ["user_id"])
    op.create_index("ix_admin_user_wallet_txns_admin_id", "admin_user_wallet_txns", ["admin_id"])

    op.create_table(
        "admin_free_configs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("admin_id", sa.Integer,
                  sa.ForeignKey("admins.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_enabled", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("kind", sa.String(20), nullable=False, server_default="shared"),
        sa.Column("label", sa.String(100)),
        sa.Column("region", sa.String(5)),
        sa.Column("traffic_limit_gb", sa.Numeric(10, 2)),
        sa.Column("duration_days", sa.Integer),
        sa.Column("shared_credential_ref", sa.String(64)),
        sa.Column("created_at", sa.TIMESTAMP, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.TIMESTAMP, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("admin_id", name="uq_admin_free_configs_admin_id"),
    )


def downgrade():
    op.drop_table("admin_free_configs")
    op.drop_index("ix_admin_user_wallet_txns_admin_id", table_name="admin_user_wallet_txns")
    op.drop_index("ix_admin_user_wallet_txns_user_id", table_name="admin_user_wallet_txns")
    op.drop_table("admin_user_wallet_txns")
    op.drop_column("admin_bots", "min_topup_tomans")
    # topup orders are destroyed on downgrade: the `kind` discriminator that
    # identifies them is being removed, and they carry NULL package_snapshot/
    # macro_region which the restored NOT NULL constraints (pre-migration state,
    # see 20260613_001) would reject.
    op.execute("DELETE FROM user_orders WHERE kind = 'topup'")
    op.drop_column("user_orders", "kind")
    op.alter_column("user_orders", "package_snapshot", existing_type=JSONB, nullable=False)
    op.alter_column("user_orders", "macro_region", existing_type=sa.String(5), nullable=False)
