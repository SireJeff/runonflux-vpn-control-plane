"""Macro region refactor: replace region_code with macro_region

Revision ID: 20260610_001
Revises: 20260607_001
Create Date: 2026-06-10
"""

from alembic import op
import sqlalchemy as sa

revision = "20260610_001"
down_revision = "20260607_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step 1: Add macro_region column (nullable first for data migration)
    op.add_column("user_regions", sa.Column("macro_region", sa.String(5), nullable=True))

    # Step 2: Populate macro_region from region_code using country mapping
    op.execute("""
        UPDATE user_regions SET macro_region = (
            CASE
                WHEN region_code IN (
                    'NL','CH','DE','FR','GB','PL','SE','FI','NO','DK',
                    'IT','ES','PT','IE','AT','BE','LU','CZ','RO','BG',
                    'HU','UA','RS','HR','SK','SI','LT','LV','EE','GR'
                ) THEN 'eu'
                WHEN region_code IN (
                    'SG','JP','HK','KR','IN','AE','TR','TH','MY','PH',
                    'ID','VN','TW','IL','SA','QA','KW','BH','OM','PK',
                    'BD','LK','MM','KH','LA'
                ) THEN 'as'
                WHEN region_code IN ('US','CA','MX') THEN 'na'
                ELSE 'row'
            END
        )
    """)

    # Step 3: Delete non-primary UserRegion rows
    op.execute("DELETE FROM user_regions WHERE is_primary = false OR is_primary IS NULL")

    # Step 4: Delete any remaining rows with NULL macro_region
    op.execute("DELETE FROM user_regions WHERE macro_region IS NULL")

    # Step 5: Make macro_region NOT NULL
    op.alter_column("user_regions", "macro_region", nullable=False)

    # Step 6: Drop old unique constraint on (user_id, region_code)
    op.drop_constraint("uq_user_region", "user_regions", type_="unique")

    # Step 7: Add unique constraint on user_id
    op.create_unique_constraint("uq_user_region_user", "user_regions", ["user_id"])

    # Step 8: Drop columns we no longer need
    op.drop_column("user_regions", "region_code")
    op.drop_column("user_regions", "expires_at")
    op.drop_column("user_regions", "status")


def downgrade() -> None:
    # Re-add dropped columns
    op.add_column("user_regions", sa.Column("region_code", sa.String(5), nullable=True))
    op.add_column("user_regions", sa.Column("expires_at", sa.TIMESTAMP, nullable=True))
    op.add_column("user_regions", sa.Column("status", sa.String(20), server_default="active", nullable=True))

    # Best-effort reverse: set region_code = macro_region
    op.execute("""
        UPDATE user_regions SET
            region_code = macro_region,
            status = 'active',
            is_primary = true
    """)

    # Swap constraints back
    op.drop_constraint("uq_user_region_user", "user_regions", type_="unique")
    op.create_unique_constraint("uq_user_region", "user_regions", ["user_id", "region_code"])

    # Drop macro_region
    op.drop_column("user_regions", "macro_region")
