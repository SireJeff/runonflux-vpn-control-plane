"""Unit test for _filter_ips_by_region creating PI rows on GeoIP match."""
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


def _run(coro):
    return asyncio.run(coro)


def test_geoip_matched_ip_creates_pi_row():
    """When GeoIP resolves an IP to the target region, a PI row should be created."""
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    mock_db.begin_nested.return_value = MagicMock()

    service = FdmSyncService(mock_db)

    async def fake_geoip(session, ip):
        # Simulate ip-api.com returning CH for 1.2.3.4
        return ("CH", "Switzerland", "Zurich")

    with patch.object(service, "_resolve_one_instance", new=fake_geoip):
        result = _run(service._filter_ips_by_region(["1.2.3.4"], "CH"))

    assert result == ["1.2.3.4"]
    # PI row should have been added via _create_pi_row_for_ip
    mock_db.add.assert_called()
    added_obj = mock_db.add.call_args[0][0]
    assert added_obj.ip_address == "1.2.3.4"
    assert added_obj.country_code == "CH"
    assert added_obj.protocol_id == 0  # Sentinel
    assert added_obj.component_name == "multi-protocol"
