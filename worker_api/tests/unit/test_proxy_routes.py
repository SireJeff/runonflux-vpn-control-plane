"""Unit tests for the dynamic Traefik router writer (proxy_routes).

Traefik's static config only routes a fixed hostname set, so a newly onboarded
subscription/dashboard/admin_panel TLD had DNS but no router/cert and 404'd.
proxy_routes writes a per-TLD file-provider config on activation so the host is
actually served. These tests pin the rendered config + the fail-open behavior.
Pure/local — no network, no Traefik.
"""
import os

import pytest

from app.services.tlds import proxy_routes


def test_slug_is_filesystem_safe():
    assert proxy_routes._slug("Sub.Example.com") == "tld-sub-example-com"
    assert proxy_routes._slug("a_b--c.io") == "tld-a-b-c-io"


def test_render_subscription_router_points_at_worker_api():
    cfg = proxy_routes.render_router_config("sub.example.com", "subscription")
    assert "Host(`sub.example.com`)" in cfg
    assert "tld-sub-example-com:" in cfg
    assert "certResolver: letsencrypt" in cfg
    assert "- websecure" in cfg
    assert "http://worker-api:8080" in cfg


def test_render_dashboard_and_admin_panel_point_at_admin_dashboard():
    for purpose in ("dashboard", "admin_panel"):
        cfg = proxy_routes.render_router_config("x.example.com", purpose)
        assert "http://admin-dashboard:3000" in cfg


def test_register_skips_fdm_purpose(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAEFIK_DYNAMIC_DIR", str(tmp_path))
    assert proxy_routes.register_route("node.daric.link", "fdm") is False
    assert list(tmp_path.iterdir()) == []


def test_register_skips_when_dir_unset(monkeypatch):
    monkeypatch.setenv("TRAEFIK_DYNAMIC_DIR", "")
    assert proxy_routes.register_route("sub.example.com", "subscription") is False


def test_register_and_deregister_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAEFIK_DYNAMIC_DIR", str(tmp_path))

    assert proxy_routes.register_route("sub.example.com", "subscription") is True
    path = tmp_path / "tld-sub-example-com.yml"
    assert path.exists()
    assert "Host(`sub.example.com`)" in path.read_text(encoding="utf-8")
    # no partial temp file left behind
    assert not any(p.name.endswith(".tmp") for p in tmp_path.iterdir())

    # idempotent re-register
    assert proxy_routes.register_route("sub.example.com", "subscription") is True

    assert proxy_routes.deregister_route("sub.example.com") is True
    assert not path.exists()
    # deregister of an absent route is a no-op (False), never raises
    assert proxy_routes.deregister_route("sub.example.com") is False


def test_register_returns_false_on_missing_dir(monkeypatch):
    monkeypatch.setenv("TRAEFIK_DYNAMIC_DIR", os.path.join("does", "not", "exist"))
    assert proxy_routes.register_route("sub.example.com", "subscription") is False
