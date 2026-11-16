"""Add socks5_port to fdm_deployments for Telegram proxy."""

from alembic import op
import sqlalchemy as sa

revision = "20260607_001"
down_revision = "20260605_001"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    exists = conn.execute(
        sa.text("SELECT 1 FROM information_schema.columns "
                "WHERE table_name='fdm_deployments' AND column_name='socks5_port'")
    ).fetchone()
    if not exists:
        op.add_column(
            "fdm_deployments",
            sa.Column("socks5_port", sa.Integer(), nullable=True),
        )


def downgrade():
    op.drop_column("fdm_deployments", "socks5_port")
