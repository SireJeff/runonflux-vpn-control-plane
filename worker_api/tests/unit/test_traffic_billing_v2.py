import sys
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.services.billing import traffic_billing_service

_mod = sys.modules["app.services.billing.traffic_billing_service"]
TrafficBillingService = _mod.TrafficBillingService
_GB = 1073741824


def _make_user(used=0, limit=100 * _GB):
    from app.models.admin_users import AdminUser

    return AdminUser(
        id=10,
        admin_id=5,
        username="alice",
        status="active",
        traffic_used_bytes=used,
        traffic_limit_bytes=limit,
    )


def _service(user, counter_row):
    """Build service with mocked wallet + a db whose TrafficCounter lookup
    returns `counter_row` (None = first sight) and AdminUser lookup returns user."""
    mock_db = MagicMock()

    def _query(model):
        q = MagicMock()
        name = getattr(model, "__name__", str(model))
        if name == "AdminUser":
            q.filter.return_value.first.return_value = user
        elif name == "TrafficCounter":
            q.filter.return_value.first.return_value = counter_row
        else:
            q.filter.return_value.first.return_value = None
        return q

    mock_db.query.side_effect = _query
    mock_db.add = MagicMock()
    mock_db.commit = MagicMock()
    with patch.object(_mod, "WalletService") as MockWallet:
        mw = MockWallet.return_value
        mw.debit_wallet.return_value = MagicMock()
        mw.has_positive_balance.return_value = True
        svc = TrafficBillingService(mock_db)
    svc._get_price_per_gb = MagicMock(return_value=Decimal("0.02"))
    svc._get_admin_telegram_id = MagicMock(return_value=None)
    return svc, mock_db


def _report(svc, cumulative_in, cumulative_out, boot_id="b1"):
    with patch.object(_mod, "NotificationRouter"), patch.object(
        _mod, "get_redis", return_value=None
    ):
        return svc.process_traffic_report(
            username="alice",
            protocol="vless",
            region_code="CH",
            bytes_in=0,
            bytes_out=0,
            instance_ip="unknown",
            report_version=2,
            cumulative_in=cumulative_in,
            cumulative_out=cumulative_out,
            boot_id=boot_id,
            instance_id="inst-1",
        )


@pytest.mark.database
def test_apply_cumulative_multi_replica_boot_ids_dont_collide(db_session):
    """Two Flux replicas (same user/protocol/instance_id, DIFFERENT boot_id) each
    keep their own counter row and never reset/thrash each other. This is the
    real ch01 topology (5 replicas per protocol sharing one FLUXVPN_INSTANCE_ID)."""
    from app.models.admin_users import AdminUser
    from app.models.admins import Admin
    from app.models.traffic_counters import TrafficCounter

    admin = Admin(username="a1", status="active", password_hash="x")
    db_session.add(admin)
    db_session.flush()
    user = AdminUser(admin_id=admin.id, username="u1", status="active")
    db_session.add(user)
    db_session.flush()

    svc = TrafficBillingService(db_session)

    # Replica A first report: bills full since-boot cumulative (100).
    d = svc._apply_cumulative_report(user.id, "vless", "app1", 100, 0, "bootA")
    db_session.flush()
    assert d == 100
    # Replica B first report: independent row, bills 50 (NOT a reset of A).
    d = svc._apply_cumulative_report(user.id, "vless", "app1", 50, 0, "bootB")
    db_session.flush()
    assert d == 50
    # Replica A again: incremental 150-100 = 50 (B did not disturb A's baseline).
    d = svc._apply_cumulative_report(user.id, "vless", "app1", 150, 0, "bootA")
    db_session.flush()
    assert d == 50
    # Replica B again: incremental 80-50 = 30.
    d = svc._apply_cumulative_report(user.id, "vless", "app1", 80, 0, "bootB")
    db_session.flush()
    assert d == 30

    # Exactly two rows exist (one per boot_id), not one thrashed row.
    rows = (
        db_session.query(TrafficCounter)
        .filter_by(
            user_id=user.id,
            protocol="vless",
            instance_id="app1",
        )
        .all()
    )
    assert len(rows) == 2
    assert {r.boot_id for r in rows} == {"bootA", "bootB"}


def test_v2_first_sight_bills_full_cumulative():
    user = _make_user(used=0)
    svc, _ = _service(user, counter_row=None)
    _report(svc, cumulative_in=1_000_000, cumulative_out=2_000_000)
    assert user.traffic_used_bytes == 3_000_000


def test_v2_steady_creep_bills_second_difference():
    from app.models.traffic_counters import TrafficCounter

    row = TrafficCounter(
        user_id=10,
        protocol="vless",
        instance_id="inst-1",
        last_cumulative_in=5_000_000,
        last_cumulative_out=448_000_000,
        boot_id="b1",
    )
    user = _make_user(used=0)
    svc, _ = _service(user, counter_row=row)
    # cumulative crept up by 62,000 total -> only that is billed
    _report(svc, cumulative_in=5_010_000, cumulative_out=448_052_000)
    assert user.traffic_used_bytes == (10_000 + 52_000)


def test_v2_frozen_counter_bills_zero():
    from app.models.traffic_counters import TrafficCounter

    row = TrafficCounter(
        user_id=10,
        protocol="vless",
        instance_id="inst-1",
        last_cumulative_in=2_113_261,
        last_cumulative_out=660_348_132,
        boot_id="b1",
    )
    user = _make_user(used=0)
    svc, _ = _service(user, counter_row=row)
    _report(svc, cumulative_in=2_113_261, cumulative_out=660_348_132)
    assert user.traffic_used_bytes == 0


def test_v2_container_restart_bootid_change_bills_full():
    from app.models.traffic_counters import TrafficCounter

    row = TrafficCounter(
        user_id=10,
        protocol="vless",
        instance_id="inst-1",
        last_cumulative_in=9_000_000,
        last_cumulative_out=9_000_000,
        boot_id="OLD",
    )
    user = _make_user(used=0)
    svc, _ = _service(user, counter_row=row)
    # new boot_id + counter reset to small values
    _report(svc, cumulative_in=1000, cumulative_out=2000, boot_id="NEW")
    assert user.traffic_used_bytes == 3000


def test_v2_xray_reset_cumulative_below_last_bills_full():
    from app.models.traffic_counters import TrafficCounter

    row = TrafficCounter(
        user_id=10,
        protocol="vless",
        instance_id="inst-1",
        last_cumulative_in=9_000_000,
        last_cumulative_out=9_000_000,
        boot_id="b1",
    )
    user = _make_user(used=0)
    svc, _ = _service(user, counter_row=row)
    # same boot_id but counter dropped (xray process restarted in-place)
    _report(svc, cumulative_in=500, cumulative_out=1000, boot_id="b1")
    assert user.traffic_used_bytes == 1500


def test_v2_asymmetric_reset_bills_only_reset_direction():
    from app.models.traffic_counters import TrafficCounter

    row = TrafficCounter(
        user_id=10,
        protocol="vless",
        instance_id="inst-1",
        last_cumulative_in=9_000_000,
        last_cumulative_out=50_000_000,
        boot_id="b1",
    )
    user = _make_user(used=0)
    svc, _ = _service(user, counter_row=row)
    # same boot_id; cumulative_in DIPPED (that direction reset) -> delta_in=100;
    # cumulative_out grew normally by 52_000 -> delta_out=52_000. Must NOT bill
    # the full 50_052_000 out-total.
    _report(svc, cumulative_in=100, cumulative_out=50_052_000, boot_id="b1")
    assert user.traffic_used_bytes == (100 + 52_000)


def test_v2_suspended_user_advances_baseline_without_billing():
    from app.models.traffic_counters import TrafficCounter

    # user is suspended; counter last-seen at 1_000_000/1_000_000
    row = TrafficCounter(
        user_id=10,
        protocol="vless",
        instance_id="inst-1",
        last_cumulative_in=1_000_000,
        last_cumulative_out=1_000_000,
        boot_id="b1",
    )
    user = _make_user(used=0)
    user.status = "suspended"
    svc, _ = _service(user, counter_row=row)
    # a report arrives while suspended: counter grew a lot (e.g. SSH kept counting)
    res = _report(svc, cumulative_in=1_000_000, cumulative_out=9_000_000, boot_id="b1")
    assert res["status"] == "skipped"
    assert user.traffic_used_bytes == 0  # nothing billed while suspended
    assert row.last_cumulative_out == 9_000_000  # baseline advanced
