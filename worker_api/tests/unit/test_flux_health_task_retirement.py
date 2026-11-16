"""Retired legacy tasks must be harmless when delivered from an old queue."""

import asyncio

import pytest

from app.core.celery_config import celery_app
from app.tasks import flux_tasks


@pytest.mark.parametrize(
    "task_name", ["flux.check_all_instances_health", "flux.restart_unhealthy_instances"]
)
def test_beat_does_not_schedule_retired_health_writers(task_name):
    scheduled = {entry["task"] for entry in celery_app.conf.beat_schedule.values()}
    assert task_name not in scheduled
    assert "fdm.sync_all_deployments" in scheduled


@pytest.mark.parametrize(
    "task",
    [flux_tasks.check_all_instances_health, flux_tasks.restart_unhealthy_instances],
)
def test_queued_legacy_task_succeeds_without_db_network_or_event_loop(
    task, monkeypatch
):
    def forbidden(*args, **kwargs):
        raise AssertionError("Retired tasks must not open resources or alter instances")

    monkeypatch.setattr(flux_tasks, "SessionLocal", forbidden)
    monkeypatch.setattr(flux_tasks, "FluxHealthMonitor", forbidden)
    monkeypatch.setattr(asyncio, "get_event_loop", forbidden)
    result = task.apply(throw=True)
    assert result.successful()
    assert result.result == {
        "skipped": "retired",
        "replacement": "fdm.sync_all_deployments",
    }
