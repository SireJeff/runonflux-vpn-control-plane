"""Add password_enc column to admin_users for encrypted plaintext display."""
from alembic import op
import sqlalchemy as sa


revision = "20260619_001"
down_revision = "20260616_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "admin_users",
        sa.Column("password_enc", sa.LargeBinary(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("admin_users", "password_enc")
