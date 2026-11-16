"""Stealth DNS + load balancing redesign

Revision ID: 20260612_002
Revises: 20260612_001
Create Date: 2026-06-12

Changes:
1. Add assigned_domain_id to admin_users (nullable FK to fdm_domains)
2. Merge per-protocol deployments into per-region deployments
3. Reassign domains from deleted deployments to surviving deployment
4. Drop old unique constraint, add new one
5. Expand domain_id column from String(5) to String(20)
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "20260612_002"
down_revision = "20260612_001"
branch_labels = None
depends_on = None


def _unique_constraint_names(conn, table):
    return {
        uc["name"] for uc in sa.inspect(conn).get_unique_constraints(table)
    }


def upgrade():
    # 1. Add assigned_domain_id to admin_users
    op.add_column(
        "admin_users",
        sa.Column("assigned_domain_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_admin_users_assigned_domain_id",
        "admin_users",
        "fdm_domains",
        ["assigned_domain_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 2. Expand domain_id column from String(5) to String(20)
    op.alter_column(
        "fdm_domains",
        "domain_id",
        existing_type=sa.String(5),
        type_=sa.String(20),
        existing_nullable=False,
    )

    # 3. Merge deployments: for each (flux_app_name, region), keep the first
    #    deployment, reassign all domains from others to it, delete the rest.
    conn = op.get_bind()

    # Only merge deployments that have a real region (not 'XX')
    groups = conn.execute(
        text("""
            SELECT flux_app_name, region, array_agg(id ORDER BY id) as deployment_ids,
                   count(*) as deployment_count
            FROM fdm_deployments
            WHERE is_active = true AND region != 'XX'
            GROUP BY flux_app_name, region
            HAVING count(*) > 1
        """)
    ).fetchall()

    for flux_app_name, region, deployment_ids, count in groups:
        surviving_id = deployment_ids[0]

        for dep_id in deployment_ids[1:]:
            # Reassign domains
            conn.execute(
                text(
                    "UPDATE fdm_domains SET deployment_id = :surviving "
                    "WHERE deployment_id = :old"
                ),
                {"surviving": surviving_id, "old": dep_id},
            )

            # Reassign sync logs
            conn.execute(
                text(
                    "UPDATE fdm_sync_logs SET deployment_id = :surviving "
                    "WHERE deployment_id = :old"
                ),
                {"surviving": surviving_id, "old": dep_id},
            )

            # Delete redundant deployment
            conn.execute(
                text("DELETE FROM fdm_deployments WHERE id = :id"),
                {"id": dep_id},
            )

    # 4. Drop old unique constraint, add new one
    #
    # NOTE: on databases built via the historical migration chain, the only
    # constraint that could exist at this point is `uq_deployment_app_protocol`
    # (created in 20260530_001, on flux_app_name+protocol_name -- it was never
    # renamed to include "region" by any migration). Production databases were
    # evolved out-of-band (manual DDL / create_all) and, at the time this
    # migration originally ran there, actually had a constraint literally named
    # `uq_deployment_app_protocol_region`. Guard both possibilities so a
    # from-scratch `alembic upgrade head` and an already-migrated database both
    # work, and so this step is a safe no-op if run again.
    existing = _unique_constraint_names(conn, "fdm_deployments")
    if "uq_deployment_app_protocol_region" in existing:
        op.drop_constraint(
            "uq_deployment_app_protocol_region", "fdm_deployments", type_="unique"
        )
    elif "uq_deployment_app_protocol" in existing:
        op.drop_constraint(
            "uq_deployment_app_protocol", "fdm_deployments", type_="unique"
        )

    if "uq_deployment_app_region" not in _unique_constraint_names(
        conn, "fdm_deployments"
    ):
        op.create_unique_constraint(
            "uq_deployment_app_region", "fdm_deployments", ["flux_app_name", "region"]
        )


def downgrade():
    conn = op.get_bind()
    existing = _unique_constraint_names(conn, "fdm_deployments")
    if "uq_deployment_app_region" in existing:
        op.drop_constraint("uq_deployment_app_region", "fdm_deployments", type_="unique")
    if "uq_deployment_app_protocol_region" not in _unique_constraint_names(
        conn, "fdm_deployments"
    ):
        op.create_unique_constraint(
            "uq_deployment_app_protocol_region",
            "fdm_deployments",
            ["flux_app_name", "protocol_name", "region"],
        )

    op.alter_column(
        "fdm_domains",
        "domain_id",
        existing_type=sa.String(20),
        type_=sa.String(5),
        existing_nullable=False,
    )

    op.drop_constraint("fk_admin_users_assigned_domain_id", "admin_users", type_="foreignkey")
    op.drop_column("admin_users", "assigned_domain_id")
