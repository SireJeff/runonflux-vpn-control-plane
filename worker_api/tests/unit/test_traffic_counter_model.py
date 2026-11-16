import pytest


@pytest.mark.database
def test_traffic_counter_unique_key_and_defaults(db_session):
    from app.models.admin_users import AdminUser
    from app.models.admins import Admin
    from app.models.traffic_counters import TrafficCounter

    admin = Admin(username="a1", status="active", password_hash="x")
    db_session.add(admin)
    db_session.flush()
    user = AdminUser(admin_id=admin.id, username="u1", status="active")
    db_session.add(user)
    db_session.flush()

    row = TrafficCounter(
        user_id=user.id,
        protocol="vless",
        instance_id="inst-1",
        last_cumulative_in=10,
        last_cumulative_out=20,
        boot_id="boot-a",
    )
    db_session.add(row)
    db_session.flush()
    assert row.id is not None
    assert row.last_cumulative_in == 10

    dup = TrafficCounter(
        user_id=user.id,
        protocol="vless",
        instance_id="inst-1",
        last_cumulative_in=0,
        last_cumulative_out=0,
        boot_id="boot-a",
    )
    db_session.add(dup)
    with pytest.raises(Exception):
        db_session.flush()
