"""fdm.check_iran_reachability Celery task body. Registration is guarded by
test_task_registration_complete.py (subprocess) and the beat entry by
test_celery_config_fdm_sync_interval.py (isolated loader)."""

from unittest.mock import AsyncMock, MagicMock, patch

from app.core.config import settings


def test_task_skips_when_disabled(monkeypatch):
    from app.tasks import fdm_tasks

    monkeypatch.setattr(settings, "FDM_IRAN_REACH_ENABLED", False)
    with patch.object(fdm_tasks, "IranReachChecker") as checker:
        out = fdm_tasks.check_iran_reachability()
    assert out == {"skipped": "disabled"}
    checker.assert_not_called()


def test_task_runs_checker_and_closes_session(monkeypatch):
    from app.tasks import fdm_tasks

    monkeypatch.setattr(settings, "FDM_IRAN_REACH_ENABLED", True)
    db = MagicMock()
    summary = {"submitted": ["1.2.3.4:1"], "blocked": [], "restored": []}
    with patch.object(fdm_tasks, "SessionLocal", return_value=db), patch.object(
        fdm_tasks, "IranReachChecker"
    ) as checker:
        checker.return_value.run = AsyncMock(return_value=summary)
        out = fdm_tasks.check_iran_reachability()
    assert out == summary
    checker.assert_called_once_with(db)
    db.close.assert_called_once()


def test_task_swallows_errors_and_rolls_back(monkeypatch):
    from app.tasks import fdm_tasks

    monkeypatch.setattr(settings, "FDM_IRAN_REACH_ENABLED", True)
    db = MagicMock()
    with patch.object(fdm_tasks, "SessionLocal", return_value=db), patch.object(
        fdm_tasks, "IranReachChecker"
    ) as checker:
        checker.return_value.run = AsyncMock(side_effect=RuntimeError("no table"))
        out = fdm_tasks.check_iran_reachability()
    assert out["error"] == "no table"
    db.rollback.assert_called_once()
    db.close.assert_called_once()
