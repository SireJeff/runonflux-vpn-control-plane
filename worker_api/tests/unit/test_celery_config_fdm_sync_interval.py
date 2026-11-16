"""Phase 4.5: FDM beat schedule reads FDM_SYNC_INTERVAL_SECONDS from settings.

celery_config.py builds `celery_app.conf.beat_schedule` once at import time
from the module-level `settings` singleton. Reloading the REAL
`app.core.celery_config` module in-place (via importlib.reload) would leave
the shared module object mutated for the rest of the pytest process — any
later test or app code importing `celery_app` would see this test's
patched value. Instead, load a private, isolated copy of the file under a
throwaway sys.modules key per case, mirroring this project's carried-
forward test lesson (test_fdm_sync_lifecycle.py's importlib dodge): patch
the bound object, never a string path, and never leave a shared module in
a test-mutated state.

Constructing a real `celery.Celery(...)` app (as celery_config.py's top
level does) touches Celery's own global app registry/current-app state,
and calling its `autodiscover_tasks(["app"])` (the file's last line)
imports every task module in the app package as a side effect. Confirmed
empirically: re-executing the real file under a throwaway module name (even
with `autodiscover_tasks` patched to a no-op) still corrupts state shared
with tests collected in the same pytest process — test_fdm_sync_dns_rightsize_tld.py
fails when collected alongside this file, passes cleanly alone. The fix is
to never construct a real Celery app during the isolated exec at all:
substitute a minimal fake for `celery.Celery` (just enough surface —
`.conf` accepts attribute assignment, `.conf.update(**kw)` and
`.autodiscover_tasks(...)` are no-ops) so the file's `beat_schedule` dict —
the only thing this test cares about — still gets built correctly, with
zero real Celery machinery touched.
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

from app.core.config import settings

_MOD_PATH = (
    Path(__file__).resolve().parent.parent.parent / "app" / "core" / "celery_config.py"
)


class _FakeConf:
    def update(self, **kwargs):
        pass


class _FakeCeleryApp:
    def __init__(self, *args, **kwargs):
        self.conf = _FakeConf()

    def autodiscover_tasks(self, *args, **kwargs):
        pass


def _load_isolated_celery_config():
    spec = importlib.util.spec_from_file_location(
        "app.core.celery_config_test_isolated",
        str(_MOD_PATH),
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["app.core.celery_config_test_isolated"] = mod
    with patch("celery.Celery", _FakeCeleryApp):
        spec.loader.exec_module(mod)
    return mod


def test_fdm_schedule_uses_configured_interval(monkeypatch):
    monkeypatch.setattr(settings, "FDM_SYNC_INTERVAL_SECONDS", 900.0)
    mod = _load_isolated_celery_config()
    entry = mod.celery_app.conf.beat_schedule["fdm.sync_all_deployments"]
    assert entry["schedule"] == 900.0


def test_fdm_schedule_defaults_to_600_when_unset():
    mod = _load_isolated_celery_config()
    entry = mod.celery_app.conf.beat_schedule["fdm.sync_all_deployments"]
    assert entry["schedule"] == 600.0


def test_iran_reachability_check_runs_on_the_fdm_queue(monkeypatch):
    monkeypatch.setattr(settings, "FDM_IRAN_REACH_RUN_INTERVAL", 1200.0)
    mod = _load_isolated_celery_config()
    entry = mod.celery_app.conf.beat_schedule["fdm.check_iran_reachability"]
    assert entry["task"] == "fdm.check_iran_reachability"
    assert entry["options"]["queue"] == "fdm"
    assert entry["schedule"] == 1200.0
