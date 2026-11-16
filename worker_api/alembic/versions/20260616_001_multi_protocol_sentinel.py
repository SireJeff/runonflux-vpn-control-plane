"""Add multi-protocol sentinel row to protocols table

Protocol-agnostic FDM deployments (NULL protocol_name) need a sentinel
protocol_id=0 to satisfy the protocol_instances.protocol_id FK constraint.
Without this row, _get_or_create_instance silently fails on every PI insert
for protocol-agnostic deployments, causing the connection-string JOIN to
exclude those IPs entirely (3-country limit regression).

Revision ID: 20260616_001
Revises: 20260615_002
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa

revision = "20260616_001"
down_revision = "20260615_002"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        INSERT INTO protocols (id, name, slug, display_name, description, is_active)
        VALUES (0, 'Multi-Protocol', 'multi-protocol',
                'Multi-Protocol (FDM sentinel)',
                'Sentinel row for protocol-agnostic FDM deployments. '
                'Required because protocol_instances.protocol_id is NOT NULL with FK.',
                true)
        ON CONFLICT (id) DO NOTHING
        """
    )
    # Ensure the sequence stays ahead of manually-inserted id=0
    # so future INSERTs without explicit id don't collide.
    op.execute("SELECT setval('protocols_id_seq', GREATEST((SELECT MAX(id) FROM protocols), 1))")


def downgrade():
    op.execute("DELETE FROM protocols WHERE id = 0")
