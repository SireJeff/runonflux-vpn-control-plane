"""Increase wallet precision to 6 decimal places

Traffic billing at $0.02/GB produces micro-transactions
(e.g. 100MB = $0.00195). 2 decimal places rounds these to $0.00.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260604_002"
down_revision = "20260604_0015"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("admins", "wallet_balance", type_=sa.Numeric(12, 6))
    op.alter_column("wallet_transactions_v2", "amount_usd", type_=sa.Numeric(12, 6))
    op.alter_column("wallet_transactions_v2", "balance_before", type_=sa.Numeric(12, 6))
    op.alter_column("wallet_transactions_v2", "balance_after", type_=sa.Numeric(12, 6))


def downgrade():
    op.alter_column("admins", "wallet_balance", type_=sa.Numeric(12, 2))
    op.alter_column("wallet_transactions_v2", "amount_usd", type_=sa.Numeric(12, 2))
    op.alter_column("wallet_transactions_v2", "balance_before", type_=sa.Numeric(12, 2))
    op.alter_column("wallet_transactions_v2", "balance_after", type_=sa.Numeric(12, 2))
