"""main.py startup hook: bot manager init failure must be visible at /health."""
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def _get_main_mod():
    """Import the real app.main module and return it."""
    import app.main as m

    return m


def test_health_reports_degraded_when_bot_manager_init_fails():
    """If _init_reseller_bot_manager caught an exception, /health must say degraded."""
    m = _get_main_mod()
    # Simulate failed init by setting module-level vars directly.
    m._BOT_MANAGER_STATUS = "failed"
    m._BOT_MANAGER_ERROR = "missing env var FLUX_API_KEY"

    client = TestClient(m.app, raise_server_exceptions=False)
    resp = client.get("/health")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["status"] == "degraded", f"Expected 'degraded', got {body}"
    assert body["bot_manager"]["status"] == "failed"
    assert "missing env var FLUX_API_KEY" in body["bot_manager"]["error"]


def test_health_reports_healthy_when_bot_manager_init_succeeds():
    """If _init_reseller_bot_manager succeeded, /health must say healthy."""
    m = _get_main_mod()
    m._BOT_MANAGER_STATUS = "ok"
    m._BOT_MANAGER_ERROR = None

    client = TestClient(m.app, raise_server_exceptions=False)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["bot_manager"]["status"] == "ok"
    assert body["bot_manager"]["error"] is None


def test_health_returns_200_even_when_bot_manager_unknown():
    """When bot manager status is 'unknown', /health must still be 200 (degraded)."""
    m = _get_main_mod()
    m._BOT_MANAGER_STATUS = "unknown"
    m._BOT_MANAGER_ERROR = None

    client = TestClient(m.app, raise_server_exceptions=False)
    resp = client.get("/health")
    assert (
        resp.status_code == 200
    ), "Docker HEALTHCHECK needs HTTP 200 even when degraded"
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["bot_manager"]["status"] == "unknown"


def test_health_includes_bot_manager_key_structure():
    """Response must always include bot_manager sub-object with status and error keys."""
    m = _get_main_mod()
    for status_val in ("ok", "failed", "unknown"):
        m._BOT_MANAGER_STATUS = status_val
        m._BOT_MANAGER_ERROR = "test error" if status_val != "ok" else None

        client = TestClient(m.app, raise_server_exceptions=False)
        resp = client.get("/health")
        body = resp.json()
        assert (
            "bot_manager" in body
        ), f"Missing bot_manager key when status={status_val}"
        assert "status" in body["bot_manager"]
        assert "error" in body["bot_manager"]
