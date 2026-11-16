"""add crypto payment fields to wire_orders

Revision ID: 20260728_001
Revises: 20260727_002
"""

import sqlalchemy as sa
from alembic import op

revision = "20260728_001"
down_revision = "20260727_002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "wire_orders",
        sa.Column("payment_method", sa.String(10), nullable=False, server_default="wire"),
    )
    op.add_column("wire_orders", sa.Column("crypto_txid", sa.String(255), nullable=True))
    op.add_column("wire_orders", sa.Column("crypto_link", sa.Text(), nullable=True))
    op.add_column("wire_orders", sa.Column("usd_rate_snapshot", sa.Numeric(12, 2), nullable=True))


def downgrade():
    op.drop_column("wire_orders", "usd_rate_snapshot")
    op.drop_column("wire_orders", "crypto_link")
    op.drop_column("wire_orders", "crypto_txid")
    op.drop_column("wire_orders", "payment_method")
