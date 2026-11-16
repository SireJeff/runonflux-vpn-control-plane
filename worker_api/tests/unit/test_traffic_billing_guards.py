"""Unit tests for the Layer-1 anti-inflation guards in TrafficBillingService.

Reproduces the confirmed prod root cause (memory
traffic_overbilling_rootcause_2026-07-25): a broken container delta-state
re-sends the whole cumulative counter (or a byte-identical value) every ~62s,
and the backend `traffic_used_bytes +=` over-bills users N-fold.

- test_frozen_repeat_is_suppressed_after_first: the exact prod signature
  (uid 53 vless reported byte-identical 10x) -> only the FIRST is billed.
- test_implausible_report_rejected: a single absurd cumulative dump is dropped.
- test_distinct_deltas_all_bill: real varying deltas are never suppressed.
- test_tiny_identical_reports_not_suppressed: keepalive-sized identical
  reports still bill (harmless, must not be dropped).
"""

import sys
from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.services.billing import traffic_billing_service

_mod = sys.modules["app.services.billing.traffic_billing_service"]
TrafficBillingService = _mod.TrafficBillingService

_GB = 1073741824


class _FakeRedis:
    """Minimal Redis stand-in supporting get/setex/exists used by the guard."""

    def __init__(self):
        self.store = {}

    def get(self, k):
        return self.store.get(k)

    def setex(self, k, ttl, v):
        self.store[k] = v.encode() if isinstance(v, str) else v

    def exists(self, k):
        return k in self.store


def _make_user(
    user_id=10,
    admin_id=5,
    username="alice",
    traffic_used_bytes=0,
    traffic_limit_bytes=100 * _GB,
):
    from app.models.admin_users import AdminUser

    return AdminUser(
        id=user_id,
        admin_id=admin_id,
        username=username,
        status="active",
        traffic_used_bytes=traffic_used_bytes,
        traffic_limit_bytes=traffic_limit_bytes,
    )


def _make_service(mock_db):
    with patch.object(_mod, "WalletService") as MockWallet:
        mock_wallet = MockWallet.return_value
        mock_wallet.debit_wallet.return_value = MagicMock()
        mock_wallet.has_positive_balance.return_value = True
        service = TrafficBillingService(mock_db)
    # Neutralise DB-hitting helpers and alerts.
    service._get_price_per_gb = MagicMock(return_value=Decimal("0.02"))
    service._get_admin_telegram_id = MagicMock(return_value=None)
    return service


def _mock_db_for(user):
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = user
    mock_db.add = MagicMock()
    mock_db.commit = MagicMock()
    return mock_db


@patch.object(_mod, "NotificationRouter")
def test_frozen_repeat_is_suppressed_after_first(MockRouter):
    """Byte-identical consecutive reports (the prod bug) bill exactly once."""
    user = _make_user(traffic_used_bytes=0)
    mock_db = _mock_db_for(user)
    service = _make_service(mock_db)
    fake_redis = _FakeRedis()

    with patch.object(_mod, "get_redis", return_value=fake_redis):
        # Report the exact same 2 GB delta 5 times, as a frozen container would.
        for _ in range(5):
            service.process_traffic_report(
                username="alice",
                protocol="vless",
                region_code="CH",
                bytes_in=0,
                bytes_out=2 * _GB,
                instance_ip="unknown",
                session_duration_seconds=60,
            )

    # Only the first report is billed; the 4 repeats are suppressed.
    assert user.traffic_used_bytes == 2 * _GB


@patch.object(_mod, "NotificationRouter")
def test_implausible_report_rejected(MockRouter):
    """A single absurd cumulative dump (> line-rate ceiling) is dropped."""
    user = _make_user(traffic_used_bytes=0)
    mock_db = _mock_db_for(user)
    service = _make_service(mock_db)
    fake_redis = _FakeRedis()

    with patch.object(_mod, "get_redis", return_value=fake_redis):
        result = service.process_traffic_report(
            username="alice",
            protocol="vless",
            region_code="CH",
            bytes_in=0,
            bytes_out=50 * _GB,
            instance_ip="unknown",
            session_duration_seconds=60,  # 50 GB in 60s >> 7.5 GB ceiling
        )

    assert result["status"] == "rejected_implausible"
    assert user.traffic_used_bytes == 0


@patch.object(_mod, "NotificationRouter")
def test_distinct_deltas_all_bill(MockRouter):
    """Real, varying deltas must never be suppressed."""
    user = _make_user(traffic_used_bytes=0)
    mock_db = _mock_db_for(user)
    service = _make_service(mock_db)
    fake_redis = _FakeRedis()

    deltas = [1 * _GB, (3 * _GB) // 2, 2 * _GB]  # all distinct, all > 1 MB
    with patch.object(_mod, "get_redis", return_value=fake_redis):
        for d in deltas:
            service.process_traffic_report(
                username="alice",
                protocol="vless",
                region_code="CH",
                bytes_in=0,
                bytes_out=d,
                instance_ip="unknown",
                session_duration_seconds=60,
            )

    assert user.traffic_used_bytes == sum(deltas)


@patch.object(_mod, "NotificationRouter")
def test_tiny_identical_reports_not_suppressed(MockRouter):
    """Identical keepalive-sized reports (< dup floor) still bill."""
    user = _make_user(traffic_used_bytes=0)
    mock_db = _mock_db_for(user)
    service = _make_service(mock_db)
    fake_redis = _FakeRedis()

    tiny = 10 * 1024  # 10 KB, below TRAFFIC_DUP_MIN_BYTES (1 MB)
    with patch.object(_mod, "get_redis", return_value=fake_redis):
        for _ in range(3):
            service.process_traffic_report(
                username="alice",
                protocol="vless",
                region_code="CH",
                bytes_in=0,
                bytes_out=tiny,
                instance_ip="unknown",
                session_duration_seconds=60,
            )

    assert user.traffic_used_bytes == 3 * tiny
