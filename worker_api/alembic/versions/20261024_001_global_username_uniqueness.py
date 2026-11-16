"""Global, case-insensitive end-user usernames.

VPN containers key Xray clients by ``email = username`` across ALL resellers and
Xray compares emails case-insensitively, so one duplicate username made Xray
reject its config and crash-looped every VLESS/Trojan container (2026-10-24).

1. Rename the legacy shared free-config sentinel ``__free__`` to the
   per-reseller ``__free__<admin_id>`` (matches ``free_username()``).
2. Add a partial unique index on ``lower(username)`` for non-deleted users.

Runs automatically on worker-api start, so a failure would crash-loop the API.
If duplicates still exist the index is SKIPPED with a loud warning instead
(sync-users dedupes defensively meanwhile); resolve them and re-run the
CREATE INDEX statement below by hand.

Revision ID: 20261024_001
Revises: 20260827_001
Create Date: 2026-10-24
"""
import sqlalchemy as sa
from alembic import op

revision = "20261024_001"
down_revision = "20260827_001"
branch_labels = None
depends_on = None

INDEX = "uq_admin_users_username_ci"
CREATE_INDEX = (
    f"CREATE UNIQUE INDEX IF NOT EXISTS {INDEX} ON admin_users (lower(username)) "
    "WHERE status IS DISTINCT FROM 'deleted'"
)


def upgrade():
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE admin_users SET username = '__free__' || admin_id "
            "WHERE username = '__free__'"
        )
    )
    dups = conn.execute(
        sa.text(
            "SELECT lower(username) AS u, array_agg(id ORDER BY id) AS ids "
            "FROM admin_users WHERE status IS DISTINCT FROM 'deleted' "
            "GROUP BY lower(username) HAVING count(*) > 1"
        )
    ).fetchall()
    if dups:
        print(
            f"WARNING [{revision}]: NOT creating {INDEX}; duplicate usernames "
            f"(case-insensitive, non-deleted): {[(d.u, list(d.ids)) for d in dups]}. "
            f"Rename them, then run: {CREATE_INDEX}"
        )
        return
    conn.execute(sa.text(CREATE_INDEX))


def downgrade():
    op.execute(f"DROP INDEX IF EXISTS {INDEX}")
    op.execute(
        "UPDATE admin_users SET username = '__free__' "
        "WHERE username = '__free__' || admin_id"
    )
