"""Add composite index on protocol_instances(ip_address, is_active)

Improves JOIN performance for:
- connection_string_service._get_domains_for_country
- connection_string_service.generate_telegram_proxy_links
- FdmSyncService._validate_domain_ips_against_instances

All three query patterns filter protocol_instances by both ip_address
(for stale-IP validation) and is_active=True. A composite index turns
this from two index scans + bitmap AND into a single index seek.

Revision ID: 20260615_002
Revises: 20260615_001
Create Date: 2026-06-15
"""
from alembic import op

revision = "20260615_002"
down_revision = "20260615_001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "ix_protocol_instances_ip_active",
        "protocol_instances",
        ["ip_address", "is_active"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_protocol_instances_ip_active", table_name="protocol_instances")
