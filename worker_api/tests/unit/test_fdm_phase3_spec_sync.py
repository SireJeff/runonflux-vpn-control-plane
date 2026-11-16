"""Phase 3 Tasks 3.3-3.5: spec fetch/persist phase + gap detection + pool sizing."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

# Bind the module OBJECT FdmSyncService comes from, then patch via patch.object on
# it. String-based patch("app.services.fdm.fdm_sync_service.X") resolves through
# sys.modules at patch time -- but a sibling test (test_fdm_sync_lifecycle.py) re-execs
# this module into sys.modules at collection time, swapping it out from under us. That
# left our FdmSyncService referencing the original (unpatched, real) FluxSpecFetcher ->
# real live API calls. patch.object(_fdm, ...) patches the exact module object our
# FdmSyncService was defined in, so it is immune to any sys.modules swap.
import app.services.fdm.fdm_sync_service as _fdm  # noqa: E402
from app.services.fdm.fdm_sync_service import _DiscoveryResult as _DR

FdmSyncService = _fdm.FdmSyncService


def _run(coro):
    return asyncio.run(coro)


def _make_app(app_name="ch01", expected=None, is_active=True):
    a = MagicMock()
    a.app_name = app_name
    a.is_active = is_active
    a.expected_instances = expected
    a.spec_components = None
    a.spec_geolocation = None
    a.last_spec_fetched_at = None
    a.last_spec_status = None
    return a


# --- Task 3.3: fetch + persist ---


def test_fetch_and_persist_app_specs_stores_expected():
    app_a = _make_app("ch01")
    reg_q = MagicMock()
    reg_q.filter.return_value.all.return_value = [app_a]
    mock_db = MagicMock()
    mock_db.query.side_effect = lambda m: (
        reg_q
        if "FluxAppRegistration" in getattr(m, "__name__", str(m))
        else MagicMock()
    )
    service = FdmSyncService(mock_db)
    fake_spec = {
        "instances": 6,
        "components": [{"name": "ssh"}],
        "geolocation": [],
        "raw": {},
    }
    with patch.object(_fdm, "FluxSpecFetcher") as FS, patch.object(
        _fdm, "FluxCloudClient"
    ):
        FS.return_value.fetch_spec = AsyncMock(return_value=fake_spec)
        _run(service._fetch_and_persist_app_specs())
    assert app_a.expected_instances == 6
    assert app_a.last_spec_status == "ok"
    assert service._spec_expected.get("ch01") == 6
    mock_db.commit.assert_called()


def test_fetch_and_persist_app_specs_degrades_on_failure():
    """Fetch failure -> last_spec_status='fetch_failed', prior expected retained,
    app NOT added to the intra-cycle cache."""
    app_a = _make_app("ch01", expected=6)
    reg_q = MagicMock()
    reg_q.filter.return_value.all.return_value = [app_a]
    mock_db = MagicMock()
    mock_db.query.side_effect = lambda m: (
        reg_q
        if "FluxAppRegistration" in getattr(m, "__name__", str(m))
        else MagicMock()
    )
    service = FdmSyncService(mock_db)
    with patch.object(_fdm, "FluxSpecFetcher") as FS, patch.object(
        _fdm, "FluxCloudClient"
    ):
        FS.return_value.fetch_spec = AsyncMock(return_value=None)
        _run(service._fetch_and_persist_app_specs())
    assert app_a.last_spec_status == "fetch_failed"
    assert app_a.expected_instances == 6, "prior expected retained"
    assert "ch01" not in service._spec_expected


# --- Task 3.4: gap detection + de-dup alert + per-deployment log (Option B) ---


def test_detect_spec_gap_no_alert_when_actual_meets_expected():
    app = _make_app("ch01", expected=3)
    reg_q = MagicMock()
    reg_q.filter.return_value.all.return_value = [app]
    mock_db = MagicMock()
    mock_db.query.side_effect = lambda m: (
        reg_q
        if "FluxAppRegistration" in getattr(m, "__name__", str(m))
        else MagicMock()
    )
    service = FdmSyncService(mock_db)
    service._get_platform_setting = lambda k: None
    service._set_platform_setting = lambda k, v: None
    with patch.object(
        FdmSyncService,
        "_get_cached_instances",
        new=AsyncMock(
            return_value=_DR(
                ["1.1.1.1", "2.2.2.2", "3.3.3.3"],
                ["1.1.1.1", "2.2.2.2", "3.3.3.3"],
                ok=True,
                error=None,
            )
        ),
    ), patch("app.services.notifications.router.NotificationRouter") as NR:
        _run(service._detect_spec_gap())
    NR.return_value.send_to_super_admin.assert_not_called()
    # Option B: no gap -> app NOT recorded for sync-log injection
    assert "ch01" not in service._spec_gap_by_app


def test_detect_spec_gap_uses_all_ips_not_port_health():
    """Hotfix: `actual` is measured on Flux-consensus all_ips, NOT the port-443
    healthy subset. Protocol-agnostic apps don't serve on 443, so healthy_ips
    can be empty while the app runs on many nodes. Constructs that exact case
    (6 running, 0 healthy-on-443, expected=6) and asserts NO gap is recorded.
    The sibling tests set all_ips == healthy_ips, so they cannot distinguish
    which field _detect_spec_gap reads — only this test can."""
    app = _make_app("ch01", expected=6)
    reg_q = MagicMock()
    reg_q.filter.return_value.all.return_value = [app]
    mock_db = MagicMock()
    mock_db.query.side_effect = lambda m: (
        reg_q
        if "FluxAppRegistration" in getattr(m, "__name__", str(m))
        else MagicMock()
    )
    service = FdmSyncService(mock_db)
    settings = {}
    service._get_platform_setting = lambda k: settings.get(k)
    service._set_platform_setting = lambda k, v: settings.__setitem__(k, v)
    # 6 distinct running IPs, NONE healthy on port 443 (protocol-agnostic case).
    discovery = _DR(
        ["10.0.0.1", "10.0.0.2", "10.0.0.3", "10.0.0.4", "10.0.0.5", "10.0.0.6"],
        [],
        ok=True,
        error=None,
    )
    with patch.object(
        FdmSyncService, "_get_cached_instances", new=AsyncMock(return_value=discovery)
    ), patch("app.services.notifications.router.NotificationRouter") as NR:
        _run(service._detect_spec_gap())
    NR.return_value.send_to_super_admin.assert_not_called()
    assert (
        "ch01" not in service._spec_gap_by_app
    ), "all_ips=6 meets expected=6 -> no gap, even though healthy_ips=[]"
    assert (
        settings.get("fdm:spec_gap:ch01:cycles") == "0"
    ), "actual>=expected resets cycles to 0"


def test_detect_spec_gap_alerts_after_threshold_and_dedups():
    """actual=3 < expected=6. Cycle counter starts at threshold-1 so THIS cycle
    crosses the threshold -> alert fires once. A second call within cooldown is
    suppressed (de-dup). Option B: the gap is also recorded in _spec_gap_by_app
    for per-deployment sync-log injection."""
    app = _make_app("ch01", expected=6)
    reg_q = MagicMock()
    reg_q.filter.return_value.all.return_value = [app]
    mock_db = MagicMock()
    mock_db.query.side_effect = lambda m: (
        reg_q
        if "FluxAppRegistration" in getattr(m, "__name__", str(m))
        else MagicMock()
    )
    service = FdmSyncService(mock_db)
    settings = {"fdm:spec_gap:ch01:cycles": "2"}  # +1 => 3 => threshold crossed
    service._get_platform_setting = lambda k: settings.get(k)

    def setter(k, v):
        settings[k] = v

    service._set_platform_setting = setter

    with patch.object(
        FdmSyncService,
        "_get_cached_instances",
        new=AsyncMock(
            return_value=_DR(
                ["1.1.1.1", "2.2.2.2", "3.3.3.3"],
                ["1.1.1.1", "2.2.2.2", "3.3.3.3"],
                ok=True,
                error=None,
            )
        ),
    ), patch("app.services.notifications.router.NotificationRouter") as NR:
        _run(service._detect_spec_gap())
    NR.return_value.send_to_super_admin.assert_called_once()
    assert any(k.endswith(":last_alerted") for k in settings), "last_alerted stamped"
    assert service._spec_gap_by_app.get("ch01") == {"expected": 6, "actual": 3}

    # Second call within cooldown -> suppressed
    with patch.object(
        FdmSyncService,
        "_get_cached_instances",
        new=AsyncMock(
            return_value=_DR(
                ["1.1.1.1", "2.2.2.2", "3.3.3.3"],
                ["1.1.1.1", "2.2.2.2", "3.3.3.3"],
                ok=True,
                error=None,
            )
        ),
    ), patch("app.services.notifications.router.NotificationRouter") as NR2:
        _run(service._detect_spec_gap())
    NR2.return_value.send_to_super_admin.assert_not_called()


def test_spec_gap_injected_into_sync_log_errors():
    """Option B: a deployment whose owning app has a spec gap gets a spec_gap
    entry appended to its sync_log.errors (queryable in fdm_sync_logs)."""
    service = FdmSyncService(MagicMock())
    service._spec_gap_by_app = {"ch01": {"expected": 6, "actual": 3}}
    dep = MagicMock()
    dep.flux_app_name = "ch01"
    sync_log = MagicMock()
    sync_log.errors = None
    service._inject_spec_gap_into_log(dep, sync_log)
    assert sync_log.errors == [{"spec_gap": {"expected": 6, "actual": 3}}]


def test_spec_gap_not_injected_when_app_has_no_gap():
    """No-op when the app has no gap this cycle; pre-existing errors untouched."""
    service = FdmSyncService(MagicMock())
    service._spec_gap_by_app = {}
    dep = MagicMock()
    dep.flux_app_name = "ch01"
    prior = [{"step": "dns", "error": "boom"}]
    sync_log = MagicMock()
    sync_log.errors = prior
    service._inject_spec_gap_into_log(dep, sync_log)
    assert sync_log.errors == prior


# --- Task 3.5: spec-informed pool sizing ---


def test_spec_pool_target_uses_expected_when_above_live():
    service = FdmSyncService(MagicMock())
    service._spec_expected = {"ch01": 6}
    assert service._spec_pool_target(MagicMock(flux_app_name="ch01"), 3) == 6


def test_spec_pool_target_caps_at_pool_cap():
    service = FdmSyncService(MagicMock())
    service._spec_expected = {"big": 100}
    assert (
        service._spec_pool_target(MagicMock(flux_app_name="big"), 3) == service.POOL_CAP
    )


def test_spec_pool_target_live_above_expected_uses_live():
    service = FdmSyncService(MagicMock())
    service._spec_expected = {"ch01": 4}
    assert service._spec_pool_target(MagicMock(flux_app_name="ch01"), 10) == 10


def test_spec_pool_target_falls_back_to_min_when_no_spec():
    service = FdmSyncService(MagicMock())
    service._spec_expected = {}
    service.db.query.return_value.filter.return_value.first.return_value = None
    # live=3, no expected -> max(3, min(MIN=2, CAP)) = max(3, 2) = 3
    assert service._spec_pool_target(MagicMock(flux_app_name="unknown"), 3) == 3


def test_runtime_pool_methods_call_spec_target():
    """The three runtime pool-sizing sites must delegate to _spec_pool_target
    (so the spec-aware target is actually applied)."""
    import inspect

    for method in (
        "_ensure_domains_exist",
        "_manage_domain_lifecycle",
        "_rightsize_domain_pool",
    ):
        src = inspect.getsource(getattr(FdmSyncService, method))
        assert "_spec_pool_target" in src, f"{method} must use _spec_pool_target"
