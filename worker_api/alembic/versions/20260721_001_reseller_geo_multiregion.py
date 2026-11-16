"""Reseller geo axis + multi-region users + order region set

Adds admin_packages.region_count/all_regions, user_orders.macro_regions,
user_regions.status/region_expires_at, and swaps user_regions unique
constraint from (user_id) to (user_id, macro_region).

Revision ID: 20260721_001
Revises: 20260717_001
Create Date: 2026-07-21

Idempotent: every add/drop is guarded via information_schema (migrations
re-run on container rebuild; unguarded re-runs crash-loop).
"""
from alembic import op
import sqlalchemy as sa

revision = "20260721_001"
down_revision = "20260717_001"
branch_labels = None
depends_on = None


def _column_exists(conn, table, column):
    return conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    ).fetchone() is not None


def _constraint_exists(conn, name):
    return conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.table_constraints "
            "WHERE constraint_name = :n"
        ),
        {"n": name},
    ).fetchone() is not None


def upgrade():
    conn = op.get_bind()

    if not _column_exists(conn, "admin_packages", "region_count"):
        op.add_column("admin_packages", sa.Column("region_count", sa.SmallInteger(), nullable=False, server_default="1"))
    if not _column_exists(conn, "admin_packages", "all_regions"):
        op.add_column("admin_packages", sa.Column("all_regions", sa.Boolean(), nullable=False, server_default="false"))

    from sqlalchemy.dialects.postgresql import JSONB
    if not _column_exists(conn, "user_orders", "macro_regions"):
        op.add_column("user_orders", sa.Column("macro_regions", JSONB(), nullable=True))

    if not _column_exists(conn, "user_regions", "status"):
        op.add_column("user_regions", sa.Column("status", sa.String(length=20), nullable=False, server_default="active"))
    if not _column_exists(conn, "user_regions", "region_expires_at"):
        op.add_column("user_regions", sa.Column("region_expires_at", sa.TIMESTAMP(), nullable=True))

    # Swap the unique constraint: (user_id) -> (user_id, macro_region)
    if _constraint_exists(conn, "uq_user_region_user"):
        op.drop_constraint("uq_user_region_user", "user_regions", type_="unique")
    if not _constraint_exists(conn, "uq_user_region_user_macro"):
        op.create_unique_constraint(
            "uq_user_region_user_macro", "user_regions", ["user_id", "macro_region"]
        )


def downgrade():
    conn = op.get_bind()
    if _constraint_exists(conn, "uq_user_region_user_macro"):
        op.drop_constraint("uq_user_region_user_macro", "user_regions", type_="unique")
    if not _constraint_exists(conn, "uq_user_region_user"):
        op.create_unique_constraint("uq_user_region_user", "user_regions", ["user_id"])
    for table, col in [
        ("user_regions", "region_expires_at"),
        ("user_regions", "status"),
        ("user_orders", "macro_regions"),
        ("admin_packages", "all_regions"),
        ("admin_packages", "region_count"),
    ]:
        if _column_exists(conn, table, col):
            op.drop_column(table, col)
