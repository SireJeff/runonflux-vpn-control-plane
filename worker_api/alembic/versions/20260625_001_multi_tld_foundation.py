"""multi tld foundation: admin_tld_states + registered_tlds.deleted_at

Revision ID: 20260625_001
Revises: 20260619_001
Create Date: 2026-06-25

Idempotent: create_table/add_column are guarded with information_schema checks.
Migrations re-run on container rebuild here (see deployment_setup gotchas); an
unguarded re-run crash-loops with DuplicateTable/DuplicateColumn.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260625_001"
down_revision = "20260619_001"
branch_labels = None
depends_on = None


def _table_exists(conn, name):
    return conn.execute(
        sa.text("SELECT 1 FROM information_schema.tables WHERE table_name = :n"),
        {"n": name},
    ).fetchone() is not None


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

    if not _table_exists(conn, "admin_tld_states"):
        op.create_table(
            "admin_tld_states",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("admin_id", sa.Integer(), sa.ForeignKey("admins.id", ondelete="CASCADE"), nullable=False),
            sa.Column("purpose", sa.String(length=20), nullable=False),
            sa.Column("pinned_tld_id", sa.Integer(), sa.ForeignKey("registered_tlds.id", ondelete="SET NULL"), nullable=True),
            sa.Column("effective_tld_id", sa.Integer(), sa.ForeignKey("registered_tlds.id", ondelete="SET NULL"), nullable=True),
            sa.Column("source", sa.String(length=12), nullable=False, server_default="unassigned"),
            sa.Column("assigned_at", sa.TIMESTAMP(), server_default=sa.func.current_timestamp()),
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.current_timestamp()),
            sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.current_timestamp()),
            sa.UniqueConstraint("admin_id", "purpose", name="uq_admin_tld_state_admin_purpose"),
        )
        op.create_index("ix_admin_tld_states_admin_id", "admin_tld_states", ["admin_id"])
        op.create_index("ix_admin_tld_states_effective_tld_id", "admin_tld_states", ["effective_tld_id"])

    if not _column_exists(conn, "registered_tlds", "deleted_at"):
        op.add_column(
            "registered_tlds",
            sa.Column("deleted_at", sa.TIMESTAMP(), nullable=True),
        )


def downgrade():
    conn = op.get_bind()
    if _column_exists(conn, "registered_tlds", "deleted_at"):
        op.drop_column("registered_tlds", "deleted_at")
    if _table_exists(conn, "admin_tld_states"):
        op.drop_index("ix_admin_tld_states_admin_id", table_name="admin_tld_states")
        op.drop_table("admin_tld_states")
