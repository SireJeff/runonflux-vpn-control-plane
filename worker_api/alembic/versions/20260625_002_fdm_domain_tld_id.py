"""phase 4a: fdm_domains.tld_id FK + backfill to active fdm TLD

Revision ID: 20260625_002
Revises: 20260625_001
Create Date: 2026-06-25

Idempotent: add_column is guarded with an information_schema check
(migrations re-run on container rebuild; an unguarded re-run crash-loops
with DuplicateColumn). Backfill is a one-shot UPDATE that only touches
NULL rows, so it is safe to re-run.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260625_002"
down_revision = "20260625_001"
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


def upgrade():
    conn = op.get_bind()

    if not _column_exists(conn, "fdm_domains", "tld_id"):
        op.add_column(
            "fdm_domains",
            sa.Column(
                "tld_id",
                sa.Integer(),
                sa.ForeignKey("registered_tlds.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
        op.create_index(
            "ix_fdm_domains_tld_id", "fdm_domains", ["tld_id"]
        )

    # Backfill: every existing fdm_domains row belongs to the single active
    # fdm TLD today. Pick the lowest-id active, non-deleted fdm TLD (matches
    # TldSelectionService tie-break). Idempotent: only touches NULL rows.
    active_fdm = conn.execute(
        sa.text(
            "SELECT id FROM registered_tlds "
            "WHERE purpose = 'fdm' AND is_active = true AND deleted_at IS NULL "
            "ORDER BY id LIMIT 1"
        )
    ).fetchone()
    if active_fdm is not None:
        conn.execute(
            sa.text(
                "UPDATE fdm_domains SET tld_id = :tid WHERE tld_id IS NULL"
            ),
            {"tid": active_fdm[0]},
        )


def downgrade():
    conn = op.get_bind()
    if _column_exists(conn, "fdm_domains", "tld_id"):
        op.drop_index("ix_fdm_domains_tld_id", table_name="fdm_domains")
        op.drop_column("fdm_domains", "tld_id")
