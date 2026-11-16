"""Add last_connection_refresh_at to admin_users for rate-limited refresh."""

from alembic import op
import sqlalchemy as sa

revision = "20260605_001"
down_revision = "20260604_002"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    exists = conn.execute(
        sa.text("SELECT 1 FROM information_schema.columns "
                "WHERE table_name='admin_users' AND column_name='last_connection_refresh_at'")
    ).fetchone()
    if not exists:
        op.add_column(
            "admin_users",
            sa.Column("last_connection_refresh_at", sa.TIMESTAMP(), nullable=True),
        )
    else:
        print("Column last_connection_refresh_at already exists, skipping.")


def downgrade():
    op.drop_column("admin_users", "last_connection_refresh_at")
