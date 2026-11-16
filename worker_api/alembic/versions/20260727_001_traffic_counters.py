"""traffic_counters table

Revision ID: 20260727_001
Revises: 20260721_002
"""
import sqlalchemy as sa
from alembic import op

revision = "20260727_001"
down_revision = "20260721_002"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    exists = conn.execute(
        sa.text("SELECT 1 FROM information_schema.tables "
                "WHERE table_name='traffic_counters'")
    ).fetchone()
    if exists:
        return
    op.create_table(
        "traffic_counters",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=False),
        sa.Column("protocol", sa.String(20), nullable=False),
        sa.Column("instance_id", sa.String(64), nullable=False),
        sa.Column("last_cumulative_in", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_cumulative_out", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("boot_id", sa.String(64), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("user_id", "protocol", "instance_id", name="uq_traffic_counter"),
    )
    op.create_index("ix_traffic_counters_user_id", "traffic_counters", ["user_id"])


def downgrade():
    op.drop_table("traffic_counters")
