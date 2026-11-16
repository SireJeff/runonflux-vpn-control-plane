"""Sync-side wiring for Iran reachability (FdmSyncService.
_apply_iran_reach_filter). Non-DB: the Session is mocked and
iran_blocked_ips is patched where fdm_sync_service looks it up."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.services.fdm.fdm_sync_service import FdmSyncService

READER = "app.services.fdm.fdm_sync_service.iran_blocked_ips"
ALL = ["1.1.1.1", "2.2.2.2", "3.3.3.3", "4.4.4.4", "5.5.5.5"]


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    monkeypatch.setattr(settings, "FDM_IRAN_REACH_ENABLED", True)
    monkeypatch.setattr(settings, "FDM_IRAN_REACH_MAX_BLOCKED_FRACTION", 0.5)


def _svc(db=None):
    svc = FdmSyncService.__new__(FdmSyncService)
    svc.db = db or MagicMock()
    return svc


def _dep():
    return SimpleNamespace(flux_app_name="ch01", region="DE")


def test_drops_a_blocked_ip_while_the_region_keeps_others():
    with patch(READER, return_value={"1.1.1.1"}) as reader:
        out = _svc()._apply_iran_reach_filter(_dep(), ALL, ["1.1.1.1", "2.2.2.2"])
    assert out == ["2.2.2.2"]
    reader.assert_called_once()


def test_disabled_returns_targets_without_reading_state(monkeypatch):
    monkeypatch.setattr(settings, "FDM_IRAN_REACH_ENABLED", False)
    with patch(READER) as reader:
        out = _svc()._apply_iran_reach_filter(_dep(), ALL, ["1.1.1.1", "2.2.2.2"])
    assert out == ["1.1.1.1", "2.2.2.2"]
    reader.assert_not_called()


def test_never_empties_a_region():
    # Every IP in the region is blocked: still serve them (useless for Iran,
    # fine elsewhere) rather than leave the region with nothing.
    with patch(READER, return_value={"1.1.1.1", "2.2.2.2"}):
        out = _svc()._apply_iran_reach_filter(_dep(), ALL, ["1.1.1.1", "2.2.2.2"])
    assert out == ["1.1.1.1", "2.2.2.2"]


def test_mass_block_failsafe_excludes_nothing():
    # 3 of the app's 5 IPs "blocked" (> 0.5): more likely check-host's Iranian
    # nodes are broken than Iran blocking most of the fleet at once.
    with patch(READER, return_value={"1.1.1.1", "2.2.2.2", "3.3.3.3"}):
        out = _svc()._apply_iran_reach_filter(_dep(), ALL, ["1.1.1.1", "4.4.4.4"])
    assert out == ["1.1.1.1", "4.4.4.4"]


def test_reader_error_serves_targets_inside_a_savepoint():
    # A full rollback here would expire sync_deployment's uncommitted
    # sync_log counts; the read runs in a SAVEPOINT so only it is undone.
    db = MagicMock()
    with patch(READER, side_effect=RuntimeError("no such table")):
        out = _svc(db)._apply_iran_reach_filter(_dep(), ALL, ["1.1.1.1", "2.2.2.2"])
    assert out == ["1.1.1.1", "2.2.2.2"]
    db.begin_nested.assert_called_once()
    db.rollback.assert_not_called()


def test_empty_targets_pass_through():
    with patch(READER) as reader:
        assert _svc()._apply_iran_reach_filter(_dep(), ALL, []) == []
    reader.assert_not_called()


def test_sync_deployment_filters_after_the_region_filter(monkeypatch):
    """Blocked IPs never reach domain lifecycle / pool sizing, and the filter
    sees the region's IPs (so the never-empty guard is per region)."""
    monkeypatch.setattr(settings, "FDM_LIVENESS_ENABLED", False)
    svc = FdmSyncService(MagicMock())
    dep = MagicMock(id=1, flux_app_name="ch01", region="DE", consecutive_failures=0)
    lifecycle = AsyncMock()
    ensure = MagicMock(return_value=[])
    with patch(READER, return_value={"1.1.1.1"}) as reader, patch.object(
        svc,
        "_discover_instances",
        new_callable=AsyncMock,
        return_value=(ALL, ALL),
    ), patch.object(
        svc,
        "_filter_ips_by_region",
        new_callable=AsyncMock,
        return_value=["1.1.1.1", "2.2.2.2"],
    ), patch.object(
        svc, "_manage_domain_lifecycle", lifecycle
    ), patch.object(
        svc, "_ensure_domains_exist", ensure
    ), patch.object(
        svc, "_inject_spec_gap_into_log", new_callable=MagicMock
    ):
        asyncio.run(svc.sync_deployment(dep))

    assert reader.call_args.args[1:] == ("ch01", ALL)
    lifecycle.assert_awaited_once_with(dep, ["2.2.2.2"])
    assert ensure.call_args.kwargs["healthy_ip_count"] == 1
