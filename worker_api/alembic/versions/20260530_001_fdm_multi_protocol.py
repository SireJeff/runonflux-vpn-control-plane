"""add protocol_name and health_check_port to fdm_deployments

Revision ID: 20260530_001
Revises: 20260529_002
Create Date: 2026-05-30
"""
from alembic import op
import sqlalchemy as sa

revision = '20260530_001'
down_revision = '20260529_002'
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns
    op.add_column('fdm_deployments', sa.Column('protocol_name', sa.String(50), nullable=True))
    op.add_column('fdm_deployments', sa.Column(
        'health_check_port', sa.Integer(), server_default='443', nullable=False
    ))

    # Drop old single-column unique index (created by original migration)
    op.drop_index('ix_fdm_deployments_flux_app_name', table_name='fdm_deployments')

    # Drop old unnamed unique constraint (auto-named by PostgreSQL)
    op.drop_constraint('fdm_deployments_flux_app_name_key', 'fdm_deployments', type_='unique')

    # Create new composite unique constraint
    op.create_unique_constraint(
        'uq_deployment_app_protocol', 'fdm_deployments',
        ['flux_app_name', 'protocol_name']
    )

    # Recreate non-unique index on flux_app_name (still useful for lookups)
    op.create_index(
        'ix_fdm_deployments_flux_app_name', 'fdm_deployments',
        ['flux_app_name'], unique=False
    )


def downgrade():
    # Drop composite constraint
    op.drop_constraint('uq_deployment_app_protocol', 'fdm_deployments', type_='unique')

    # Drop columns
    op.drop_column('fdm_deployments', 'health_check_port')
    op.drop_column('fdm_deployments', 'protocol_name')

    # Restore original unique index
    op.drop_index('ix_fdm_deployments_flux_app_name', table_name='fdm_deployments')
    op.create_index(
        'ix_fdm_deployments_flux_app_name', 'fdm_deployments',
        ['flux_app_name'], unique=True
    )

    # Restore original unique constraint
    op.create_unique_constraint(
        'fdm_deployments_flux_app_name_key', 'fdm_deployments',
        ['flux_app_name'], type_='unique'
    )
