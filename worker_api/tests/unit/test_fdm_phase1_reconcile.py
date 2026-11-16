"""Phase 1 tests: scoped reconcile_app + prune grace/app filter."""
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import app.services.fdm.fdm_sync_service  # noqa: F401  (cold-import dodge)
from tests.unit._fdm_isolated_import import isolated_module_load

_MOD_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "app"
    / "services"
    / "fdm"
    / "fdm_sync_service.py"
)
with isolated_module_load("app.services.fdm.fdm_sync_service", _MOD_PATH) as _mod:
    FdmSyncService = _mod.FdmSyncService


def _run(coro):
    return asyncio.run(coro)


def _make_deployment(
    id=1, flux_app_name="ch01", region="CH", is_active=True, consecutive_failures=0
):
    d = MagicMock()
    d.id = id
    d.flux_app_name = flux_app_name
    d.region = region
    d.is_active = is_active
    d.consecutive_failures = consecutive_failures
    d.base_domain = "operator4.example.invalid"
    d.protocol_name = None
    return d


def _make_domain(
    id=1,
    deployment_id=1,
    domain_name="cdn-01.operator4.example.invalid",
    dns_record_id="rec1",
    updated_at=None,
):
    d = MagicMock()
    d.id = id
    d.deployment_id = deployment_id
    d.domain_name = domain_name
    d.dns_record_id = dns_record_id
    d.tld_id = None
    d.updated_at = updated_at  # None => treated as stale
    return d


# --- reconcile_app: inactive app prunes immediately, no grace ---


def test_reconcile_app_inactive_prunes_immediately():
    """Deactivating an app via operator action must prune DNS with grace=0
    (no 30-min wait). reconcile_app scopes the prune to that app."""
    dep = _make_deployment(id=7, flux_app_name="na01", region="US", is_active=False)
    dom = _make_domain(id=3, deployment_id=7)

    mock_db = MagicMock()
    # FluxAppRegistration lookup -> inactive app
    reg_q = MagicMock()
    reg_q.filter.return_value.first.return_value = MagicMock(is_active=False)
    # FdmDeployment lookup -> [dep]
    dep_q = MagicMock()
    dep_q.filter.return_value.all.return_value = [dep]
    # FdmDomain orphan lookup -> [dom]
    dom_q = MagicMock()
    # reconcile_app's app_name branch chains a SECOND .filter() onto the orphan
    # query, so make .filter() idempotent: any number of filters stays on the
    # same node whose .all() returns [dom].
    _filtered = dom_q.join.return_value.filter.return_value
    _filtered.filter.return_value = _filtered
    _filtered.all.return_value = [dom]

    def query(model):
        name = getattr(model, "__name__", str(model))
        if "FluxAppRegistration" in name:
            return reg_q
        if "FdmDeployment" in name:
            return dep_q
        return dom_q

    mock_db.query.side_effect = query

    service = FdmSyncService(mock_db)
    with patch.object(
        FdmSyncService, "_delete_dns_record_for_domain", new_callable=AsyncMock
    ) as mock_del:
        result = _run(service.reconcile_app("na01"))

    assert result["active"] is False
    assert result["pruned"] == 1
    mock_del.assert_awaited_once_with(dom)
    mock_db.delete.assert_called_once_with(dom)
    mock_db.commit.assert_called()


# --- reconcile_app: active app resets failures + syncs ---


def test_reconcile_app_active_resets_failures_and_syncs():
    """Reactivating an app resets consecutive_failures (so a former phantom
    doesn't immediately re-deactivate) and runs one sync per deployment."""
    dep = _make_deployment(
        id=7, flux_app_name="na01", region="US", is_active=True, consecutive_failures=3
    )

    mock_db = MagicMock()
    reg_q = MagicMock()
    reg_q.filter.return_value.first.return_value = MagicMock(is_active=True)
    dep_q = MagicMock()
    dep_q.filter.return_value.all.return_value = [dep]

    def query(model):
        name = getattr(model, "__name__", str(model))
        return reg_q if "FluxAppRegistration" in name else dep_q

    mock_db.query.side_effect = query

    service = FdmSyncService(mock_db)
    fake_log = MagicMock(status="success")
    with patch.object(
        FdmSyncService, "sync_deployment", new_callable=AsyncMock, return_value=fake_log
    ):
        result = _run(service.reconcile_app("na01"))

    assert dep.consecutive_failures == 0, "reactivation must reset failure counter"
    assert dep.is_active is True
    assert result["active"] is True
    assert result["synced"]["na01:US"] == "success"


# --- _prune_inactive_deployment_domains: grace + app_name filter ---


def test_prune_respects_zero_grace():
    """grace_minutes=0 means even domains touched 'now' are pruned (operator action)."""
    from datetime import datetime, timezone

    fresh = _make_domain(id=1, updated_at=datetime.now(timezone.utc))
    mock_db = MagicMock()
    mock_db.query.return_value.join.return_value.filter.return_value.all.return_value = [
        fresh
    ]
    service = FdmSyncService(mock_db)
    with patch.object(
        FdmSyncService, "_delete_dns_record_for_domain", new_callable=AsyncMock
    ):
        pruned = _run(service._prune_inactive_deployment_domains(grace_minutes=0))
    assert pruned == 1


def test_prune_app_filter_limits_scope():
    """app_name scopes the orphan query to one app's deployments. The impl
    chains a SECOND .filter() (flux_app_name) after the base is_active==False
    filter; this test asserts that scoping filter is invoked. Hardened from a
    vacuous no-op that passed via MagicMock's empty __iter__ default."""
    mock_db = MagicMock()
    # chain = return_value of the FIRST .filter() (is_active==False)
    chain = mock_db.query.return_value.join.return_value.filter.return_value
    chain.filter.return_value.all.return_value = []  # full double-filter chain -> []
    service = FdmSyncService(mock_db)
    _run(service._prune_inactive_deployment_domains(app_name="na01"))

    # The app_name arg MUST drive a second .filter() (the scoping filter).
    chain.filter.assert_called_once()
    # Empty result -> no prune, no commit.
    mock_db.commit.assert_not_called()


# --- fdm.reconcile_app Celery task ---


def test_reconcile_app_task_invokes_service():
    """The Celery task thin-wraps FdmSyncService.reconcile_app under asyncio.run."""
    import inspect

    from app.tasks import fdm_tasks

    src = inspect.getsource(fdm_tasks)
    assert "def reconcile_app" in src, "fdm.reconcile_app task must exist"
    assert (
        "FdmSyncService" in src and "reconcile_app" in src
    ), "task must call FdmSyncService.reconcile_app"
    # Must use asyncio.run (the modern pattern), not get_event_loop
    task_src = src[src.find("def reconcile_app") :]
    assert "asyncio.run(" in task_src, "task must use asyncio.run"


# --- update_app enqueues scoped reconcile on is_active change ---


def test_update_app_enqueues_reconcile_on_toggle():
    """Toggling is_active must enqueue fdm.reconcile_app so DNS is reconciled
    immediately (no 40-min wait for the beat + grace)."""
    import inspect

    from app.api.v1.endpoints import super_admin

    src = inspect.getsource(super_admin.update_app)
    assert (
        "reconcile_app" in src
    ), "update_app must enqueue reconcile_app on is_active change"
    assert ".delay(" in src, "must enqueue via .delay()"
    # And it must be conditional on the is_active branch
    is_active_pos = src.find("request.is_active is not None")
    reconcile_pos = src.find("reconcile_app")
    assert (
        reconcile_pos > is_active_pos
    ), "reconcile enqueue must be within the is_active branch"


# --- delete_app cleans DNS records + deactivates ProtocolInstances ---


def test_delete_app_cleans_dns_and_deactivates_pi():
    """DELETE must not orphan DNS A-records: it calls _delete_dns_record_for_domain
    per domain before deleting rows, and deactivates the app's ProtocolInstances."""
    import inspect

    from app.api.v1.endpoints import super_admin

    src = inspect.getsource(super_admin.delete_app)
    assert (
        "_delete_dns_record_for_domain" in src
    ), "delete_app must delete each domain's DNS record (mirror delete_tld)"
    assert "ProtocolInstance" in src, "delete_app must deactivate ProtocolInstances"
    # The DNS cleanup must happen BEFORE the bulk domain delete
    cleanup_pos = src.find("_delete_dns_record_for_domain")
    bulk_delete_pos = src.find(".delete(synchronize_session=False)")
    assert cleanup_pos < bulk_delete_pos, "DNS cleanup must precede row deletion"


# --- list_apps derived `serving` flag ---


def test_list_apps_exposes_serving_flag():
    """list_apps must derive a `serving` flag = app active AND has a healthy
    domain under an ACTIVE deployment (so a phantom-deactivated app no longer
    falsely reads healthy).

    Phase 4.7a: the derivation moved into the shared _compute_app_health
    helper (list_apps/get_app previously duplicated this block verbatim) --
    check the helper's source for the is_active consideration, and
    list_apps's own source for calling it and exposing a `serving` value."""
    import inspect

    from app.api.v1.endpoints import super_admin

    src = inspect.getsource(super_admin.list_apps)
    assert "serving" in src, "list_apps must expose a `serving` value"
    assert "_compute_app_health" in src, "list_apps must use the shared helper"
    helper_src = inspect.getsource(super_admin._compute_app_health)
    assert (
        "FdmDeployment.is_active" in helper_src or "is_active == True" in helper_src
    ), "serving must consider deployment active-state, not just healthy domain count"


def test_app_registration_response_has_serving_field():
    """The response schema must expose `serving: bool`."""
    # Schema may be defined in super_admin.py or app/schemas/. Search both.
    import importlib
    import inspect

    from app.api.v1.endpoints import super_admin

    found = False
    for mod_path in ("app.api.v1.endpoints.super_admin", "app.schemas.super_admin"):
        try:
            mod = importlib.import_module(mod_path)
        except Exception:
            continue
        if hasattr(mod, "AppRegistrationResponse"):
            fields = mod.AppRegistrationResponse.model_fields
            assert (
                "serving" in fields
            ), f"AppRegistrationResponse must have a `serving` field (in {mod_path})"
            found = True
    assert found, "AppRegistrationResponse not found in expected modules"
