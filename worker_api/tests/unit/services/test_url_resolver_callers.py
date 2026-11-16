"""Task 3 — pin that url_resolver routes through the per-admin effective TLD when
admin_id is passed, and falls back to platform_settings/env when admin_id is None.

Mock-based (no DB). Complements Phase 1's test_url_resolver.py; this pins the
behavior the caller-wiring relies on: threading user.admin_id into the resolver
makes it go per-admin. The wiring itself is verified by grep (no unthreaded
get_*_base_url(db) calls remain) + clean app import.
"""
from unittest.mock import MagicMock


def test_subscription_url_uses_admin_effective(monkeypatch):
    from app.services import url_resolver

    fake_tld = MagicMock()
    fake_tld.domain = "sub.effective.example"
    fake_svc = MagicMock()
    fake_svc.return_value.resolve_effective.return_value = fake_tld
    monkeypatch.setattr(url_resolver, "TldSelectionService", fake_svc)

    url = url_resolver.get_subscription_base_url(MagicMock(), admin_id=42)

    assert url == "https://sub.effective.example"
    fake_svc.return_value.resolve_effective.assert_called_once_with(42, "subscription")


def test_subscription_url_legacy_fallback_when_admin_id_none(monkeypatch):
    """admin_id=None short-circuits _effective_domain before TldSelectionService is
    touched, so the platform_settings/env fallback path is used."""
    from app.services import url_resolver

    fake_svc = MagicMock()
    monkeypatch.setattr(url_resolver, "TldSelectionService", fake_svc)

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    url = url_resolver.get_subscription_base_url(db, admin_id=None)

    fake_svc.assert_not_called()  # never reached _effective_domain's service call
    assert url is not None  # settings.FLUXVPN_API_URL fallback
