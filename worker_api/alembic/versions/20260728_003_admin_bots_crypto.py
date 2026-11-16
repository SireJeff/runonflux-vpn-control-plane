"""add per-reseller crypto address to admin_bots

Revision ID: 20260728_003
Revises: 20260728_002
"""

import sqlalchemy as sa
from alembic import op

revision = "20260728_003"
down_revision = "20260728_002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("admin_bots", sa.Column("crypto_address", sa.String(255), nullable=True))
    op.add_column("admin_bots", sa.Column("crypto_network", sa.String(50), nullable=True))
    op.add_column("admin_bots", sa.Column("crypto_memo", sa.String(255), nullable=True))


def downgrade():
    op.drop_column("admin_bots", "crypto_memo")
    op.drop_column("admin_bots", "crypto_network")
    op.drop_column("admin_bots", "crypto_address")
