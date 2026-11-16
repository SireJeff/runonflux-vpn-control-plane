"""Phase 3 Task 3.1: FluxAppRegistration spec columns + alembic migration.

App-root inside the VM container is /app (worker_api build context). parents[2]
of /app/tests/unit/<this>.py == /app.
"""
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]  # /app in-container, worker_api/ locally
VERSIONS = APP_ROOT / "alembic" / "versions"


def test_flux_app_registration_has_spec_columns():
    """The model must declare the 5 spec-awareness columns (Goal 1 plumbing)."""
    from app.models.flux_app_registration import FluxAppRegistration

    cols = set(FluxAppRegistration.__table__.columns.keys())
    expected = {
        "expected_instances",
        "spec_components",
        "spec_geolocation",
        "last_spec_fetched_at",
        "last_spec_status",
    }
    missing = expected - cols
    assert not missing, f"FluxAppRegistration missing spec columns: {missing}"


def test_spec_migration_chains_off_current_head_and_adds_columns():
    """The new migration must chain off the current head (20260626_001) and add
    all 5 columns on flux_app_registrations. (Migration is applied on prod at
    deploy time with pg_dump; this is the structural proof.)"""
    mig = VERSIONS / "20260717_001_flux_app_spec_columns.py"
    assert mig.exists(), f"migration file missing: {mig}"
    src = mig.read_text(encoding="utf-8")
    assert 'revision = "20260717_001"' in src, "revision id must be 20260717_001"
    assert (
        'down_revision = "20260626_001"' in src
    ), "must chain off current head 20260626_001"
    assert "flux_app_registrations" in src, "must target flux_app_registrations"
    for col in (
        "expected_instances",
        "spec_components",
        "spec_geolocation",
        "last_spec_fetched_at",
        "last_spec_status",
    ):
        assert col in src, f"migration must reference column {col}"
