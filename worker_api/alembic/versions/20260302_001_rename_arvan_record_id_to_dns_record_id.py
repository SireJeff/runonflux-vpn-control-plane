"""rename arvan_record_id to dns_record_id

Revision ID: 20260302_001
Revises: 20260228_001
Create Date: 2026-03-02
"""
from alembic import op
import sqlalchemy as sa

revision = "20260302_001"
down_revision = "20260228_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "fdm_domains",
        "arvan_record_id",
        new_column_name="dns_record_id",
        existing_type=sa.String(255),
    )


def downgrade() -> None:
    op.alter_column(
        "fdm_domains",
        "dns_record_id",
        new_column_name="arvan_record_id",
        existing_type=sa.String(255),
    )
