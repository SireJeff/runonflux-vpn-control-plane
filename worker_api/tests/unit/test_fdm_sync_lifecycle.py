"""Unit tests for FDM sync lifecycle methods.

Tests the three new self-correcting behaviors:
- _auto_deactivate_phantom_deployments
- _validate_domain_ips_against_instances
- _rightsize_domain_pool
"""
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

# Pre-import the real package so app.services.fdm.__init__ is fully cached
# BEFORE the isolated load below re-registers a fresh module under the same
# name. Without this, collecting this file standalone (as the VM runner
# does) triggers a cold circular import: fdm_sync_service:29 (from .dns_provider)
# -> app.services.fdm/__init__:14 (from .fdm_sync_service import FdmSyncService)
# finds the half-executed module and raises ImportError. Idempotent in a full
# suite run where the package is already loaded.
import app.services.fdm.fdm_sync_service  # noqa: E402,F401
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
    id=1,
    flux_app_name="ch01",
    region="CH",
    is_active=True,
    consecutive_failures=0,
    last_sync_status="success",
    domain_pool_size=5,
):
    """Create a mock FdmDeployment-like object."""
    d = MagicMock()
    d.id = id
    d.flux_app_name = flux_app_name
    d.region = region
    d.is_active = is_active
    d.consecutive_failures = consecutive_failures
    d.last_sync_status = last_sync_status
    d.domain_pool_size = domain_pool_size
    d.base_domain = "operator4.example.invalid"
    d.protocol_name = None
    return d


# ---------------------------------------------------------------------------
# _auto_deactivate_phantom_deployments
# ---------------------------------------------------------------------------


def test_auto_deactivate_phantom_deactivates_at_threshold():
    """Deployment with consecutive_failures >= 3 should be deactivated."""
    phantom = _make_deployment(
        id=54,
        region="PT",
        consecutive_failures=3,
        last_sync_status="failed",
    )
    healthy = _make_deployment(
        id=2,
        region="CH",
        consecutive_failures=0,
        last_sync_status="success",
    )

    mock_db = MagicMock()
    # First query: find phantom deployments (filter by is_active + failures)
    mock_db.query.return_value.filter.return_value.all.return_value = [phantom]

    service = FdmSyncService(mock_db)
    _run(service._auto_deactivate_phantom_deployments())

    assert phantom.is_active is False, "Phantom deployment should be deactivated"
    assert healthy.is_active is True, "Healthy deployment should be untouched"
    mock_db.commit.assert_called_once()


def test_auto_deactivate_threshold_constant_is_three():
    """Threshold is exactly 3 -- deployments with failures=2 stay, failures=3 go.

    Note: The actual SQL filter ``>= 3`` is SQLAlchemy's responsibility.
    This test pins the PHANTOM_THRESHOLD constant so a future change
    breaks the suite and forces a conscious decision.
    """
    import inspect
    import re

    src = inspect.getsource(FdmSyncService._auto_deactivate_phantom_deployments)
    match = re.search(r"PHANTOM_THRESHOLD\s*=\s*(\d+)", src)
    assert match, "PHANTOM_THRESHOLD constant not found in method source"
    assert int(match.group(1)) == 3, f"Expected threshold 3, got {match.group(1)}"


def test_auto_deactivate_phantom_handles_empty_db():
    """No deployments at all -> no-op, no commit."""
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = []

    service = FdmSyncService(mock_db)
    _run(service._auto_deactivate_phantom_deployments())

    mock_db.commit.assert_not_called()


# ---------------------------------------------------------------------------
# _validate_domain_ips_against_instances
# ---------------------------------------------------------------------------


def _make_domain(
    id=1,
    deployment_id=1,
    domain_name="cdn-01.operator4.example.invalid",
    current_ip="168.119.18.248",
    health_status="healthy",
):
    """Create a mock FdmDomain-like object."""
    d = MagicMock()
    d.id = id
    d.deployment_id = deployment_id
    d.domain_name = domain_name
    d.current_ip = current_ip
    d.health_status = health_status
    # Phase 4b.1: model these as legacy NULL-tld_id domains so
    # _delete_dns_record_for_domain takes its NULL->active-TLD fallback
    # (behavior-identical to pre-4b.1). The new domain-own-TLD path is
    # covered by test_fdm_sync_tld_generation.py.
    d.tld_id = None
    return d


def _make_pi(ip="168.119.18.248", is_active=True):
    """Create a mock ProtocolInstance-like object."""
    pi = MagicMock()
    pi.ip_address = ip
    pi.is_active = is_active
    return pi


def _build_query_side_effect(fd_domain_results, pi_results):
    """Build a side_effect function for mock_db.query that dispatches by model.

    - For FdmDomain queries, returns a chain ending in .all() -> fd_domain_results
    - For ProtocolInstance queries, returns a chain ending in .first() -> next(pi_results)
    - For liveness queries, returns an empty set of app/IP observations
    """
    pi_iter = iter(pi_results)

    def query_side_effect(model, *columns):
        m = MagicMock()
        model_name = getattr(model, "__name__", str(model))
        if "FdmIpLiveness" in model_name:
            m.filter.return_value.all.return_value = []
        elif "FdmDomain" in model_name:
            m.filter.return_value.all.return_value = fd_domain_results
        elif "ProtocolInstance" in model_name:
            m.filter.return_value.first.side_effect = lambda: next(pi_iter)
        return m

    return query_side_effect


def test_validate_domain_ips_marks_stale_ip_unhealthy():
    """Domain pointing to IP not in active PI should be marked unhealthy."""
    fresh_domain = _make_domain(id=1, current_ip="168.119.18.248")
    stale_domain = _make_domain(id=2, current_ip="84.86.252.100")

    mock_db = MagicMock()
    mock_db.begin_nested.return_value = MagicMock()  # savepoint mock
    mock_db.query.side_effect = _build_query_side_effect(
        fd_domain_results=[fresh_domain, stale_domain],
        pi_results=[_make_pi(ip="168.119.18.248"), None],  # fresh found, stale not
    )

    service = FdmSyncService(mock_db)
    marked_count = _run(service._validate_domain_ips_against_instances())

    assert fresh_domain.health_status == "healthy", "Fresh domain should stay healthy"
    assert (
        stale_domain.health_status == "unhealthy"
    ), "Stale domain should be marked unhealthy"
    assert marked_count == 1
    mock_db.commit.assert_called_once()


def test_validate_domain_ips_skips_already_unhealthy():
    """Already-unhealthy domains are filtered out by the initial query."""
    mock_db = MagicMock()
    mock_db.begin_nested.return_value = MagicMock()
    # Initial query returns empty (filter excludes unhealthy)
    mock_db.query.side_effect = _build_query_side_effect(
        fd_domain_results=[],
        pi_results=[],
    )

    service = FdmSyncService(mock_db)
    count = _run(service._validate_domain_ips_against_instances())

    assert count == 0
    mock_db.commit.assert_not_called()


def test_validate_domain_ips_handles_null_current_ip():
    """Domain with NULL current_ip that slips past filter should be skipped gracefully.

    The SQL filter (current_ip != None) normally excludes null-IP domains, but
    if it ever doesn't, the implementation must not crash on str(None) or falsely
    match a PI with ip_address='None'. This test verifies that safety net.
    """
    null_domain = _make_domain(id=4, current_ip=None)

    mock_db = MagicMock()
    mock_db.begin_nested.return_value = MagicMock()
    # Simulate the null-IP domain slipping past the SQL filter
    mock_db.query.side_effect = _build_query_side_effect(
        fd_domain_results=[null_domain],
        pi_results=[None],  # No PI matches "None" string
    )

    service = FdmSyncService(mock_db)
    count = _run(service._validate_domain_ips_against_instances())

    # Domain should be marked unhealthy because no active PI matched
    # (str(None) = "None" which doesn't match any real IP)
    assert count == 1
    assert null_domain.health_status == "unhealthy"
    mock_db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Integration: sync_all_deployments wiring
# ---------------------------------------------------------------------------


def test_sync_all_deployments_invokes_phases_in_order():
    """sync_all_deployments should call all 10 lifecycle phases in the canonical order.

    The 10 phases, in order, are:
      fetch_and_persist_app_specs -> detect_spec_gap -> re_resolve_xx ->
      auto_split_regions -> detect_new_countries -> validate_domain_ips ->
      auto_deactivate_phantom -> reconcile_deployment_app_state ->
      prune_inactive_deployment_domains -> ensure_pi_for_fdm_domains.

    The load-bearing invariant this guards: reconcile_deployment_app_state
    (Task 2.1, deactivates orphaned deployments) must run IMMEDIATELY BEFORE
    prune_inactive_deployment_domains, so orphans it marks inactive are reaped
    by prune on the same session within prune's grace window. Without this
    ordering, prune would defer reaping to a later cycle.
    """
    from unittest.mock import AsyncMock, patch

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = (
        []
    )  # no active deployments

    order: list = []

    def record(tag, ret=None):
        """side_effect: append `tag` to `order` and return `ret` (mirrors phase return)."""

        def _():
            order.append(tag)
            return ret

        return _

    with patch.object(
        FdmSyncService,
        "_fetch_and_persist_app_specs",
        new_callable=AsyncMock,
        side_effect=record("fetch_and_persist_app_specs"),
    ) as mock_fetch_specs, patch.object(
        FdmSyncService,
        "_detect_spec_gap",
        new_callable=AsyncMock,
        side_effect=record("detect_spec_gap"),
    ) as mock_detect_gap, patch.object(
        FdmSyncService,
        "_re_resolve_xx_instances",
        new_callable=AsyncMock,
        side_effect=record("re_resolve_xx"),
    ) as mock_re_resolve, patch.object(
        FdmSyncService,
        "_auto_split_regions",
        new_callable=AsyncMock,
        side_effect=record("auto_split_regions"),
    ) as mock_split, patch.object(
        FdmSyncService,
        "_detect_new_countries",
        new_callable=AsyncMock,
        side_effect=record("detect_new_countries"),
    ) as mock_detect, patch.object(
        FdmSyncService,
        "_validate_domain_ips_against_instances",
        new_callable=AsyncMock,
        side_effect=record("validate_domain_ips", 0),
    ) as mock_validate, patch.object(
        FdmSyncService,
        "_auto_deactivate_phantom_deployments",
        new_callable=AsyncMock,
        side_effect=record("auto_deactivate_phantom", 0),
    ) as mock_deactivate, patch.object(
        FdmSyncService,
        "_reconcile_deployment_app_state",
        new_callable=AsyncMock,
        side_effect=record("reconcile_deployment_app_state"),
    ) as mock_reconcile, patch.object(
        FdmSyncService,
        "_prune_inactive_deployment_domains",
        new_callable=AsyncMock,
        side_effect=record("prune_inactive_deployment_domains", 0),
    ) as mock_prune, patch.object(
        FdmSyncService,
        "_ensure_pi_for_fdm_domains",
        new_callable=AsyncMock,
        side_effect=record("ensure_pi_for_fdm_domains"),
    ) as mock_ensure_pi:
        service = FdmSyncService(mock_db)
        _run(service.sync_all_deployments())

        # All 10 phases must be called exactly once
        mock_fetch_specs.assert_awaited_once()
        mock_detect_gap.assert_awaited_once()
        mock_re_resolve.assert_awaited_once()
        mock_split.assert_awaited_once()
        mock_detect.assert_awaited_once()
        mock_validate.assert_awaited_once()
        mock_deactivate.assert_awaited_once()
        mock_reconcile.assert_awaited_once()
        mock_prune.assert_awaited_once()
        mock_ensure_pi.assert_awaited_once()

    expected_order = [
        "fetch_and_persist_app_specs",
        "detect_spec_gap",
        "re_resolve_xx",
        "auto_split_regions",
        "detect_new_countries",
        "validate_domain_ips",
        "auto_deactivate_phantom",
        "reconcile_deployment_app_state",
        "prune_inactive_deployment_domains",
        "ensure_pi_for_fdm_domains",
    ]
    assert (
        order == expected_order
    ), f"Phases must run in the canonical order. Got {order}, expected {expected_order}"
    # Load-bearing invariant: reconcile_deployment_app_state immediately
    # precedes prune_inactive_deployment_domains.
    assert order.index("reconcile_deployment_app_state") + 1 == order.index(
        "prune_inactive_deployment_domains"
    ), "reconcile_deployment_app_state must run IMMEDIATELY before prune_inactive_deployment_domains"


# ---------------------------------------------------------------------------
# Reactivation: _detect_new_countries must reset consecutive_failures
# ---------------------------------------------------------------------------


def test_detect_new_countries_resets_consecutive_failures_on_reactivation():
    """Reactivating a previously-deactivated deployment must reset consecutive_failures.

    Without this, a phantom deactivated with failures=3 would be reactivated
    by _detect_new_countries (when region gets IPs again) but immediately
    re-deactivated by _auto_deactivate_phantom_deployments in the same sync
    cycle if the next sync fails for any reason.
    """
    # Read the source of _detect_new_countries and find the reactivation block
    import inspect

    src = inspect.getsource(FdmSyncService._detect_new_countries)

    # The reactivation block must include "consecutive_failures = 0"
    # to prevent phantom flapping
    assert (
        "consecutive_failures = 0" in src or "consecutive_failures=0" in src
    ), "_detect_new_countries must reset consecutive_failures = 0 on reactivation"

    # Find the reactivation context (where existing.is_active = True is set)
    assert "is_active = True" in src, "Reactivation block must exist"

    # Verify the reset happens AFTER the is_active assignment (or near it)
    # by checking they appear in the right order in source
    is_active_pos = src.find("is_active = True")
    reset_pos = src.find("consecutive_failures = 0")
    assert (
        reset_pos > is_active_pos
    ), f"Reset should come after reactivation. is_active at {is_active_pos}, reset at {reset_pos}"


# ---------------------------------------------------------------------------
# _rightsize_domain_pool invocation from sync_deployment
# ---------------------------------------------------------------------------


def test_rightsize_called_from_sync_deployment_on_success_branch():
    """Verify that _rightsize_domain_pool is invoked from sync_deployment's success branch.

    Uses source inspection to confirm the call exists in the SUCCESS branch.
    A future refactor that accidentally removes this call would break this test.
    """
    import inspect

    src = inspect.getsource(FdmSyncService.sync_deployment)

    # Find the success branch
    assert (
        'sync_log.status = "success"' in src
    ), "sync_deployment must have a success branch"

    # Find positions: success branch start vs rightsize call
    success_pos = src.find('sync_log.status = "success"')
    partial_pos = src.find('sync_log.status = "partial"', success_pos)
    rightsize_pos = src.find("_rightsize_domain_pool(", success_pos)

    assert rightsize_pos > success_pos, (
        f"_rightsize_domain_pool call must be in success branch. "
        f"success_pos={success_pos}, rightsize_pos={rightsize_pos}"
    )

    # Verify the rightsize call comes BEFORE the partial branch (i.e., in success branch)
    if partial_pos > 0:
        assert rightsize_pos < partial_pos, (
            f"_rightsize_domain_pool call must be in success branch (before partial). "
            f"rightsize_pos={rightsize_pos}, partial_pos={partial_pos}"
        )


def test_rightsize_called_from_sync_deployment_on_partial_branch():
    """Verify that _rightsize_domain_pool is also invoked from the PARTIAL branch.

    Pool sizing is independent of DNS update status — a partial sync with fewer
    IPs than domains should still rightsize.
    """
    import inspect

    src = inspect.getsource(FdmSyncService.sync_deployment)

    # Find the partial branch
    assert (
        'sync_log.status = "partial"' in src
    ), "sync_deployment must have a partial branch"

    # Count _rightsize_domain_pool calls — should be 2 (success + partial)
    call_count = src.count("_rightsize_domain_pool(")
    assert (
        call_count >= 2
    ), f"Expected at least 2 _rightsize_domain_pool calls (success + partial), got {call_count}"

    # Find the partial branch start and verify rightsize is called within it
    partial_pos = src.find('sync_log.status = "partial"')
    failed_pos = src.find('sync_log.status = "failed"', partial_pos)
    rightsize_after_partial = src.find("_rightsize_domain_pool(", partial_pos)

    assert rightsize_after_partial > partial_pos, (
        f"_rightsize_domain_pool must be called in partial branch. "
        f"partial_pos={partial_pos}, rightsize_after_partial={rightsize_after_partial}"
    )

    if failed_pos > 0:
        assert rightsize_after_partial < failed_pos, (
            f"_rightsize_domain_pool in partial branch must come before failed branch. "
            f"rightsize_after_partial={rightsize_after_partial}, failed_pos={failed_pos}"
        )


# ---------------------------------------------------------------------------
# DNS record cleanup on domain deletion
# ---------------------------------------------------------------------------


def test_delete_dns_record_for_domain_skips_when_no_record_id():
    """Domains without dns_record_id should be skipped (no DNS to clean up)."""
    mock_db = MagicMock()
    domain = _make_domain(id=99, current_ip="1.1.1.1")
    domain.dns_record_id = None  # No DNS record

    service = FdmSyncService(mock_db)
    _run(service._delete_dns_record_for_domain(domain))

    # Should not query for TLD since there's no record to delete
    mock_db.query.assert_not_called()


def test_delete_dns_record_for_domain_handles_missing_tld():
    """When no active FDM TLD exists, log warning and return."""
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    domain = _make_domain(id=99, current_ip="1.1.1.1")
    domain.dns_record_id = "abc123"

    service = FdmSyncService(mock_db)
    _run(service._delete_dns_record_for_domain(domain))

    # Verify TLD query happened
    mock_db.query.return_value.filter.return_value.first.assert_called_once()


def test_delete_dns_record_for_domain_swallows_dns_errors():
    """DNS provider errors should be logged but not propagated."""
    mock_db = MagicMock()

    # TLD lookup returns a valid TLD
    mock_tld = MagicMock()
    mock_tld.dns_provider = "cloudflare"
    mock_tld.domain = "operator4.example.invalid"
    mock_tld.zone_id = "zone123"
    mock_db.query.return_value.filter.return_value.first.return_value = mock_tld

    domain = _make_domain(id=99, current_ip="1.1.1.1")
    domain.dns_record_id = "rec123"

    # Patch create_dns_client to raise
    with patch("app.services.fdm.dns_provider.create_dns_client") as mock_factory:
        mock_factory.side_effect = RuntimeError("DNS API down")

        service = FdmSyncService(mock_db)
        # Should NOT raise — error must be swallowed
        _run(service._delete_dns_record_for_domain(domain))


# ---------------------------------------------------------------------------
# _auto_split_regions single-region collision guard
# ---------------------------------------------------------------------------


def _single_region_split_setup(existing_first):
    """Build (service, xx_dep, existing) for a single-region auto-split run.

    Discovery returns one healthy IP that resolves to 'US'. The DB holds one
    active XX placeholder. `existing_first` is what the per-region existence
    check (`...filter(...).first()`) returns — an existing US deployment or None.
    """
    from unittest.mock import AsyncMock

    xx_dep = _make_deployment(id=59, flux_app_name="na01", region="XX")
    mock_db = MagicMock()
    q = mock_db.query.return_value
    q.join.return_value = q
    q.filter.return_value.all.return_value = [xx_dep]  # XX-deployment listing
    q.filter.return_value.first.return_value = (
        existing_first  # per-region existence check
    )
    service = FdmSyncService(mock_db)
    # These tests isolate the XX-name collision paths; the PostgreSQL region
    # recovery tests exercise the real app-scoped liveness gate.
    service._region_candidate_ips = AsyncMock(return_value=["1.2.3.4"])
    return service, xx_dep, mock_db


def test_auto_split_single_region_deactivates_xx_when_region_exists():
    """When a per-region deployment already exists, the XX placeholder must be
    DEACTIVATED (not renamed) so the rename can't collide on uq_deployment_app_region.
    """
    from unittest.mock import AsyncMock

    existing_us = _make_deployment(
        id=61, flux_app_name="na01", region="US", is_active=True
    )
    service, xx_dep, mock_db = _single_region_split_setup(existing_first=existing_us)

    mock_discovery = AsyncMock()
    mock_discovery.get_app_instances = AsyncMock(
        return_value=(["1.2.3.4"], ["1.2.3.4"])
    )
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_discovery)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch.object(_mod, "FluxDiscoveryService", return_value=mock_cm), patch.object(
        FdmSyncService, "_resolve_ip_region", new_callable=AsyncMock, return_value="US"
    ):
        _run(service._auto_split_regions())

    assert xx_dep.is_active is False, "XX placeholder must be deactivated on collision"
    assert xx_dep.region == "XX", "XX placeholder must NOT be renamed on collision"
    assert existing_us.is_active is True, "existing region deployment stays/gets active"


def test_auto_split_single_region_renames_when_no_existing():
    """Regression: with no existing per-region deployment, XX is renamed to the
    single region (original behavior preserved)."""
    from unittest.mock import AsyncMock

    service, xx_dep, mock_db = _single_region_split_setup(existing_first=None)

    mock_discovery = AsyncMock()
    mock_discovery.get_app_instances = AsyncMock(
        return_value=(["1.2.3.4"], ["1.2.3.4"])
    )
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_discovery)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch.object(_mod, "FluxDiscoveryService", return_value=mock_cm), patch.object(
        FdmSyncService, "_resolve_ip_region", new_callable=AsyncMock, return_value="US"
    ):
        _run(service._auto_split_regions())

    assert xx_dep.region == "US", "XX should be renamed to the single region when free"
    assert xx_dep.is_active is True, "renamed deployment stays active"


def test_sync_all_rolls_back_before_logging_failed_deployment():
    """A deployment whose sync raises must trigger rollback() on ITS OWN
    scratch session BEFORE the failed FdmSyncLog is written there, AND must
    never touch the original service's self.db -- Phase 4.6 moved per-
    deployment failure handling to an isolated SessionLocal() per task."""
    from unittest.mock import AsyncMock

    dep = _make_deployment(id=61, flux_app_name="na01", region="US")
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = [dep]

    scratch_db = MagicMock()
    scratch_db.query.return_value.filter.return_value.first.return_value = dep
    call_order = []
    scratch_db.rollback.side_effect = lambda: call_order.append("rollback")
    scratch_db.add.side_effect = lambda *a, **k: call_order.append("add")

    with patch.object(
        FdmSyncService, "_fetch_and_persist_app_specs", new_callable=AsyncMock
    ), patch.object(
        FdmSyncService, "_detect_spec_gap", new_callable=AsyncMock
    ), patch.object(
        FdmSyncService, "_reconcile_deployment_app_state", new_callable=AsyncMock
    ), patch.object(
        FdmSyncService, "_re_resolve_xx_instances", new_callable=AsyncMock
    ), patch.object(
        FdmSyncService, "_auto_split_regions", new_callable=AsyncMock
    ), patch.object(
        FdmSyncService, "_detect_new_countries", new_callable=AsyncMock
    ), patch.object(
        FdmSyncService,
        "_validate_domain_ips_against_instances",
        new_callable=AsyncMock,
        return_value=0,
    ), patch.object(
        FdmSyncService,
        "_auto_deactivate_phantom_deployments",
        new_callable=AsyncMock,
        return_value=0,
    ), patch.object(
        FdmSyncService,
        "_prune_inactive_deployment_domains",
        new_callable=AsyncMock,
        return_value=0,
    ), patch.object(
        FdmSyncService,
        "_ensure_pi_for_fdm_domains",
        new_callable=AsyncMock,
        return_value=0,
    ), patch.object(
        FdmSyncService, "_prewarm_discovery_cache", new_callable=AsyncMock
    ), patch.object(
        _mod, "SessionLocal", return_value=scratch_db
    ), patch.object(
        FdmSyncService,
        "sync_deployment",
        new_callable=AsyncMock,
        side_effect=RuntimeError("boom"),
    ):
        service = FdmSyncService(mock_db)
        _run(service.sync_all_deployments())

    assert (
        "rollback" in call_order
    ), "scratch db.rollback() must be called on deployment failure"
    assert call_order.index("rollback") < call_order.index(
        "add"
    ), "rollback must happen before writing the failed FdmSyncLog"
    mock_db.rollback.assert_not_called()
    mock_db.commit.assert_not_called()


def test_run_phase_rolls_back_on_failure():
    """A pre-sync phase that raises must trigger db.rollback(), so a poisoned
    session (e.g. a failed commit inside the phase) cannot abort the unguarded
    `deployments = self.db.query(...)` that immediately follows the phases in
    sync_all_deployments. This is the actual fleet-abort surface from the na01
    incident: _auto_split_regions' failed commit was swallowed by _run_phase
    WITHOUT a rollback, then line ~1075's query hit PendingRollbackError."""
    from unittest.mock import AsyncMock

    mock_db = MagicMock()
    service = FdmSyncService(mock_db)
    boom = AsyncMock(side_effect=RuntimeError("phase boom"))

    _run(service._run_phase("boom_phase", boom))  # must NOT raise

    mock_db.rollback.assert_called_once()
