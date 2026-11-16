"""add crypto payment fields to user_orders

Revision ID: 20260728_002
Revises: 20260728_001
"""

import sqlalchemy as sa
from alembic import op

revision = "20260728_002"
down_revision = "20260728_001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "user_orders",
        sa.Column("payment_method", sa.String(10), nullable=False, server_default="card"),
    )
    op.add_column("user_orders", sa.Column("crypto_txid", sa.String(255), nullable=True))
    op.add_column("user_orders", sa.Column("crypto_link", sa.Text(), nullable=True))
    op.add_column("user_orders", sa.Column("amount_usd_snapshot", sa.Numeric(12, 2), nullable=True))


def downgrade():
    op.drop_column("user_orders", "amount_usd_snapshot")
    op.drop_column("user_orders", "crypto_link")
    op.drop_column("user_orders", "crypto_txid")
    op.drop_column("user_orders", "payment_method")
