"""Guard: every Celery task the app defines (and every task the beat schedule
names) must actually be registered with the production Celery app.

Why a subprocess: importing the real ``app.core.celery_config`` runs
``celery_app.autodiscover_tasks(["app"])`` and constructs a real
``celery.Celery`` app. ``test_celery_config_fdm_sync_interval.py`` documents
(at length, empirically) that doing this in the pytest process corrupts
Celery's global app/registry state and breaks sibling tests collected in the
same run. So the real import happens ONLY in the ``__main__`` block below,
which runs in a fresh interpreter spawned by ``_run_report()``. The pytest
process itself imports nothing but stdlib + pytest.

The bug this guards against has recurred three times in 8 months: a new task
module (flux_tasks 2025-11, node_tasks 2026-02, tld_analytics 2026-06) was
added to disk but never added to ``app/tasks/__init__.py``'s import list, so
``autodiscover_tasks(["app"])`` (which only imports that one ``__init__``)
never registered its tasks, and every ``beat_schedule`` entry pointing at
them failed each cycle with "Received unregistered task".
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# tests/unit/<this file> -> parents[2] == worker_api (where ``app`` is importable)
_WORKER_API_ROOT = Path(__file__).resolve().parents[2]


def _run_report():
    """Spawn a fresh interpreter that imports the real Celery app and prints a
    JSON registration report. Isolation guarantees the parent pytest process
    never touches real Celery global state."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_WORKER_API_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve())],
        cwd=str(_WORKER_API_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, (
        "registration-report subprocess failed (rc=%s)\n--- stdout ---\n%s\n"
        "--- stderr ---\n%s" % (proc.returncode, proc.stdout, proc.stderr)
    )
    # The report is the last non-empty stdout line (import-time logging may
    # precede it).
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    assert lines, "subprocess produced no stdout\n--- stderr ---\n%s" % proc.stderr
    return json.loads(lines[-1])


@pytest.fixture(scope="module")
def registration_report():
    return _run_report()


def test_all_defined_tasks_are_registered(registration_report):
    registered = set(registration_report["registered"])
    defined = set(registration_report["defined"])
    missing = sorted(defined - registered)
    assert not missing, (
        "%d task(s) are defined under app/tasks/ but NOT registered with "
        "celery_app -- their module is almost certainly missing from "
        "app/tasks/__init__.py's import list:\n  %s"
        % (len(missing), "\n  ".join(missing))
    )


def test_all_scheduled_tasks_are_registered(registration_report):
    registered = set(registration_report["registered"])
    scheduled = set(registration_report["scheduled"])
    missing = sorted(scheduled - registered)
    assert not missing, (
        "%d beat_schedule task(s) name a task that is NOT registered with "
        "celery_app -- either the task is unimported (fix __init__.py) or the "
        "schedule entry is dead and should be removed:\n  %s"
        % (len(missing), "\n  ".join(missing))
    )


if __name__ == "__main__":
    # Runs ONLY in the spawned subprocess. Safe to touch real Celery here.
    import importlib

    import app.core.celery_config as cc

    # Reproduce the worker's registration path. autodiscover_tasks(["app"]) is
    # LAZY -- it schedules ``import app.tasks`` for finalize time, which is too
    # late for the @shared_task finalizers to be registered in that same pass.
    # Import app.tasks explicitly FIRST (running __init__.py's import list, the
    # exact thing production registration depends on), THEN finalize so those
    # finalizers actually run and ``registered`` reflects the true production
    # set. Without this, celery_app.tasks comes back with zero app tasks.
    import app.tasks  # noqa: F401  -- side effect: runs __init__ import list

    cc.celery_app.finalize()
    registered = sorted(cc.celery_app.tasks.keys())

    # Independently discover every task DEFINED on disk, bypassing __init__.py:
    # import each app/tasks/*.py directly and collect objects that quack like a
    # Celery task (have a string ``.name`` and a callable ``.delay``). This
    # covers @shared_task, @shared_task(...), and @celery_app.task(...) alike.
    tasks_dir = Path(cc.__file__).resolve().parents[1] / "tasks"  # app/tasks
    defined = set()
    for pyfile in sorted(tasks_dir.glob("*.py")):
        if pyfile.name == "__init__.py":
            continue
        module = importlib.import_module("app.tasks." + pyfile.stem)
        for value in vars(module).values():
            name = getattr(value, "name", None)
            if isinstance(name, str) and callable(getattr(value, "delay", None)):
                defined.add(name)

    scheduled = sorted(
        entry["task"] for entry in cc.celery_app.conf.beat_schedule.values()
    )

    print(
        json.dumps(
            {
                "registered": registered,
                "defined": sorted(defined),
                "scheduled": scheduled,
            }
        )
    )
