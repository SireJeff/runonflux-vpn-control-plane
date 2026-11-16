"""Referral traffic bonus: reward_type + traffic bonus columns.

Revision ID: 20260827_001
Revises: 20260824_001
Create Date: 2026-08-27
"""
import sqlalchemy as sa
from alembic import op

revision = "20260827_001"
down_revision = "20260824_001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "admin_referral_configs",
        sa.Column(
            "reward_type", sa.String(20), nullable=False, server_default="cashback"
        ),
    )
    op.add_column(
        "admin_referral_configs",
        sa.Column(
            "traffic_per_referral_mb", sa.Integer, nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "admin_referral_configs",
        sa.Column(
            "traffic_max_bonus_mb", sa.Integer, nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "free_config_global",
        sa.Column(
            "max_referral_bonus_mb", sa.Integer, nullable=False, server_default="1000"
        ),
    )


def downgrade():
    op.drop_column("free_config_global", "max_referral_bonus_mb")
    op.drop_column("admin_referral_configs", "traffic_max_bonus_mb")
    op.drop_column("admin_referral_configs", "traffic_per_referral_mb")
    op.drop_column("admin_referral_configs", "reward_type")
