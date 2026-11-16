"""Initial migration with refresh tokens

Revision ID: d8e8d7b42e47
Revises:
Create Date: 2026-02-05 12:21:23.886518+00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d8e8d7b42e47"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### Base Schema Creation ###
    op.create_table(
        "protocols",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=50), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("flux_app_name", sa.String(length=255), nullable=True),
        sa.Column("default_port", sa.Integer(), nullable=True),
        sa.Column("exposed_port", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index(op.f("ix_protocols_id"), "protocols", ["id"], unique=False)
    op.create_index(
        op.f("ix_protocols_is_active"), "protocols", ["is_active"], unique=False
    )
    op.create_index(op.f("ix_protocols_name"), "protocols", ["name"], unique=True)

    op.create_table(
        "subscription_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("tier", sa.String(length=50), nullable=False),
        sa.Column("duration_months", sa.Integer(), nullable=False),
        sa.Column("price_usd", sa.DECIMAL(precision=10, scale=2), nullable=False),
        sa.Column("max_protocols", sa.Integer(), nullable=True),
        sa.Column("max_connections", sa.Integer(), nullable=True),
        sa.Column("data_limit_gb", sa.Integer(), nullable=True),
        sa.Column("daily_ip_changes", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_subscription_plans_duration_months"),
        "subscription_plans",
        ["duration_months"],
        unique=False,
    )
    op.create_index(
        op.f("ix_subscription_plans_id"), "subscription_plans", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_subscription_plans_tier"), "subscription_plans", ["tier"], unique=False
    )

    op.create_table(
        "system_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("trial_days", sa.Integer(), nullable=False),
        sa.Column(
            "referral_commission_bronze",
            sa.Numeric(precision=5, scale=2),
            nullable=False,
        ),
        sa.Column(
            "referral_commission_silver",
            sa.Numeric(precision=5, scale=2),
            nullable=False,
        ),
        sa.Column(
            "referral_commission_gold", sa.Numeric(precision=5, scale=2), nullable=False
        ),
        sa.Column(
            "referral_commission_platinum",
            sa.Numeric(precision=5, scale=2),
            nullable=False,
        ),
        sa.Column("maintenance_mode", sa.Boolean(), nullable=False),
        sa.Column("max_ip_changes_per_month", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "translations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("language", sa.String(length=5), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("context", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", "language", name="uq_translation_key_language"),
    )
    op.create_index(op.f("ix_translations_id"), "translations", ["id"], unique=False)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_username", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("flux_wallet_address", sa.String(length=255), nullable=True),
        sa.Column("referral_code", sa.String(length=50), nullable=True),
        sa.Column("referred_by", sa.Integer(), nullable=True),
        sa.Column("referral_tier", sa.String(length=50), nullable=True),
        sa.Column("total_referrals", sa.Integer(), nullable=True),
        sa.Column(
            "referral_earnings_usd", sa.DECIMAL(precision=10, scale=2), nullable=True
        ),
        sa.Column("wallet_balance", sa.DECIMAL(precision=10, scale=2), nullable=True),
        sa.Column("trial_used", sa.Boolean(), nullable=True),
        sa.Column("trial_started_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("trial_expires_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("language", sa.String(length=5), nullable=True),
        sa.Column("is_admin", sa.Boolean(), nullable=True),
        # Excluded soft delete columns: is_deleted, deleted_at, deletion_scheduled_at (Added in 20260220_002)
        sa.Column("refresh_token_jti", sa.String(length=255), nullable=True),
        sa.Column("refresh_token_expires_at", sa.TIMESTAMP(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["referred_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("refresh_token_jti"),
    )
    op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)
    op.create_index(op.f("ix_users_language"), "users", ["language"], unique=False)
    op.create_index(
        op.f("ix_users_referral_code"), "users", ["referral_code"], unique=True
    )
    op.create_index(
        op.f("ix_users_referred_by"), "users", ["referred_by"], unique=False
    )
    op.create_index(
        op.f("ix_users_telegram_user_id"), "users", ["telegram_user_id"], unique=True
    )

    op.create_table(
        "admin_alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("alert_type", sa.String(length=100), nullable=False),
        sa.Column("priority", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("extra_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("sent_telegram", sa.Boolean(), nullable=True),
        sa.Column("sent_email", sa.Boolean(), nullable=True),
        sa.Column("acknowledged", sa.Boolean(), nullable=True),
        sa.Column("acknowledged_by", sa.Integer(), nullable=True),
        sa.Column("acknowledged_at", sa.TIMESTAMP(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["acknowledged_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_admin_alerts_unacknowledged",
        "admin_alerts",
        ["acknowledged"],
        unique=False,
        postgresql_where=sa.text("acknowledged = FALSE"),
    )
    op.create_index(op.f("ix_admin_alerts_id"), "admin_alerts", ["id"], unique=False)

    op.create_table(
        "auth_logs",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_auth_logs_created_at"), "auth_logs", ["created_at"], unique=False
    )
    op.create_index(op.f("ix_auth_logs_id"), "auth_logs", ["id"], unique=False)

    op.create_table(
        "ip_change_quota",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "date", sa.Date(), server_default=sa.text("(CURRENT_DATE)"), nullable=False
        ),
        sa.Column("changes_used", sa.Integer(), nullable=True),
        sa.Column("daily_limit", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "date", name="uq_user_date"),
    )
    op.create_index(
        op.f("ix_ip_change_quota_id"), "ip_change_quota", ["id"], unique=False
    )

    op.create_table(
        "protocol_instances",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("protocol_id", sa.Integer(), nullable=False),
        sa.Column("flux_app_name", sa.String(length=255), nullable=False),
        sa.Column("component_name", sa.String(length=50), nullable=True),
        sa.Column("instance_number", sa.Integer(), nullable=False),
        sa.Column("flux_node_name", sa.String(length=255), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("country_name", sa.String(length=100), nullable=False),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("last_health_check", sa.TIMESTAMP(), nullable=True),
        sa.Column("health_status", sa.String(length=50), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["protocol_id"], ["protocols.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("flux_app_name", "component_name", name="uq_app_component"),
    )
    op.create_index(
        op.f("ix_protocol_instances_country_code"),
        "protocol_instances",
        ["country_code"],
        unique=False,
    )
    op.create_index(
        op.f("ix_protocol_instances_flux_app_name"),
        "protocol_instances",
        ["flux_app_name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_protocol_instances_id"), "protocol_instances", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_protocol_instances_ip_address"),
        "protocol_instances",
        ["ip_address"],
        unique=False,
    )
    op.create_index(
        op.f("ix_protocol_instances_is_active"),
        "protocol_instances",
        ["is_active"],
        unique=False,
    )

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("is_trial", sa.Boolean(), nullable=True),
        sa.Column(
            "started_at",
            sa.TIMESTAMP(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.Column("expires_at", sa.TIMESTAMP(), nullable=False),
        sa.Column("auto_renew", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["subscription_plans.id"],
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_subscriptions_active_user",
        "subscriptions",
        ["user_id", "status"],
        unique=False,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        op.f("ix_subscriptions_expires_at"),
        "subscriptions",
        ["expires_at"],
        unique=False,
    )
    op.create_index(op.f("ix_subscriptions_id"), "subscriptions", ["id"], unique=False)
    op.create_index(
        op.f("ix_subscriptions_is_active"), "subscriptions", ["is_active"], unique=False
    )
    op.create_index(
        op.f("ix_subscriptions_is_trial"), "subscriptions", ["is_trial"], unique=False
    )
    op.create_index(
        op.f("ix_subscriptions_status"), "subscriptions", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_subscriptions_user_id"), "subscriptions", ["user_id"], unique=False
    )

    op.create_table(
        "support_tickets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("ticket_number", sa.String(length=32), nullable=True),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("priority", sa.String(length=50), nullable=True),
        sa.Column("assigned_to", sa.Integer(), nullable=True),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.Column("resolved_at", sa.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(["assigned_to"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_support_tickets_assigned_to"),
        "support_tickets",
        ["assigned_to"],
        unique=False,
    )
    op.create_index(
        op.f("ix_support_tickets_category"),
        "support_tickets",
        ["category"],
        unique=False,
    )
    op.create_index(
        op.f("ix_support_tickets_id"), "support_tickets", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_support_tickets_status"), "support_tickets", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_support_tickets_ticket_number"),
        "support_tickets",
        ["ticket_number"],
        unique=True,
    )
    op.create_index(
        op.f("ix_support_tickets_user_id"), "support_tickets", ["user_id"], unique=False
    )

    op.create_table(
        "trial_activations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_username", sa.String(length=255), nullable=True),
        sa.Column(
            "started_at",
            sa.TIMESTAMP(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.Column("expires_at", sa.TIMESTAMP(), nullable=False),
        sa.Column("converted_to_paid", sa.Boolean(), nullable=True),
        sa.Column("conversion_date", sa.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(
        op.f("ix_trial_activations_expires_at"),
        "trial_activations",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_trial_activations_id"), "trial_activations", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_trial_activations_telegram_user_id"),
        "trial_activations",
        ["telegram_user_id"],
        unique=False,
    )

    op.create_table(
        "withdrawal_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("amount_usd", sa.DECIMAL(precision=10, scale=2), nullable=False),
        sa.Column("withdrawal_method", sa.String(length=50), nullable=False),
        sa.Column(
            "withdrawal_details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("admin_notes", sa.Text(), nullable=True),
        sa.Column("processed_by", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.Column("processed_at", sa.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(["processed_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_withdrawal_requests_created_at"),
        "withdrawal_requests",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_withdrawal_requests_id"), "withdrawal_requests", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_withdrawal_requests_status"),
        "withdrawal_requests",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_withdrawal_requests_user_id"),
        "withdrawal_requests",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "connection_logs",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("protocol_id", sa.Integer(), nullable=False),
        sa.Column("instance_id", sa.Integer(), nullable=True),
        sa.Column("connected_at", sa.TIMESTAMP(), nullable=False),
        sa.Column("disconnected_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("bytes_uploaded", sa.BigInteger(), nullable=True),
        sa.Column("bytes_downloaded", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["instance_id"],
            ["protocol_instances.id"],
        ),
        sa.ForeignKeyConstraint(
            ["protocol_id"],
            ["protocols.id"],
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_connection_logs_created_at"),
        "connection_logs",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_connection_logs_id"), "connection_logs", ["id"], unique=False
    )

    op.create_table(
        "connection_violations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("protocol_id", sa.Integer(), nullable=False),
        sa.Column("max_allowed", sa.Integer(), nullable=False),
        sa.Column("attempted_connections", sa.Integer(), nullable=False),
        sa.Column(
            "violation_time",
            sa.TIMESTAMP(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.Column("action_taken", sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(["protocol_id"], ["protocols.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["subscription_id"], ["subscriptions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_connection_violations_id"),
        "connection_violations",
        ["id"],
        unique=False,
    )

    op.create_table(
        "ip_change_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("protocol_id", sa.Integer(), nullable=False),
        sa.Column("old_instance_id", sa.Integer(), nullable=True),
        sa.Column("new_instance_id", sa.Integer(), nullable=True),
        sa.Column("requested_country_code", sa.String(length=2), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("denial_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.Column("processed_at", sa.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(
            ["new_instance_id"],
            ["protocol_instances.id"],
        ),
        sa.ForeignKeyConstraint(
            ["old_instance_id"],
            ["protocol_instances.id"],
        ),
        sa.ForeignKeyConstraint(["protocol_id"], ["protocols.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["subscription_id"], ["subscriptions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ip_change_requests_id"), "ip_change_requests", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_ip_change_requests_status"),
        "ip_change_requests",
        ["status"],
        unique=False,
    )

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=True),
        sa.Column("amount_usd", sa.DECIMAL(precision=10, scale=2), nullable=False),
        sa.Column("payment_method", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("transaction_id", sa.String(length=255), nullable=True),
        sa.Column("deposit_to_wallet", sa.Boolean(), nullable=True),
        sa.Column("extra_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.Column("completed_at", sa.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(
            ["subscription_id"], ["subscriptions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_payments_created_at"), "payments", ["created_at"], unique=False
    )
    op.create_index(op.f("ix_payments_id"), "payments", ["id"], unique=False)
    op.create_index(op.f("ix_payments_status"), "payments", ["status"], unique=False)
    op.create_index(
        op.f("ix_payments_transaction_id"), "payments", ["transaction_id"], unique=False
    )
    op.create_index(op.f("ix_payments_user_id"), "payments", ["user_id"], unique=False)

    op.create_table(
        "renewal_warnings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("days_before_expiration", sa.Integer(), nullable=False),
        sa.Column(
            "sent_at",
            sa.TIMESTAMP(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.Column("user_action", sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(
            ["subscription_id"], ["subscriptions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "subscription_id",
            "days_before_expiration",
            name="uq_subscription_warning_days",
        ),
    )
    op.create_index(
        op.f("ix_renewal_warnings_id"), "renewal_warnings", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_renewal_warnings_sent_at"),
        "renewal_warnings",
        ["sent_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_renewal_warnings_subscription_id"),
        "renewal_warnings",
        ["subscription_id"],
        unique=False,
    )

    op.create_table(
        "support_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("sender_id", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=True),
        sa.Column("is_internal", sa.Boolean(), nullable=True),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("read_at", sa.TIMESTAMP(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["support_tickets.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_support_messages_unread",
        "support_messages",
        ["ticket_id", "read_at"],
        unique=False,
        postgresql_where=sa.text("read_at IS NULL"),
    )
    op.create_index(
        op.f("ix_support_messages_id"), "support_messages", ["id"], unique=False
    )

    op.create_table(
        "usage_alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("threshold_percent", sa.Integer(), nullable=False),
        sa.Column("data_limit_gb", sa.Integer(), nullable=False),
        sa.Column("data_used_gb", sa.DECIMAL(precision=10, scale=2), nullable=False),
        sa.Column(
            "sent_at",
            sa.TIMESTAMP(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["subscription_id"], ["subscriptions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "subscription_id", "threshold_percent", name="uq_subscription_threshold"
        ),
    )
    op.create_index(op.f("ix_usage_alerts_id"), "usage_alerts", ["id"], unique=False)
    op.create_index(
        op.f("ix_usage_alerts_user_id"), "usage_alerts", ["user_id"], unique=False
    )

    op.create_table(
        "user_credentials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("protocol_id", sa.Integer(), nullable=False),
        sa.Column(
            "credential_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("server_location", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["protocol_id"], ["protocols.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["subscription_id"], ["subscriptions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "subscription_id", "protocol_id", name="uq_subscription_protocol"
        ),
    )
    op.create_index(
        op.f("ix_user_credentials_id"), "user_credentials", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_user_credentials_subscription_id"),
        "user_credentials",
        ["subscription_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_credentials_user_id"),
        "user_credentials",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "user_protocol_assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("protocol_id", sa.Integer(), nullable=False),
        sa.Column("instance_id", sa.Integer(), nullable=False),
        sa.Column(
            "assigned_at",
            sa.TIMESTAMP(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["instance_id"],
            ["protocol_instances.id"],
        ),
        sa.ForeignKeyConstraint(["protocol_id"], ["protocols.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["subscription_id"], ["subscriptions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "subscription_id", "protocol_id", name="uq_assignment_subscription_protocol"
        ),
    )
    op.create_index(
        op.f("ix_user_protocol_assignments_id"),
        "user_protocol_assignments",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_protocol_assignments_instance_id"),
        "user_protocol_assignments",
        ["instance_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_protocol_assignments_subscription_id"),
        "user_protocol_assignments",
        ["subscription_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_protocol_assignments_user_id"),
        "user_protocol_assignments",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "referral_earnings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("referrer_id", sa.Integer(), nullable=False),
        sa.Column("referred_user_id", sa.Integer(), nullable=False),
        sa.Column("payment_id", sa.Integer(), nullable=True),
        sa.Column(
            "commission_percent", sa.DECIMAL(precision=5, scale=2), nullable=False
        ),
        sa.Column("amount_usd", sa.DECIMAL(precision=10, scale=2), nullable=False),
        sa.Column("credited_to_wallet", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["referred_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["referrer_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_referral_earnings_id"), "referral_earnings", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_referral_earnings_referred_user_id"),
        "referral_earnings",
        ["referred_user_id"],
        unique=False,
    )

    op.create_table(
        "wallet_transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("amount_usd", sa.DECIMAL(precision=10, scale=2), nullable=False),
        sa.Column("transaction_type", sa.String(length=50), nullable=False),
        sa.Column("payment_id", sa.Integer(), nullable=True),
        sa.Column("subscription_id", sa.Integer(), nullable=True),
        sa.Column("reference_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("balance_before", sa.DECIMAL(precision=10, scale=2), nullable=True),
        sa.Column("balance_after", sa.DECIMAL(precision=10, scale=2), nullable=True),
        sa.Column("extra_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["subscription_id"], ["subscriptions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_wallet_transactions_id"), "wallet_transactions", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_wallet_transactions_reference_id"),
        "wallet_transactions",
        ["reference_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_wallet_transactions_status"),
        "wallet_transactions",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_wallet_transactions_transaction_type"),
        "wallet_transactions",
        ["transaction_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("wallet_transactions")
    op.drop_table("referral_earnings")
    op.drop_table("user_protocol_assignments")
    op.drop_table("user_credentials")
    op.drop_table("usage_alerts")
    op.drop_table("support_messages")
    op.drop_table("renewal_warnings")
    op.drop_table("payments")
    op.drop_table("ip_change_requests")
    op.drop_table("connection_violations")
    op.drop_table("connection_logs")
    op.drop_table("withdrawal_requests")
    op.drop_table("trial_activations")
    op.drop_table("support_tickets")
    op.drop_table("subscriptions")
    op.drop_table("protocol_instances")
    op.drop_table("ip_change_quota")
    op.drop_table("auth_logs")
    op.drop_table("admin_alerts")
    op.drop_table("users")
    op.drop_table("translations")
    op.drop_table("system_settings")
    op.drop_table("subscription_plans")
    op.drop_table("protocols")
