"""Phase 2 tests: deployment<->app active-state reconciliation."""
import asyncio
from unittest.mock import MagicMock, patch


def _run(coro):
    return asyncio.run(coro)


def test_update_app_toggle_off_deactivates_protocol_instances():
    """Toggling is_active=False must deactivate app-scoped ProtocolInstance rows
    so they leave the connection-string JOIN (mirrors delete_app). Goal-3
    completeness — final-review finding I-1."""
    from importlib import import_module

    from app.api.v1.endpoints import super_admin

    app = MagicMock(id=1, app_name="ch01", is_active=True, protocol_ports={})
    app_q = MagicMock()
    app_q.filter.return_value.first.return_value = app
    dep_q = MagicMock()  # FdmDeployment toggle
    pi_q = MagicMock()  # ProtocolInstance deactivate

    mock_db = MagicMock()

    def query(model):
        name = getattr(model, "__name__", str(model))
        if "FluxAppRegistration" in name:
            return app_q
        if "ProtocolInstance" in name:
            return pi_q
        return dep_q

    mock_db.query.side_effect = query

    Req = None
    for mp in ("app.schemas.super_admin", "app.api.v1.endpoints.super_admin"):
        try:
            m = import_module(mp)
            if hasattr(m, "UpdateAppRequest"):
                Req = m.UpdateAppRequest
        except Exception:
            pass
    assert Req, "UpdateAppRequest not found"
    request = Req(is_active=False)

    with patch("app.tasks.fdm_tasks.reconcile_app"):
        resp = _run(super_admin.update_app(1, request, mock_db, {}))

    pi_q.filter.return_value.update.assert_called_once()
    update_arg = pi_q.filter.return_value.update.call_args[0][0]
    assert update_arg == {"is_active": False}, "PI rows must be deactivated"

    # Important 2 (final-review): the deactivate must be scoped by flux_app_name,
    # not an unfiltered UPDATE that wipes ALL ProtocolInstance rows. The filter
    # arg is a SQLAlchemy BinaryExpression; stringify and inspect the column.
    filter_expr = pi_q.filter.call_args[0][0]
    assert "flux_app_name" in str(
        filter_expr
    ), "PI deactivate must be scoped by flux_app_name, not unfiltered"
    # Minor 3 (final-review): synchronize_session=False must be passed to avoid
    # identity-map synchronization overhead on a bulk UPDATE.
    assert (
        pi_q.filter.return_value.update.call_args[1].get("synchronize_session") is False
    )

    assert app.is_active is False
    assert "reconcile" in resp["message"].lower()


def test_update_app_toggle_on_does_not_deactivate_protocol_instances():
    """Toggling is_active=True must NOT touch ProtocolInstance rows (toggle-ON
    reactivates PI via the reconcile sync's _ensure_pi_for_fdm_domains phase).
    A regression that drops the `if request.is_active is False:` guard and
    unconditionally deactivates PI rows would silently break reactivation.
    Final-review finding I-1 (toggle-ON path coverage)."""
    from importlib import import_module

    from app.api.v1.endpoints import super_admin

    app = MagicMock(id=1, app_name="ch01", is_active=False, protocol_ports={})
    app_q = MagicMock()
    app_q.filter.return_value.first.return_value = app
    dep_q = MagicMock()  # FdmDeployment toggle
    pi_q = MagicMock()  # ProtocolInstance deactivate

    mock_db = MagicMock()

    def query(model):
        name = getattr(model, "__name__", str(model))
        if "FluxAppRegistration" in name:
            return app_q
        if "ProtocolInstance" in name:
            return pi_q
        return dep_q

    mock_db.query.side_effect = query

    Req = None
    for mp in ("app.schemas.super_admin", "app.api.v1.endpoints.super_admin"):
        try:
            m = import_module(mp)
            if hasattr(m, "UpdateAppRequest"):
                Req = m.UpdateAppRequest
        except Exception:
            pass
    assert Req, "UpdateAppRequest not found"
    request = Req(is_active=True)

    with patch("app.tasks.fdm_tasks.reconcile_app"):
        resp = _run(super_admin.update_app(1, request, mock_db, {}))

    # The toggle-ON path must not issue any PI-deactivate UPDATE.
    pi_q.filter.return_value.update.assert_not_called()
    assert app.is_active is True
    # Confirms the toggle path ran (vs. the no-toggle "App updated" branch).
    assert "reconcile" in resp["message"].lower()


# --- _reconcile_deployment_app_state: deactivate deployments under inactive/missing apps ---


def _make_deployment(id=1, flux_app_name="ch01", region="DE", is_active=True):
    d = MagicMock()
    d.id = id
    d.flux_app_name = flux_app_name
    d.region = region
    d.is_active = is_active
    return d


def test_reconcile_deployment_app_state_deactivates_orphans():
    """An ACTIVE deployment whose app is missing or inactive is deactivated each
    cycle so the prune phase reaps its DNS in the SAME cycle. Covers both
    operator-toggle-off (plan 2.1) and deleted-app orphan (plan 2.2).

    Phase 4.7a: orphan detection moved from a Python-side list-comprehension
    filter to a SQL NOT-IN clause. The mock's dep_q.all() return value now
    represents what that SQL filter would already have narrowed down to --
    just the orphan -- since the mock doesn't evaluate real SQL itself."""
    from app.services.fdm.fdm_sync_service import FdmSyncService

    dep_live = _make_deployment(id=1, flux_app_name="ch01", region="DE")
    dep_dead = _make_deployment(id=2, flux_app_name="goneapp", region="US")

    mock_db = MagicMock()
    reg_q = MagicMock()
    reg_q.filter.return_value.all.return_value = [("ch01",)]
    dep_q = MagicMock()
    dep_q.filter.return_value.all.return_value = [dep_dead]

    def query(model):
        name = getattr(model, "__name__", str(model))
        if "FluxAppRegistration" in name:
            return reg_q
        return dep_q

    mock_db.query.side_effect = query

    service = FdmSyncService(mock_db)
    _run(service._reconcile_deployment_app_state())

    assert (
        dep_live.is_active is True
    ), "live-app deployment stays active (never touched by the deactivate loop)"
    assert dep_dead.is_active is False, "missing-app deployment deactivated"
    mock_db.commit.assert_called_once()


def test_reconcile_deployment_app_state_deactivates_multiple_orphans():
    """Multiple orphaned deployments across different apps are all deactivated
    in one pass, and commit() still fires exactly once regardless of orphan
    count -- guards against an off-by-one or early-return in the new SQL-side
    filtering."""
    from app.services.fdm.fdm_sync_service import FdmSyncService

    dep_live = _make_deployment(id=1, flux_app_name="ch01", region="DE")
    dep_dead_1 = _make_deployment(id=2, flux_app_name="goneapp", region="US")
    dep_dead_2 = _make_deployment(id=3, flux_app_name="alsogone", region="NL")
    dep_dead_3 = _make_deployment(id=4, flux_app_name="goneapp", region="FR")

    mock_db = MagicMock()
    reg_q = MagicMock()
    reg_q.filter.return_value.all.return_value = [("ch01",)]
    dep_q = MagicMock()
    dep_q.filter.return_value.all.return_value = [dep_dead_1, dep_dead_2, dep_dead_3]

    def query(model):
        name = getattr(model, "__name__", str(model))
        if "FluxAppRegistration" in name:
            return reg_q
        return dep_q

    mock_db.query.side_effect = query

    service = FdmSyncService(mock_db)
    _run(service._reconcile_deployment_app_state())

    assert dep_live.is_active is True
    assert dep_dead_1.is_active is False
    assert dep_dead_2.is_active is False
    assert dep_dead_3.is_active is False
    mock_db.commit.assert_called_once()


# --- get_app: serving + active-filtered healthy count (review M-3) ---


def test_get_app_derives_serving_and_filters_active():
    """get_app must match list_apps: serving derived, and the healthy count
    filters on ACTIVE deployments. Phase 1 left get_app returning serving=False
    and a healthy count inflated by phantom-deactivated deployments."""
    from app.api.v1.endpoints import super_admin

    app = MagicMock(
        id=1,
        app_name="ch01",
        protocol_ports={},
        is_active=True,
        registered_by=None,
        last_discovery_at=None,
        last_discovery_ips=None,
    )
    deployments = [
        MagicMock(region="DE"),
        MagicMock(region="XX"),
    ]  # XX excluded from regions

    app_q = MagicMock()
    app_q.filter.return_value.first.return_value = app
    dep_q = MagicMock()
    dep_q.filter.return_value.all.return_value = deployments
    healthy_q = MagicMock()
    healthy_q.join.return_value.filter.return_value.count.return_value = 5

    mock_db = MagicMock()

    def query(model):
        name = getattr(model, "__name__", str(model))
        if "FluxAppRegistration" in name:
            return app_q
        if "FdmDeployment" in name:
            return dep_q
        return healthy_q

    mock_db.query.side_effect = query

    resp = _run(super_admin.get_app(1, mock_db, {}))

    assert resp.serving is True, "active app + >0 healthy => serving"
    assert (
        resp.healthy_instances == 5
    ), "healthy count must come from the active-filtered query"
    assert "XX" not in resp.regions, "XX placeholder must be excluded from regions"


def test_compute_app_health_matches_list_apps_and_get_app_shape():
    """The shared helper (Phase 4.7a) must return the exact 3-tuple both
    list_apps and get_app destructure: (regions, healthy_active, serving)."""
    from app.api.v1.endpoints import super_admin

    app = MagicMock(id=1, app_name="ch01", is_active=True)
    deployments = [MagicMock(region="DE"), MagicMock(region="XX")]

    dep_q = MagicMock()
    dep_q.filter.return_value.all.return_value = deployments
    healthy_q = MagicMock()
    healthy_q.join.return_value.filter.return_value.count.return_value = 5

    mock_db = MagicMock()

    def query(model):
        name = getattr(model, "__name__", str(model))
        if "FdmDeployment" in name:
            return dep_q
        return healthy_q

    mock_db.query.side_effect = query

    regions, healthy_active, serving = super_admin._compute_app_health(mock_db, app)

    assert regions == ["DE"], "XX placeholder must be excluded, real regions sorted"
    assert healthy_active == 5
    assert serving is True, "active app + >0 healthy => serving"
