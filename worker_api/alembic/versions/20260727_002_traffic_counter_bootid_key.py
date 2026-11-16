"""traffic_counters: add boot_id to the unique key (per-replica)

One Flux app (one FLUXVPN_INSTANCE_ID) runs many replicas that all report the
same instance_id; each replica has a unique boot_id. Keying by boot_id gives
each replica-boot its own row so they don't collide/thrash. The table is empty
in prod (no v2 containers reporting yet), so this re-key is safe.

Revision ID: 20260727_002
Revises: 20260727_001
"""
import sqlalchemy as sa
from alembic import op

revision = "20260727_002"
down_revision = "20260727_001"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    # Backfill any NULL boot_id to '' (table is empty in prod, but be safe) and
    # make the column NOT NULL with a '' default.
    conn.execute(sa.text("UPDATE traffic_counters SET boot_id = '' WHERE boot_id IS NULL"))
    op.alter_column(
        "traffic_counters", "boot_id",
        existing_type=sa.String(64), nullable=False, server_default="",
    )
    # Swap the unique constraint to include boot_id (idempotent-ish: drop if present).
    conn.execute(sa.text("ALTER TABLE traffic_counters DROP CONSTRAINT IF EXISTS uq_traffic_counter"))
    op.create_unique_constraint(
        "uq_traffic_counter", "traffic_counters",
        ["user_id", "protocol", "instance_id", "boot_id"],
    )


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text("ALTER TABLE traffic_counters DROP CONSTRAINT IF EXISTS uq_traffic_counter"))
    op.create_unique_constraint(
        "uq_traffic_counter", "traffic_counters",
        ["user_id", "protocol", "instance_id"],
    )
    op.alter_column(
        "traffic_counters", "boot_id",
        existing_type=sa.String(64), nullable=True, server_default=None,
    )
