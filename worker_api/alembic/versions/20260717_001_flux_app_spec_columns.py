"""Add spec-awareness columns to flux_app_registrations (FDM Hardening Phase 3.1)

Stores the Flux appspecifications snapshot so FDM can size domain pools to a
Flux app's declared instance count and surface an expected-vs-actual gap.
All columns nullable: populated on the first reconcile cycle by FluxSpecFetcher.

Revision ID: 20260717_001
Revises: 20260626_001
Create Date: 2026-07-17

Idempotent: add_column is guarded with an information_schema check (migrations
re-run on container rebuild; an unguarded re-run crash-loops with DuplicateColumn).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260717_001"
down_revision = "20260626_001"
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


_COLUMNS = [
    ("expected_instances", sa.Integer()),
    ("spec_components", JSONB()),
    ("spec_geolocation", JSONB()),
    ("last_spec_fetched_at", sa.TIMESTAMP()),
    ("last_spec_status", sa.String(length=50)),
]

_TABLE = "flux_app_registrations"


def upgrade():
    conn = op.get_bind()
    for name, typ in _COLUMNS:
        if not _column_exists(conn, _TABLE, name):
            op.add_column(_TABLE, sa.Column(name, typ, nullable=True))


def downgrade():
    conn = op.get_bind()
    for name, _ in reversed(_COLUMNS):
        if _column_exists(conn, _TABLE, name):
            op.drop_column(_TABLE, name)
