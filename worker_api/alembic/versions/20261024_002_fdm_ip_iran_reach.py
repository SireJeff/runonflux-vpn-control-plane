"""create fdm_ip_iran_reach (FDM Iran reachability via check-host.net)

A new table rather than columns on fdm_ip_liveness: if this migration never
runs, only the Iran check is disabled (both of its paths fail open), and the
liveness gate's model keeps working. IF NOT EXISTS makes a re-run a no-op,
since worker-api runs `alembic upgrade head` under `set -e` at every start.

Revision ID: 20261024_002
Revises: 20261024_001
"""

from alembic import op

revision = "20261024_002"
down_revision = "20261024_001"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS fdm_ip_iran_reach (
            id SERIAL PRIMARY KEY,
            flux_app_name VARCHAR(255) NOT NULL,
            ip_address INET NOT NULL,
            port INTEGER,
            pending_request_id VARCHAR(64),
            submitted_at TIMESTAMP,
            checked_at TIMESTAMP,
            blocked_streak INTEGER NOT NULL DEFAULT 0,
            blocked_at TIMESTAMP,
            last_verdict VARCHAR(16),
            last_summary VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_fdm_ip_iran_reach_app_ip UNIQUE (flux_app_name, ip_address)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_fdm_ip_iran_reach_id ON fdm_ip_iran_reach (id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_fdm_ip_iran_reach_flux_app_name "
        "ON fdm_ip_iran_reach (flux_app_name)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_fdm_ip_iran_reach_ip_address "
        "ON fdm_ip_iran_reach (ip_address)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS fdm_ip_iran_reach")
