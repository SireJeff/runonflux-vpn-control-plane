"""create fdm_ip_liveness (endpoint-liveness gating, Problem B)

Revision ID: 20260801_001
Revises: 20260729_001
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import INET

revision = "20260801_001"
down_revision = "20260729_001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "fdm_ip_liveness",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("flux_app_name", sa.String(length=255), nullable=False),
        sa.Column("ip_address", INET(), nullable=False),
        sa.Column(
            "consecutive_failures",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("last_checked_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("last_live_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("demoted_at", sa.TIMESTAMP(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "flux_app_name", "ip_address", name="uq_fdm_ip_liveness_app_ip"
        ),
    )
    op.create_index("ix_fdm_ip_liveness_id", "fdm_ip_liveness", ["id"], unique=False)
    op.create_index(
        "ix_fdm_ip_liveness_flux_app_name",
        "fdm_ip_liveness",
        ["flux_app_name"],
        unique=False,
    )
    op.create_index(
        "ix_fdm_ip_liveness_ip_address",
        "fdm_ip_liveness",
        ["ip_address"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_fdm_ip_liveness_ip_address", table_name="fdm_ip_liveness")
    op.drop_index("ix_fdm_ip_liveness_flux_app_name", table_name="fdm_ip_liveness")
    op.drop_index("ix_fdm_ip_liveness_id", table_name="fdm_ip_liveness")
    op.drop_table("fdm_ip_liveness")
