"""Phase 4.1: per-app discovery cache — one fetch per (app,port) per cycle, with
a failure sentinel that distinguishes discovery-down from app-empty (3.4-a/d)."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import app.services.fdm.fdm_sync_service as _fdm  # noqa: E402

FdmSyncService = _fdm.FdmSyncService
_DiscoveryResult = _fdm._DiscoveryResult


def _run(coro):
    return asyncio.run(coro)


def _discovery_cm(ips_all, ips_healthy, *, raises=None):
    """Build a mock whose async-CM instance returns (ips_all, ips_healthy), or
    raises `raises` from get_app_instances."""
    inst = AsyncMock()
    if raises is not None:
        inst.get_app_instances = AsyncMock(side_effect=raises)
    else:
        inst.get_app_instances = AsyncMock(return_value=(ips_all, ips_healthy))
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=inst)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm


def test_cache_returns_success_result():
    service = FdmSyncService(MagicMock())
    with patch.object(
        _fdm,
        "FluxDiscoveryService",
        return_value=_discovery_cm(["1.1.1.1", "2.2.2.2"], ["1.1.1.1"]),
    ):
        res = _run(service._get_cached_instances("ch01", 443))
    assert res.ok is True and res.error is None
    assert res.all_ips == ["1.1.1.1", "2.2.2.2"]
    assert res.healthy_ips == ["1.1.1.1"]


def test_cache_stores_failure_sentinel():
    """Discovery raises -> ok=False sentinel (NOT re-raised). A success-only cache
    would re-fetch+re-fail on every call site during an outage (defeats 3.4-d)."""
    service = FdmSyncService(MagicMock())
    with patch.object(
        _fdm,
        "FluxDiscoveryService",
        return_value=_discovery_cm([], [], raises=RuntimeError("flux 429")),
    ):
        res = _run(service._get_cached_instances("ch01", 443))
    assert res.ok is False
    assert res.all_ips == [] and res.healthy_ips == []
    assert "flux 429" in (res.error or "")


def test_cache_calls_get_app_instances_once_per_key():
    """3.4-d: across repeated calls for the same (app,port), the underlying
    get_app_instances is invoked exactly once per cycle."""
    service = FdmSyncService(MagicMock())
    inst = AsyncMock()
    inst.get_app_instances = AsyncMock(return_value=(["1.1.1.1"], ["1.1.1.1"]))
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=inst)
    cm.__aexit__ = AsyncMock(return_value=None)
    with patch.object(_fdm, "FluxDiscoveryService", return_value=cm):
        for _ in range(4):
            res = _run(service._get_cached_instances("ch01", 443))
    assert inst.get_app_instances.await_count == 1
    assert res.ok is True


def test_cache_key_isolated_by_port():
    """Same app, different port -> two cache entries (healthy set can differ by port)."""
    service = FdmSyncService(MagicMock())
    with patch.object(
        _fdm,
        "FluxDiscoveryService",
        return_value=_discovery_cm(["1.1.1.1"], ["1.1.1.1"]),
    ):
        _run(service._get_cached_instances("ch01", 443))
    with patch.object(
        _fdm,
        "FluxDiscoveryService",
        return_value=_discovery_cm(["2.2.2.2"], ["2.2.2.2"]),
    ):
        _run(service._get_cached_instances("ch01", 22))
    assert service._discovery_cache[("ch01", 443)].healthy_ips == ["1.1.1.1"]
    assert service._discovery_cache[("ch01", 22)].healthy_ips == ["2.2.2.2"]


def test_cache_ok_true_with_empty_is_success_not_failure():
    """Discovery succeeds but app has zero healthy -> ok=True, empty. Distinct from
    discovery failure (ok=False). _detect_spec_gap relies on this split (3.4-a)."""
    service = FdmSyncService(MagicMock())
    with patch.object(_fdm, "FluxDiscoveryService", return_value=_discovery_cm([], [])):
        res = _run(service._get_cached_instances("ch01", 443))
    assert res.ok is True and res.healthy_ips == []


# --- Phase 4.1.2: rewires + skip-on-failure (3.4-a) + M2 guard ---


def test_detect_spec_gap_freezes_on_discovery_failure():
    """3.4-a: discovery failure -> _detect_spec_gap skips the app entirely (no
    cycles increment, no _spec_gap_by_app entry, no alert). Contrast: a real gap
    (ok=True, fewer than expected) DOES increment."""
    app = MagicMock()
    app.app_name = "ch01"
    app.expected_instances = 6
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
    failed = _DiscoveryResult([], [], ok=False, error="timeout")
    with patch.object(
        FdmSyncService, "_get_cached_instances", new=AsyncMock(return_value=failed)
    ), patch("app.services.notifications.router.NotificationRouter") as NR:
        _run(service._detect_spec_gap())
    NR.return_value.send_to_super_admin.assert_not_called()
    assert (
        "fdm:spec_gap:ch01:cycles" not in settings
    ), "cycles must not advance on discovery failure"
    assert (
        "ch01" not in service._spec_gap_by_app
    ), "no gap recorded when discovery failed"


def test_detect_spec_gap_survives_corrupt_cycles_value():
    """M2: a non-numeric cycles PlatformSetting must NOT ValueError-abort the phase."""
    app = MagicMock()
    app.app_name = "ch01"
    app.expected_instances = 6
    reg_q = MagicMock()
    reg_q.filter.return_value.all.return_value = [app]
    mock_db = MagicMock()
    mock_db.query.side_effect = lambda m: (
        reg_q
        if "FluxAppRegistration" in getattr(m, "__name__", str(m))
        else MagicMock()
    )
    service = FdmSyncService(mock_db)
    settings = {"fdm:spec_gap:ch01:cycles": "not-a-number"}
    service._get_platform_setting = lambda k: settings.get(k)
    service._set_platform_setting = lambda k, v: settings.__setitem__(k, v)
    ok_gap = _DiscoveryResult(
        ["1.1.1.1"], ["1.1.1.1"], ok=True, error=None
    )  # 1 < 6 -> real gap
    with patch.object(
        FdmSyncService, "_get_cached_instances", new=AsyncMock(return_value=ok_gap)
    ), patch("app.services.notifications.router.NotificationRouter"):
        _run(service._detect_spec_gap())  # must NOT raise
    # corrupt value -> reset to 1 (not aborted); alert only after threshold so not yet sent
    assert settings["fdm:spec_gap:ch01:cycles"] == "1"


def test_healthy_sync_of_gapped_app_stays_success_with_spec_gap_in_errors():
    """3.4-c: a healthy sync_deployment whose owning app has a spec gap stays
    status='success' with the gap recorded in errors. Exercises the REAL call
    site at fdm_sync_service.py:275 (injection AFTER status computation at :233,
    outside the try/except).

    If a refactor moves injection before the status check, the spec_gap entry
    lands in `errors` -> `errors` is now truthy -> the `if errors:` block at
    :260 overwrites sync_log.errors AFTER the success branch already set
    status='success', BUT more critically the success-branch condition
    `if not errors and ...` at :233 would flip to False -> status flips
    success->partial -> this test fails. That ordering invariant is what this
    test exists to pin.

    E2E via sync_deployment (not the injector directly): mocks the 6
    side-effect seams so the success branch is reached — discovery returns a
    healthy IP, region='DE' (non-XX) skips the :187 ProtocolInstance
    auto-detect branch that would otherwise mutate deployment.region via a
    truthy MagicMock query, _ensure_domains_exist returns one domain, and
    _update_dns_records_v2 returns (1, []) so `domains_updated == len(domains)`
    and `not errors` both hold. The real FdmSyncLog is captured from
    db.add() calls, then status + errors are asserted post-injection."""
    from app.models.fdm import FdmSyncLog

    dep = MagicMock()
    dep.flux_app_name = "ch01"
    dep.region = "DE"  # non-XX -> skips :187 ProtocolInstance auto-detect branch

    mock_db = MagicMock()
    added = []
    mock_db.add.side_effect = lambda o: added.append(o)  # capture real FdmSyncLog

    service = FdmSyncService(mock_db)
    service._spec_gap_by_app = {"ch01": {"expected": 6, "actual": 3}}

    domains = [MagicMock()]  # 1 domain; non-empty -> :207 "No domains" guard passes

    with patch.object(
        FdmSyncService,
        "_discover_instances",
        new=AsyncMock(return_value=(["1.1.1.1"], ["1.1.1.1"])),
    ), patch.object(
        FdmSyncService, "_filter_ips_by_region", new=AsyncMock(return_value=["1.1.1.1"])
    ), patch.object(
        FdmSyncService, "_manage_domain_lifecycle", new=AsyncMock()
    ), patch.object(
        FdmSyncService, "_ensure_domains_exist", new=MagicMock(return_value=domains)
    ), patch.object(
        FdmSyncService,
        "_update_dns_records_v2",
        new=AsyncMock(return_value=(len(domains), [])),
    ), patch.object(
        FdmSyncService, "_rightsize_domain_pool", new=AsyncMock()
    ), patch.object(
        FdmSyncService, "_alert_dns_dark_tlds", new=AsyncMock()
    ), patch(
        "app.services.notifications.router.NotificationRouter"
    ):
        _run(service.sync_deployment(dep))

    sync_logs = [o for o in added if isinstance(o, FdmSyncLog)]
    assert sync_logs, "a FdmSyncLog must be created and db.add'd by sync_deployment"
    log = sync_logs[0]
    assert (
        log.status == "success"
    ), f"healthy sync of a gapped app must stay success, got {log.status!r}"
    assert any(
        "spec_gap" in str(e) for e in (log.errors or [])
    ), "errors must contain the spec_gap entry after injection"


# --- Phase 4.1.3: M1 — redact compose[].environmentParameters from DEBUG log ---


def test_scrub_env_params_strips_compose_environment_parameters():
    """M1: the DEBUG-log scrub strips compose[].environmentParameters (JWTs)."""
    from app.services.flux.client import FluxCloudClient

    client = FluxCloudClient()
    payload = {
        "data": {
            "app": "ch01",
            "compose": [
                {"name": "ssh", "environmentParameters": {"FLUXVPN_AUTH_TOKEN": "jwt"}},
                {"name": "ss", "environmentParameters": {"X": "y"}},
            ],
        }
    }
    scrubbed = client._scrub_env_params(payload)
    for comp in scrubbed["data"]["compose"]:
        assert "environmentParameters" not in comp
    # log-only: original payload UNTOUCHED (fetcher still reads environmentParameters)
    assert payload["data"]["compose"][0]["environmentParameters"] == {
        "FLUXVPN_AUTH_TOKEN": "jwt"
    }


def test_request_redact_is_wired():
    """M1: _request must accept redact and route through _scrub_env_params."""
    import inspect

    from app.services.flux.client import FluxCloudClient

    src = inspect.getsource(FluxCloudClient._request)
    assert "redact" in src and "_scrub_env_params" in src
