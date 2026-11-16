"""Create admin_bots, admin_packages, user_orders, admin_referral_configs,
admin_referral_earnings tables; alter admin_users and admins.

Revision ID: 20260613_001
Revises: 20260612_002
Create Date: 2026-06-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "20260613_001"
down_revision = "20260612_002"
branch_labels = None
depends_on = None


def upgrade():
    # ── New table: admin_bots ──────────────────────────────────────────
    op.create_table(
        "admin_bots",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("admin_id", sa.Integer,
                  sa.ForeignKey("admins.id", ondelete="CASCADE"), nullable=False),
        sa.Column("bot_token_enc", sa.LargeBinary, nullable=False),
        sa.Column("bot_username", sa.String(100), nullable=False),
        sa.Column("bot_user_id", sa.BigInteger, nullable=False),
        sa.Column("bot_display_name", sa.String(100)),
        sa.Column("welcome_message_fa", sa.Text),
        sa.Column("welcome_message_en", sa.Text),
        sa.Column("card_number", sa.String(20)),
        sa.Column("card_holder_name", sa.String(100)),
        sa.Column("support_phone", sa.String(20)),
        sa.Column("support_telegram", sa.String(50)),
        sa.Column("default_macro_region", sa.String(5), nullable=False, server_default="eu"),
        sa.Column("webhook_secret", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("webhook_registered_at", sa.TIMESTAMP),
        sa.Column("last_update_at", sa.TIMESTAMP),
        sa.Column("created_at", sa.TIMESTAMP, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("admin_id", name="uq_admin_bots_admin_id"),
        sa.UniqueConstraint("bot_user_id", name="uq_admin_bots_bot_user_id"),
    )
    op.create_index("ix_admin_bots_admin_id", "admin_bots", ["admin_id"])

    # ── New table: admin_packages ──────────────────────────────────────
    op.create_table(
        "admin_packages",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("admin_id", sa.Integer,
                  sa.ForeignKey("admins.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("traffic_limit_gb", sa.Numeric(10, 2), nullable=False),
        sa.Column("duration_days", sa.Integer, nullable=False),
        sa.Column("price_tomans", sa.Numeric(12, 2), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("display_order", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.TIMESTAMP, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("admin_id", "name", name="uq_admin_packages_admin_name"),
    )
    op.create_index("ix_admin_packages_admin_id", "admin_packages", ["admin_id"])

    # ── New table: user_orders ─────────────────────────────────────────
    op.create_table(
        "user_orders",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer,
                  sa.ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("admin_id", sa.Integer,
                  sa.ForeignKey("admins.id"), nullable=False),
        sa.Column("package_id", sa.Integer,
                  sa.ForeignKey("admin_packages.id", ondelete="SET NULL")),
        sa.Column("package_snapshot", JSONB, nullable=False),
        sa.Column("macro_region", sa.String(5), nullable=False),
        sa.Column("amount_tomans", sa.Numeric(12, 2), nullable=False),
        sa.Column("wallet_credit_applied_tomans", sa.Numeric(12, 2),
                  nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("receipt_file_id", sa.String(255)),
        sa.Column("receipt_file_unique_id", sa.String(255)),
        sa.Column("receipt_local_path", sa.String(500)),
        sa.Column("reviewer_admin_id", sa.Integer,
                  sa.ForeignKey("admins.id")),
        sa.Column("reviewed_at", sa.TIMESTAMP),
        sa.Column("admin_notes", sa.Text),
        sa.Column("rejection_reason", sa.Text),
        sa.Column("created_at", sa.TIMESTAMP, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("expires_at", sa.TIMESTAMP),
    )
    op.create_index("idx_user_orders_admin_status", "user_orders", ["admin_id", "status"])
    op.create_index("idx_user_orders_user", "user_orders", ["user_id", "created_at"])

    # ── New table: admin_referral_configs ─────────────────────────────
    op.create_table(
        "admin_referral_configs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("admin_id", sa.Integer,
                  sa.ForeignKey("admins.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("is_enabled", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("reward_percentage", sa.Numeric(5, 2),
                  nullable=False, server_default="10.00"),
        sa.Column("created_at", sa.TIMESTAMP, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.TIMESTAMP, server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    # ── New table: admin_referral_earnings ────────────────────────────
    op.create_table(
        "admin_referral_earnings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("admin_id", sa.Integer,
                  sa.ForeignKey("admins.id", ondelete="CASCADE"), nullable=False),
        sa.Column("referrer_user_id", sa.Integer,
                  sa.ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("referred_user_id", sa.Integer,
                  sa.ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_id", sa.Integer,
                  sa.ForeignKey("user_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("commission_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("amount_tomans", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("idx_referral_earnings_referrer", "admin_referral_earnings", ["referrer_user_id"])
    op.create_index("idx_referral_earnings_admin", "admin_referral_earnings", ["admin_id"])

    # ── Alter: admin_users (telegram linkage + referral + wallet) ─────
    op.add_column("admin_users", sa.Column("telegram_id", sa.BigInteger))
    op.add_column("admin_users", sa.Column("telegram_chat_id", sa.BigInteger))
    op.add_column("admin_users", sa.Column("registered_bot_id", sa.Integer,
                  sa.ForeignKey("admin_bots.id", ondelete="SET NULL")))
    op.add_column("admin_users", sa.Column("current_order_id", sa.Integer,
                  sa.ForeignKey("user_orders.id", ondelete="SET NULL")))
    op.add_column("admin_users", sa.Column("language", sa.String(5),
                  server_default="fa", nullable=False))
    op.add_column("admin_users", sa.Column("referral_code", sa.String(50)))
    op.add_column("admin_users", sa.Column("referred_by_user_id", sa.Integer,
                  sa.ForeignKey("admin_users.id", ondelete="SET NULL")))
    op.add_column("admin_users", sa.Column("wallet_credit_tomans", sa.Numeric(12, 2),
                  server_default="0", nullable=False))
    op.create_unique_constraint("uq_admin_users_admin_tg", "admin_users",
                                ["admin_id", "telegram_id"])
    op.create_unique_constraint("uq_admin_users_referral_code", "admin_users",
                                ["admin_id", "referral_code"])
    op.create_index("ix_admin_users_referrer", "admin_users", ["referred_by_user_id"])

    # ── Alter: admins (default_macro_region) ──────────────────────────
    op.add_column("admins", sa.Column("default_macro_region", sa.String(5),
                                      server_default="eu"))


def downgrade():
    op.drop_column("admins", "default_macro_region")

    op.drop_index("ix_admin_users_referrer", table_name="admin_users")
    op.drop_constraint("uq_admin_users_referral_code", "admin_users", type_="unique")
    op.drop_constraint("uq_admin_users_admin_tg", "admin_users", type_="unique")
    op.drop_column("admin_users", "wallet_credit_tomans")
    op.drop_column("admin_users", "referred_by_user_id")
    op.drop_column("admin_users", "referral_code")
    op.drop_column("admin_users", "language")
    op.drop_column("admin_users", "current_order_id")
    op.drop_column("admin_users", "registered_bot_id")
    op.drop_column("admin_users", "telegram_chat_id")
    op.drop_column("admin_users", "telegram_id")

    op.drop_index("idx_referral_earnings_admin", table_name="admin_referral_earnings")
    op.drop_index("idx_referral_earnings_referrer", table_name="admin_referral_earnings")
    op.drop_table("admin_referral_earnings")
    op.drop_table("admin_referral_configs")

    op.drop_index("idx_user_orders_user", table_name="user_orders")
    op.drop_index("idx_user_orders_admin_status", table_name="user_orders")
    op.drop_table("user_orders")

    op.drop_index("ix_admin_packages_admin_id", table_name="admin_packages")
    op.drop_table("admin_packages")

    op.drop_index("ix_admin_bots_admin_id", table_name="admin_bots")
    op.drop_table("admin_bots")
