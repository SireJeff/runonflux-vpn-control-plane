"""Add traffic_limit_bytes to admin_users

Revision ID: 20260604_001
Revises: 20260530_002
Create Date: 2026-06-04
"""
from alembic import op
import sqlalchemy as sa

revision = '20260604_001'
down_revision = '20260530_002'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'admin_users',
        sa.Column('traffic_limit_bytes', sa.BigInteger(), nullable=True, comment='Per-user traffic limit in bytes. NULL = unlimited'),
    )


def downgrade():
    op.drop_column('admin_users', 'traffic_limit_bytes')
