"""Create registered_tlds table and seed from platform_settings

Revision ID: 20260612_001
Revises: 20260611_001
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "20260612_001"
down_revision = "20260611_001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "registered_tlds",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("dns_provider", sa.String(20), nullable=False),
        sa.Column("zone_id", sa.String(255), nullable=True),
        sa.Column("purpose", sa.String(20), nullable=False),
        sa.Column("server_ip", sa.String(45), nullable=True),
        sa.Column("is_active", sa.Boolean, default=False, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.TIMESTAMP, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("domain", "purpose", name="uq_registered_tlds_domain_purpose"),
    )
    op.create_index("ix_registered_tlds_id", "registered_tlds", ["id"])
    op.create_index("ix_registered_tlds_purpose", "registered_tlds", ["purpose"])
    op.create_index("ix_registered_tlds_is_active", "registered_tlds", ["is_active"])

    # Seed: read current Cloudflare domain + zone_id from platform_settings
    conn = op.get_bind()

    domain_row = conn.execute(
        text("SELECT value FROM platform_settings WHERE key = 'cloudflare_domain'")
    ).fetchone()
    zone_row = conn.execute(
        text("SELECT value FROM platform_settings WHERE key = 'cloudflare_zone_id'")
    ).fetchone()

    if domain_row and domain_row[0]:
        domain = domain_row[0]
        zone_id = zone_row[0] if zone_row else None
        conn.execute(
            text(
                "INSERT INTO registered_tlds (domain, dns_provider, zone_id, purpose, is_active) "
                "VALUES (:domain, 'cloudflare', :zone_id, 'fdm', true)"
            ),
            {"domain": domain, "zone_id": zone_id},
        )


def downgrade():
    op.drop_index("ix_registered_tlds_is_active")
    op.drop_index("ix_registered_tlds_purpose")
    op.drop_index("ix_registered_tlds_id")
    op.drop_table("registered_tlds")
