"""Protocol instance from-scratch gap: connection columns + instance-aware unique constraint

ProtocolInstance.current_connections / max_connections and the
uq_app_component_instance unique constraint (flux_app_name, component_name,
instance_number) exist on the model and in production (added out-of-band via
Base.metadata.create_all / manual DDL, per the PI-slot-reuse fix) but were
never captured by a migration. The original migration
(20260205_1221_d8e8d7b42e47) only created a two-column unique constraint
`uq_app_component` (flux_app_name, component_name) with no connection-count
columns, and no later migration ever added them.

A from-scratch `alembic upgrade head` therefore reaches head without error
but leaves `protocol_instances` missing columns that services/autoscaling/
autoscaler.py and other production code paths read directly
(`instance.current_connections`), and missing the 3-column unique constraint
needed to allow multiple instances per (app, component) distinguished by
instance_number.

Revision ID: 20260729_001
Revises: 20260728_003
Create Date: 2026-07-29

Idempotent: guarded via information_schema / inspector so it is a no-op on
any database where these already exist (i.e. production).
"""

import sqlalchemy as sa
from alembic import op

revision = "20260729_001"
down_revision = "20260728_003"
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


def _unique_constraint_names(conn, table):
    return {uc["name"] for uc in sa.inspect(conn).get_unique_constraints(table)}


def upgrade():
    conn = op.get_bind()

    if not _column_exists(conn, "protocol_instances", "current_connections"):
        op.add_column(
            "protocol_instances",
            sa.Column("current_connections", sa.Integer(), nullable=True, server_default="0"),
        )
    if not _column_exists(conn, "protocol_instances", "max_connections"):
        op.add_column(
            "protocol_instances",
            sa.Column("max_connections", sa.Integer(), nullable=True, server_default="100"),
        )

    existing = _unique_constraint_names(conn, "protocol_instances")
    if "uq_app_component" in existing:
        op.drop_constraint("uq_app_component", "protocol_instances", type_="unique")
    if "uq_app_component_instance" not in _unique_constraint_names(conn, "protocol_instances"):
        op.create_unique_constraint(
            "uq_app_component_instance",
            "protocol_instances",
            ["flux_app_name", "component_name", "instance_number"],
        )


def downgrade():
    conn = op.get_bind()

    existing = _unique_constraint_names(conn, "protocol_instances")
    if "uq_app_component_instance" in existing:
        op.drop_constraint("uq_app_component_instance", "protocol_instances", type_="unique")
    if "uq_app_component" not in _unique_constraint_names(conn, "protocol_instances"):
        op.create_unique_constraint(
            "uq_app_component", "protocol_instances", ["flux_app_name", "component_name"]
        )

    if _column_exists(conn, "protocol_instances", "max_connections"):
        op.drop_column("protocol_instances", "max_connections")
    if _column_exists(conn, "protocol_instances", "current_connections"):
        op.drop_column("protocol_instances", "current_connections")
