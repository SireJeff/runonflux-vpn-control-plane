from datetime import datetime, timedelta, timezone

import pytest

from app.api.v1.endpoints.admin import (
    SystemSettingsUpdate,
    get_system_logs,
    get_system_settings,
    update_system_settings,
)
from app.models import (
    AuthLog,
    ConnectionLog,
    Protocol,
    ProtocolInstance,
    SystemSettings,
)


@pytest.mark.asyncio
async def test_settings_support_decimal_commission_values(db, test_admin_user):
    updated = await update_system_settings(
        SystemSettingsUpdate(
            trial_days=3,
            referral_commission_bronze=12.5,
            referral_commission_silver=17.25,
            referral_commission_gold=21.75,
            referral_commission_platinum=33.33,
            max_ip_changes_per_month=3,
        ),
        admin=test_admin_user,
        db=db,
    )

    assert updated.referral_commission_bronze == 12.5
    assert updated.referral_commission_silver == 17.25
    assert updated.referral_commission_gold == 21.75
    assert updated.referral_commission_platinum == 33.33

    stored = db.query(SystemSettings).filter(SystemSettings.id == 1).first()
    assert stored is not None
    assert float(stored.referral_commission_bronze) == 12.5
    assert float(stored.referral_commission_platinum) == 33.33

    loaded = await get_system_settings(admin=test_admin_user, db=db)
    assert loaded.referral_commission_gold == 21.75


@pytest.mark.asyncio
async def test_system_logs_apply_search_source_and_date_filters(
    db, test_admin_user, test_user
):
    protocol = Protocol(
        name="ssh",
        slug="ssh",
        display_name="SSH",
        description="SSH protocol",
        flux_app_name="fluxvpn-ssh",
        default_port=22,
        is_active=True,
    )
    db.add(protocol)
    db.commit()
    db.refresh(protocol)

    instance = ProtocolInstance(
        protocol_id=protocol.id,
        flux_app_name="vpnfluxUSE01",
        component_name="ssh",
        instance_number=1,
        ip_address="127.0.0.1",
        country_code="US",
        country_name="United States",
        health_status="healthy",
        is_active=True,
    )
    db.add(instance)
    db.commit()
    db.refresh(instance)

    old_conn = ConnectionLog(
        id=1,
        user_id=test_user.id,
        protocol_id=protocol.id,
        instance_id=instance.id,
        connected_at=datetime.now(timezone.utc).replace(tzinfo=None)
        - timedelta(days=10),
    )
    recent_auth = AuthLog(
        id=2,
        user_id=test_user.id,
        event_type="login",
        success=False,
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )

    db.add(old_conn)
    db.add(recent_auth)
    db.commit()

    failed_only = await get_system_logs(
        admin=test_admin_user,
        db=db,
        search="failed",
        limit=100,
    )
    assert len(failed_only) == 1
    assert failed_only[0].source == "auth"

    auth_only = await get_system_logs(
        admin=test_admin_user,
        db=db,
        source="auth",
        limit=100,
    )
    assert len(auth_only) == 1
    assert auth_only[0].source == "auth"

    today = datetime.now(timezone.utc).replace(tzinfo=None).date().isoformat()
    today_logs = await get_system_logs(
        admin=test_admin_user,
        db=db,
        start_date=today,
        limit=100,
    )
    assert len(today_logs) == 1
    assert today_logs[0].source == "auth"


@pytest.mark.asyncio
async def test_system_settings_read_and_update_target_singleton_id_1(
    db, test_admin_user
):
    # Seed two rows to ensure API always targets singleton row id=1
    db.add(
        SystemSettings(
            id=1,
            trial_days=3,
            referral_commission_bronze=5.0,
            referral_commission_silver=10.0,
            referral_commission_gold=15.0,
            referral_commission_platinum=20.0,
            maintenance_mode=False,
            max_ip_changes_per_month=3,
        )
    )
    db.add(
        SystemSettings(
            id=2,
            trial_days=9,
            referral_commission_bronze=9.0,
            referral_commission_silver=19.0,
            referral_commission_gold=29.0,
            referral_commission_platinum=39.0,
            maintenance_mode=True,
            max_ip_changes_per_month=9,
        )
    )
    db.commit()

    updated = await update_system_settings(
        SystemSettingsUpdate(
            trial_days=7,
            referral_commission_bronze=5.0,
            referral_commission_silver=10.0,
            referral_commission_gold=15.0,
            referral_commission_platinum=20.0,
            maintenance_mode=True,
            max_ip_changes_per_month=3,
        ),
        admin=test_admin_user,
        db=db,
    )

    assert updated.trial_days == 7
    assert updated.maintenance_mode is True

    row1 = db.query(SystemSettings).filter(SystemSettings.id == 1).first()
    row2 = db.query(SystemSettings).filter(SystemSettings.id == 2).first()

    assert row1 is not None
    assert row1.trial_days == 7
    assert row2 is not None
    assert row2.trial_days == 9

    loaded = await get_system_settings(admin=test_admin_user, db=db)
    assert loaded.trial_days == 7
