"""Unit tests for the sync-layer liveness wiring (FdmSyncService.
_apply_liveness_gate). Non-DB: the shared Session is mocked and
LivenessGate.gate is patched — this covers the fail-open + rollback contract
that the DB-gated gate() test does not exercise."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.config import settings
from app.services.fdm.fdm_sync_service import FdmSyncService


def _svc(db):
    svc = FdmSyncService.__new__(FdmSyncService)
    svc.db = db
    return svc


def _dep(name="app01"):
    return SimpleNamespace(flux_app_name=name)


def test_disabled_bypasses_gate_and_returns_all_ips():
    svc = _svc(MagicMock())
    with patch.object(settings, "FDM_LIVENESS_ENABLED", False), patch(
        "app.services.fdm.fdm_sync_service.LivenessGate"
    ) as gate_cls:
        out = asyncio.run(svc._apply_liveness_gate(_dep(), ["1.1.1.1", "2.2.2.2"]))
    assert out == ["1.1.1.1", "2.2.2.2"]
    gate_cls.assert_not_called()


def test_excludes_dead_ips():
    svc = _svc(MagicMock())
    with patch.object(settings, "FDM_LIVENESS_ENABLED", True), patch(
        "app.services.fdm.fdm_sync_service.LivenessGate"
    ) as gate_cls:
        gate_cls.return_value.gate = AsyncMock(return_value={"2.2.2.2"})
        out = asyncio.run(svc._apply_liveness_gate(_dep(), ["1.1.1.1", "2.2.2.2"]))
    assert out == ["1.1.1.1"]


def test_fail_open_rolls_back_and_serves_all_ips_on_gate_error():
    db = MagicMock()
    svc = _svc(db)
    with patch.object(settings, "FDM_LIVENESS_ENABLED", True), patch(
        "app.services.fdm.fdm_sync_service.LivenessGate"
    ) as gate_cls:
        gate_cls.return_value.gate = AsyncMock(side_effect=RuntimeError("db boom"))
        out = asyncio.run(svc._apply_liveness_gate(_dep(), ["1.1.1.1", "2.2.2.2"]))
    assert out == ["1.1.1.1", "2.2.2.2"]  # fail-open: unchanged candidate set
    db.rollback.assert_called_once()  # session recovered for the rest of sync
