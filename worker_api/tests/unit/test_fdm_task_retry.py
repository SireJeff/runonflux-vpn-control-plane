"""Tests that sync_all_deployments task is decorated for retry + acks_late."""
import inspect
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

from tests.unit._fdm_isolated_import import isolated_module_load


def _build_stubs():
    """Build sys.modules stand-ins for fdm_tasks.py's transitive deps so it
    can be loaded without a real DB or app context. Only stubs a dependency
    that isn't already real -- isolated_module_load() applies exactly the
    dict it's given and restores it afterward; this function decides WHICH
    entries need stubbing, matching the file's own prior behavior.
    """
    module_stubs = {}

    if "app" not in sys.modules:
        module_stubs["app"] = types.ModuleType("app")

    if "app.core" not in sys.modules:
        module_stubs["app.core"] = types.ModuleType("app.core")

    if "app.core.database" not in sys.modules:
        db = types.ModuleType("app.core.database")
        db.SessionLocal = MagicMock
        module_stubs["app.core.database"] = db

    if "app.models" not in sys.modules:
        module_stubs["app.models"] = types.ModuleType("app.models")

    if "app.models.fdm" not in sys.modules:
        fdm_m = types.ModuleType("app.models.fdm")
        fdm_m.FdmDeployment = MagicMock
        fdm_m.FdmSyncLog = MagicMock
        module_stubs["app.models.fdm"] = fdm_m

    if "app.services" not in sys.modules:
        services_pkg = types.ModuleType("app.services")
        # __path__ makes this behave as a real package for resolving
        # submodules this file doesn't itself stub (e.g. app.services.flux),
        # instead of shadowing them with a dead end. Pre-existing bug --
        # empirically confirmed to break test_fdm_task_retry.py +
        # test_fdm_sync_tld_generation.py together before this fix.
        services_pkg.__path__ = [
            str(Path(__file__).resolve().parent.parent.parent / "app" / "services")
        ]
        module_stubs["app.services"] = services_pkg

    if "app.services.fdm" not in sys.modules:
        pkg = types.ModuleType("app.services.fdm")
        pkg.__path__ = [
            str(
                Path(__file__).resolve().parent.parent.parent
                / "app"
                / "services"
                / "fdm"
            )
        ]
        module_stubs["app.services.fdm"] = pkg

    return module_stubs


_TASKS_PATH = (
    Path(__file__).resolve().parent.parent.parent / "app" / "tasks" / "fdm_tasks.py"
)
with isolated_module_load(
    "app.tasks.fdm_tasks",
    _TASKS_PATH,
    module_stubs=_build_stubs(),
    attr_stubs={("app.services.fdm", "FdmSyncService"): MagicMock},
) as _mod:
    pass


def test_sync_all_deployments_has_acks_late():
    """Task must have acks_late=True so worker crash -> task re-delivery."""
    task = _mod.sync_all_deployments
    assert (
        task.acks_late is True
    ), "acks_late must be True so worker crashes don't lose tasks"


def test_sync_all_deployments_has_reject_on_worker_lost():
    """Task must reject on worker lost so the task is requeued."""
    task = _mod.sync_all_deployments
    assert task.task_reject_on_worker_lost is True


def test_sync_all_deployments_has_autoretry_for_exception():
    """Task must autoretry on Exception so transient failures don't wait 10 min."""
    task = _mod.sync_all_deployments
    autoretry = task.autoretry_for
    assert autoretry, "autoretry_for must be set"
    assert (
        Exception in autoretry
    ), "autoretry_for must include Exception (transient failures)"


def test_sync_all_deployments_max_retries_at_least_3():
    """Must retry at least 3 times before giving up."""
    task = _mod.sync_all_deployments
    assert task.max_retries >= 3


def test_sync_all_deployments_uses_asyncio_run_not_get_event_loop():
    """Must use asyncio.run() not the deprecated get_event_loop() pattern."""
    src = inspect.getsource(_mod.sync_all_deployments)
    assert "asyncio.run(" in src, "Must use asyncio.run() for fresh event loop"
    assert (
        "asyncio.get_event_loop()" not in src
    ), "Must NOT use deprecated asyncio.get_event_loop() pattern"
