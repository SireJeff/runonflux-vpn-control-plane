from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints import admin_api
from app.core.auth.role_dependencies import require_admin
from app.core.database import get_db


def _client(resolver):
    app = FastAPI()
    app.include_router(admin_api.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: MagicMock()
    app.dependency_overrides[require_admin] = lambda: {"id": 5, "role": "admin"}
    admin_api.resolve_admin_panel_url = resolver  # module-level name, monkeypatched
    return TestClient(app)


def test_panel_url_returns_effective(monkeypatch):
    monkeypatch.setattr(
        admin_api,
        "resolve_admin_panel_url",
        lambda db, admin_id: ("https://panel.acme.info", "panel.acme.info", False),
    )
    client = _client(admin_api.resolve_admin_panel_url)
    body = client.get("/api/v1/admin/panel-url").json()
    assert body == {
        "panel_url": "https://panel.acme.info",
        "domain": "panel.acme.info",
        "is_fallback": False,
    }


def test_panel_url_returns_fallback(monkeypatch):
    monkeypatch.setattr(
        admin_api,
        "resolve_admin_panel_url",
        lambda db, admin_id: ("https://panel.operator5.example.invalid", None, True),
    )
    client = _client(admin_api.resolve_admin_panel_url)
    body = client.get("/api/v1/admin/panel-url").json()
    assert body == {
        "panel_url": "https://panel.operator5.example.invalid",
        "domain": None,
        "is_fallback": True,
    }
