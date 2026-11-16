"""Create v2 gap tables missing from the from-scratch migration chain

wallet_transactions_v2 and flux_app_registrations existed only as SQLAlchemy
models (provisioned at runtime via Base.metadata.create_all, and in the test
conftest) and were never captured by a create_table migration. A from-scratch
`alembic upgrade head` therefore failed at 20260604_002, which alters
wallet_transactions_v2 before it exists.

This migration is inserted BEFORE 20260604_002 (down_revision 20260604_001).
On a database already at a later head (e.g. production) it is an already-applied
ancestor and never runs; the inspector guards make it a no-op even if it did.
On a fresh database it creates both tables so the rest of the chain (including
the alter in 20260604_002) succeeds. Column types/precision match the models.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260604_0015"
down_revision = "20260604_001"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade():
    if not _has_table("wallet_transactions_v2"):
        op.create_table(
            "wallet_transactions_v2",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "admin_id",
                sa.Integer(),
                sa.ForeignKey("admins.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("amount_usd", sa.Numeric(12, 6), nullable=False),
            sa.Column("transaction_type", sa.String(length=50), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("reference_id", sa.String(length=255), nullable=True),
            sa.Column("balance_before", sa.Numeric(12, 6), nullable=True),
            sa.Column("balance_after", sa.Numeric(12, 6), nullable=True),
            sa.Column("extra_data", postgresql.JSONB(), nullable=True),
            sa.Column(
                "created_at",
                sa.TIMESTAMP(),
                server_default=sa.text("now()"),
                nullable=True,
            ),
        )
        op.create_index(
            "ix_wallet_transactions_v2_admin_id",
            "wallet_transactions_v2",
            ["admin_id"],
        )
        op.create_index(
            "ix_wallet_transactions_v2_transaction_type",
            "wallet_transactions_v2",
            ["transaction_type"],
        )
        op.create_index(
            "ix_wallet_transactions_v2_status",
            "wallet_transactions_v2",
            ["status"],
        )
        op.create_index(
            "ix_wallet_transactions_v2_reference_id",
            "wallet_transactions_v2",
            ["reference_id"],
        )

    if not _has_table("flux_app_registrations"):
        op.create_table(
            "flux_app_registrations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("app_name", sa.String(length=255), nullable=False),
            sa.Column("protocol_ports", postgresql.JSONB(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=True),
            sa.Column("registered_by", sa.Integer(), nullable=True),
            sa.Column("last_discovery_at", sa.TIMESTAMP(), nullable=True),
            sa.Column("last_discovery_ips", postgresql.JSONB(), nullable=True),
            sa.Column(
                "created_at",
                sa.TIMESTAMP(),
                server_default=sa.text("now()"),
                nullable=True,
            ),
            sa.Column(
                "updated_at",
                sa.TIMESTAMP(),
                server_default=sa.text("now()"),
                nullable=True,
            ),
            sa.Column("expected_instances", sa.Integer(), nullable=True),
            sa.Column("spec_components", postgresql.JSONB(), nullable=True),
            sa.Column("spec_geolocation", postgresql.JSONB(), nullable=True),
            sa.Column("last_spec_fetched_at", sa.TIMESTAMP(), nullable=True),
            sa.Column("last_spec_status", sa.String(length=50), nullable=True),
            sa.UniqueConstraint("app_name", name="uq_flux_app_registrations_app_name"),
        )
        op.create_index(
            "ix_flux_app_registrations_is_active",
            "flux_app_registrations",
            ["is_active"],
        )


def downgrade():
    if _has_table("flux_app_registrations"):
        op.drop_table("flux_app_registrations")
    if _has_table("wallet_transactions_v2"):
        op.drop_table("wallet_transactions_v2")
