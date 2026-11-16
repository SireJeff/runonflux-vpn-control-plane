"""Reseller platform tables

Revision ID: 20260530_002
Revises: 20260530_001
Create Date: 2026-05-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '20260530_002'
down_revision = '20260530_001'
branch_labels = None
depends_on = None


def upgrade():
    # 1. admins table
    op.create_table(
        'admins',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('username', sa.String(50), unique=True, nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('display_name', sa.String(100), nullable=True),
        sa.Column('telegram_id', sa.String(50), nullable=True),
        sa.Column('whatsapp_number', sa.String(20), nullable=True),
        sa.Column('phone_number', sa.String(20), nullable=True),
        sa.Column('wallet_balance', sa.Numeric(12, 2), server_default='0.00'),
        sa.Column('status', sa.String(20), server_default='pending'),
        sa.Column('assigned_password', sa.String(255), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('approved_by', sa.Integer(), sa.ForeignKey('admins.id'), nullable=True),
        sa.Column('approved_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.func.current_timestamp()),
    )
    op.create_index('ix_admins_username', 'admins', ['username'])

    # 2. admin_users table
    op.create_table(
        'admin_users',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('admin_id', sa.Integer(), sa.ForeignKey('admins.id', ondelete='CASCADE'), nullable=False),
        sa.Column('username', sa.String(50), nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=True),
        sa.Column('display_name', sa.String(100), nullable=True),
        sa.Column('remark', sa.Text(), nullable=True),
        sa.Column('status', sa.String(20), server_default='active'),
        sa.Column('traffic_used_bytes', sa.BigInteger(), server_default='0'),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint('admin_id', 'username', name='uq_admin_user'),
    )
    op.create_index('ix_admin_users_admin_id', 'admin_users', ['admin_id'])

    # 3. user_credentials_v2 table
    op.create_table(
        'user_credentials_v2',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('admin_users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('protocol', sa.String(20), nullable=False),
        sa.Column('credential_data', JSONB(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint('user_id', 'protocol', name='uq_user_protocol'),
    )
    op.create_index('ix_user_credentials_v2_user_id', 'user_credentials_v2', ['user_id'])

    # 4. user_regions table
    op.create_table(
        'user_regions',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('admin_users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('region_code', sa.String(5), nullable=False),
        sa.Column('is_primary', sa.Boolean(), server_default='false'),
        sa.Column('activated_at', sa.TIMESTAMP(), server_default=sa.func.current_timestamp()),
        sa.Column('expires_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('status', sa.String(20), server_default='active'),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint('user_id', 'region_code', name='uq_user_region'),
    )
    op.create_index('ix_user_regions_user_id', 'user_regions', ['user_id'])

    # 5. traffic_logs table
    op.create_table(
        'traffic_logs',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('admin_users.id'), nullable=False),
        sa.Column('admin_id', sa.Integer(), sa.ForeignKey('admins.id'), nullable=False),
        sa.Column('protocol', sa.String(20), nullable=False),
        sa.Column('region_code', sa.String(5), nullable=False),
        sa.Column('bytes_in', sa.BigInteger(), server_default='0'),
        sa.Column('bytes_out', sa.BigInteger(), server_default='0'),
        sa.Column('session_started_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('session_ended_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('instance_ip', sa.String(45), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.current_timestamp()),
    )
    op.create_index('idx_traffic_logs_user_id', 'traffic_logs', ['user_id'])
    op.create_index('idx_traffic_logs_admin_id', 'traffic_logs', ['admin_id'])
    op.create_index('idx_traffic_logs_created_at', 'traffic_logs', ['created_at'])

    # 6. wire_orders table
    op.create_table(
        'wire_orders',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('admin_id', sa.Integer(), sa.ForeignKey('admins.id'), nullable=False),
        sa.Column('amount_tomans', sa.Numeric(12, 2), nullable=False),
        sa.Column('amount_usd', sa.Numeric(12, 2), nullable=True),
        sa.Column('contact_telegram', sa.String(50), nullable=False),
        sa.Column('contact_whatsapp', sa.String(20), nullable=True),
        sa.Column('contact_phone', sa.String(20), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('status', sa.String(20), server_default='pending'),
        sa.Column('admin_notes', sa.Text(), nullable=True),
        sa.Column('reviewed_by', sa.Integer(), sa.ForeignKey('admins.id'), nullable=True),
        sa.Column('reviewed_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.current_timestamp()),
    )
    op.create_index('ix_wire_orders_admin_id', 'wire_orders', ['admin_id'])

    # 7. platform_settings table
    op.create_table(
        'platform_settings',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('key', sa.String(100), unique=True, nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.func.current_timestamp()),
    )

    # Seed default platform settings
    op.execute("""
        INSERT INTO platform_settings (key, value) VALUES
        ('price_per_gb', '0.02'),
        ('price_per_region_monthly', '2.00'),
        ('min_topup_tomans', '500000'),
        ('toman_to_usd_rate', '0.0000167')
        ON CONFLICT (key) DO NOTHING;
    """)


def downgrade():
    op.drop_table('platform_settings')
    op.drop_table('wire_orders')
    op.drop_table('traffic_logs')
    op.drop_table('user_regions')
    op.drop_table('user_credentials_v2')
    op.drop_table('admin_users')
    op.drop_table('admins')
