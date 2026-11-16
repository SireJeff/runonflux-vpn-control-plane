"""Add consecutive_failures column to fdm_deployments

Tracks the number of consecutive failed syncs per deployment.
Used by _auto_deactivate_phantom_deployments to deactivate phantom
deployments (e.g., regions where Flux no longer has instances) after
a configurable threshold of failures.

Revision ID: 20260615_001
Revises: 20260613_001
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa

revision = "20260615_001"
down_revision = "20260613_001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "fdm_deployments",
        sa.Column(
            "consecutive_failures",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    # Backfill: any deployment currently in 'failed' state starts at 1
    # so the new auto-deactivation logic can act on existing phantoms quickly.
    op.execute(
        "UPDATE fdm_deployments SET consecutive_failures = 1 "
        "WHERE last_sync_status = 'failed'"
    )


def downgrade():
    op.drop_column("fdm_deployments", "consecutive_failures")
