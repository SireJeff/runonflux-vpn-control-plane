"""Unit tests for _ensure_pi_for_fdm_domains self-healing phase."""
import asyncio
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

from tests.unit._fdm_isolated_import import isolated_module_load


def _build_stubs():
    """Build sys.modules stand-ins for fdm_sync_service.py's transitive
    deps so it can be loaded without a real DB or app context. Only stubs a
    dependency that isn't already real -- isolated_module_load() applies
    exactly the dict it's given and restores it afterward; this function
    decides WHICH entries need stubbing, matching the file's own prior
    behavior. Avoids circular imports via __init__.py and missing modules
    like app.core.constants.
    """
    module_stubs = {}

    if "app.core" not in sys.modules:
        module_stubs["app.core"] = types.ModuleType("app.core")

    if "app.core.config" not in sys.modules:
        cfg = types.ModuleType("app.core.config")
        cfg.settings = MagicMock()
        module_stubs["app.core.config"] = cfg

    if "app.core.constants" not in sys.modules:
        const = types.ModuleType("app.core.constants")
        const.SUPPORTED_REGIONS = []
        const.COUNTRY_NAMES = {}
        module_stubs["app.core.constants"] = const

    if "app.core.database" not in sys.modules:
        db_mod = types.ModuleType("app.core.database")
        db_mod.Base = MagicMock()
        db_mod.Session = MagicMock
        module_stubs["app.core.database"] = db_mod

    if "app.models" not in sys.modules:
        models = types.ModuleType("app.models")
        models.ProtocolInstance = MagicMock
        module_stubs["app.models"] = models

    if "app.models.ip_management" not in sys.modules:
        ip_mgmt = types.ModuleType("app.models.ip_management")

        class _DummyPI:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

            ip_address = None
            is_active = True
            id = None

        ip_mgmt.ProtocolInstance = _DummyPI
        module_stubs["app.models.ip_management"] = ip_mgmt

    if "app.models.fdm" not in sys.modules:
        fdm_m = types.ModuleType("app.models.fdm")
        fdm_m.FdmDeployment = MagicMock
        fdm_m.FdmDomain = MagicMock
        fdm_m.FdmSyncLog = MagicMock
        module_stubs["app.models.fdm"] = fdm_m

    if "app.services" not in sys.modules:
        services_pkg = types.ModuleType("app.services")
        # __path__ makes this behave as a real package for resolving
        # submodules this file doesn't itself stub (e.g. app.services.flux),
        # instead of shadowing them with a dead end. Pre-existing bug --
        # empirically confirmed to break this file when combined with
        # files needing a real app.services.flux.* import.
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

    if "app.services.fdm.dns_provider" not in sys.modules:
        dns = types.ModuleType("app.services.fdm.dns_provider")
        dns.create_dns_client = MagicMock

        # DnsProviderClient: Phase 4.4's arvancloud_client.py now imports
        # this from the real dns_provider module. Pre-existing bug --
        # empirically confirmed to break this file's OWN collection, even
        # running completely alone, before this fix. MUST be a plain class
        # (not MagicMock) -- arvancloud_client.py subclasses it, and a fresh
        # exec of that module under a MagicMock base class would make the
        # real ArvanCloudDnsClient inherit Mock's __setattr__ restrictions,
        # breaking every later test that constructs a real ArvanCloudDnsClient
        # (empirically confirmed: combining this file with
        # test_fdm_phase4_arvan_rate_limit.py reproduced 10 failures with the
        # MagicMock stub, 0 with a plain class).
        class _DummyDnsProviderClient:
            pass

        dns.DnsProviderClient = _DummyDnsProviderClient
        module_stubs["app.services.fdm.dns_provider"] = dns

    if "app.services.fdm.fdm_domain_service" not in sys.modules:
        fds = types.ModuleType("app.services.fdm.fdm_domain_service")

        class _DummyDomainService:
            def __init__(self, db):
                pass

        fds.FdmDomainService = _DummyDomainService
        module_stubs["app.services.fdm.fdm_domain_service"] = fds

    if "app.services.fdm.flux_discovery" not in sys.modules:
        fld = types.ModuleType("app.services.fdm.flux_discovery")
        fld.FluxDiscoveryService = MagicMock
        module_stubs["app.services.fdm.flux_discovery"] = fld

    if "app.services.fdm.arvancloud_client" not in sys.modules:
        arvan = types.ModuleType("app.services.fdm.arvancloud_client")

        class ArvanCloudRateLimitBudgetExceeded(Exception):
            pass

        arvan.ArvanCloudRateLimitBudgetExceeded = ArvanCloudRateLimitBudgetExceeded
        module_stubs["app.services.fdm.arvancloud_client"] = arvan

    return module_stubs


_MOD_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "app"
    / "services"
    / "fdm"
    / "fdm_sync_service.py"
)
with isolated_module_load(
    "app.services.fdm.fdm_sync_service",
    _MOD_PATH,
    module_stubs=_build_stubs(),
) as _mod:
    FdmSyncService = _mod.FdmSyncService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro):
    return asyncio.run(coro)


def _make_domain(
    id=1,
    domain_name="de-01.operator3.example.invalid",
    current_ip="1.2.3.4",
    health_status="healthy",
    deployment_id=1,
):
    d = MagicMock()
    d.id = id
    d.domain_name = domain_name
    d.current_ip = current_ip
    d.health_status = health_status
    d.deployment_id = deployment_id
    return d


def _make_deployment(id=1, flux_app_name="ch01", region="DE"):
    d = MagicMock()
    d.id = id
    d.flux_app_name = flux_app_name
    d.region = region
    d.protocol_name = None
    return d


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_ensures_missing_pi_rows_are_created():
    """Healthy domains whose current_ip has no active PI row should get one."""
    domain = _make_domain(current_ip="5.6.7.8")
    deployment = _make_deployment()

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = [domain]
    # Production code makes two .first() calls per domain:
    #   1. existing PI lookup by IP -> None (no existing row)
    #   2. deployment lookup by deployment_id -> deployment object
    mock_db.query.return_value.filter.return_value.first.side_effect = [
        None,
        deployment,
    ]
    mock_db.begin_nested.return_value = MagicMock()

    service = FdmSyncService(mock_db)
    fake_instance = MagicMock(id=99)
    with patch.object(
        service, "_get_or_create_instance", return_value=fake_instance
    ) as mock_goci:
        result = _run(service._ensure_pi_for_fdm_domains())

    assert result == 1, "Should report 1 PI row created"
    mock_goci.assert_called_once()
    mock_db.commit.assert_called_once()


def test_skips_domains_with_existing_pi_row():
    """Domains whose current_ip already has an active PI row should be skipped."""
    domain = _make_domain(current_ip="5.6.7.8")

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = [domain]
    # First .first() returns existing PI row
    mock_db.query.return_value.filter.return_value.first.return_value = MagicMock(id=42)

    service = FdmSyncService(mock_db)
    with patch.object(service, "_get_or_create_instance") as mock_gci:
        result = _run(service._ensure_pi_for_fdm_domains())

    assert result == 0, "Should not create duplicate PI rows"
    mock_gci.assert_not_called()


def test_skips_domains_without_current_ip():
    """Domains with NULL current_ip should be skipped (nothing to backfill)."""
    # Note: query filter excludes NULL current_ip at SQL level, so this test
    # simulates the post-filter result being an empty list.
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = []

    service = FdmSyncService(mock_db)
    result = _run(service._ensure_pi_for_fdm_domains())

    assert result == 0
    mock_db.add.assert_not_called()


def test_continues_on_per_domain_failure():
    """Single-domain failure should not abort the whole phase."""
    good_domain = _make_domain(id=1, current_ip="1.1.1.1")
    bad_domain = _make_domain(id=2, current_ip="2.2.2.2")

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = [
        good_domain,
        bad_domain,
    ]
    # Production code makes two .first() calls per domain (PI lookup, then deployment lookup).
    # For both domains: PI lookup -> None; deployment lookup -> deployment object.
    # bad_domain fails inside _get_or_create_instance (after deployment lookup succeeds).
    mock_db.query.return_value.filter.return_value.first.side_effect = [
        None,
        _make_deployment(id=1),  # good_domain
        None,
        _make_deployment(id=2),  # bad_domain
    ]
    mock_db.begin_nested.return_value = MagicMock()

    service = FdmSyncService(mock_db)

    def fake_goci(deployment, ip, instance_number):
        if "2.2.2.2" in str(ip):
            raise Exception("simulated per-IP failure")
        return MagicMock(id=99)

    with patch.object(service, "_get_or_create_instance", side_effect=fake_goci):
        result = _run(service._ensure_pi_for_fdm_domains())

    assert result == 1, "Only the successful domain counts"
