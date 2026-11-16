"""Unit tests for _get_or_create_instance resilience + sentinel usage."""
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


def _make_deployment(protocol_name=None, flux_app_name="ch01"):
    d = MagicMock()
    d.flux_app_name = flux_app_name
    d.protocol_name = protocol_name
    d.base_domain = "operator3.example.invalid"
    return d


def test_uses_sentinel_protocol_id_for_protocol_agnostic_deployment():
    """When deployment.protocol_name is None, must use protocol_id=0 (sentinel)."""
    deployment = _make_deployment(protocol_name=None)
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    mock_db.begin_nested.return_value = MagicMock()

    service = FdmSyncService(mock_db)
    result = service._get_or_create_instance(
        deployment, ip="1.2.3.4", instance_number=1
    )

    assert result is not None, "Should succeed with sentinel protocol_id=0"
    # Inspect the PI object that was added to session
    added_obj = mock_db.add.call_args[0][0]
    assert added_obj.protocol_id == 0, "Must use sentinel protocol_id=0"
    assert added_obj.component_name == "multi-protocol"
    # Must use flush() not commit() so savepoint rollback works cleanly
    mock_db.commit.assert_not_called()
    mock_db.flush.assert_called()


def test_reactivates_inactive_row_squatting_slot():
    """An INACTIVE row occupying the target (flux_app_name, component,
    instance_number) slot must be REUSED + reactivated, never left for a fresh
    INSERT. The uq_app_component_instance constraint ignores is_active, so the
    slot lookup must too — otherwise the insert collides (prod: repeated
    UniqueViolation on ch01/multi-protocol/1, ip 82.64.230.28, dead squatter
    94.60.150.175)."""
    deployment = _make_deployment(protocol_name=None)  # -> component 'multi-protocol'
    inactive = MagicMock()
    inactive.ip_address = "94.60.150.175"  # old dead IP holding the slot
    inactive.is_active = False
    inactive.id = 777

    mock_db = MagicMock()
    mock_db.begin_nested.return_value = MagicMock()
    # step 1 (lookup by IP, active) -> None; step 2 (lookup by slot) -> squatter
    mock_db.query.return_value.filter.return_value.first.side_effect = [None, inactive]

    service = FdmSyncService(mock_db)
    with patch.object(
        FdmSyncService, "_lookup_geoip", return_value=("CH", "Switzerland", "Zurich")
    ):
        result = service._get_or_create_instance(
            deployment, ip="82.64.230.28", instance_number=1
        )

    assert result is inactive, "must reuse the row squatting the slot"
    assert inactive.ip_address == "82.64.230.28", "must repoint to the live IP"
    assert inactive.is_active is True, "must REACTIVATE the reused slot row"
    mock_db.add.assert_not_called()  # no colliding fresh INSERT
    mock_db.flush.assert_called()


def test_updates_active_slot_row_with_rotated_ip():
    """Regression guard: an ACTIVE row on the slot with a different IP is still
    updated in place (existing behavior preserved by the constraint-aligned
    lookup)."""
    deployment = _make_deployment(protocol_name=None)
    active = MagicMock()
    active.ip_address = "10.0.0.1"
    active.is_active = True
    active.id = 501

    mock_db = MagicMock()
    mock_db.begin_nested.return_value = MagicMock()
    mock_db.query.return_value.filter.return_value.first.side_effect = [None, active]

    service = FdmSyncService(mock_db)
    with patch.object(
        FdmSyncService, "_lookup_geoip", return_value=("CH", "Switzerland", "Zurich")
    ):
        result = service._get_or_create_instance(
            deployment, ip="203.0.113.7", instance_number=2
        )

    assert result is active
    assert active.ip_address == "203.0.113.7"
    assert active.is_active is True
    mock_db.add.assert_not_called()


def test_create_pi_row_reuses_inactive_slot():
    """_create_pi_row_for_ip must also reuse an INACTIVE row squatting the
    deterministic (fdm-discovered, multi-protocol, hash(ip)) slot rather than
    INSERT and collide on uq_app_component_instance (the sibling of the
    _get_or_create_instance bug)."""
    inactive = MagicMock()
    inactive.ip_address = "1.1.1.1"
    inactive.is_active = False
    inactive.id = 42

    mock_db = MagicMock()
    mock_db.begin_nested.return_value = MagicMock()
    # 1st .first() = existence-by-active-IP -> None; 2nd = slot lookup -> squatter
    mock_db.query.return_value.filter.return_value.first.side_effect = [None, inactive]

    service = FdmSyncService(mock_db)
    service._create_pi_row_for_ip("82.64.230.28", "CH", "Switzerland", "Zurich")

    assert inactive.ip_address == "82.64.230.28", "must repoint the reused slot row"
    assert inactive.is_active is True, "must reactivate the reused slot row"
    mock_db.add.assert_not_called()  # no colliding fresh INSERT
    mock_db.flush.assert_called()


def test_failure_logs_structured_error_at_error_level():
    """On exception, must log at ERROR level with IP, deployment, and stack trace."""
    deployment = _make_deployment(protocol_name=None)
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    savepoint = MagicMock()
    mock_db.begin_nested.return_value = savepoint
    mock_db.flush.side_effect = Exception("simulated FK violation")

    service = FdmSyncService(mock_db)
    with patch.object(_mod.logger, "error") as mock_error:
        result = service._get_or_create_instance(
            deployment, ip="1.2.3.4", instance_number=1
        )

    assert result is None
    savepoint.rollback.assert_called_once()
    # Verify structured logging: message must mention IP + deployment + exc
    assert mock_error.called, "Must log at ERROR level"
    log_args = mock_error.call_args
    log_msg = log_args[0][0] if log_args[0] else ""
    assert "1.2.3.4" in log_msg, "Log must include IP"
    assert "ch01" in log_msg, "Log must include flux_app_name"
