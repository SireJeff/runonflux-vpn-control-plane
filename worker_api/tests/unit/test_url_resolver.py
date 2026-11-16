"""Unit tests for URL resolver helpers.

Imports the real ``app.services.url_resolver`` module (loaded once by
tests/conftest.py's real ``app`` import). DB/TLD-selection lookups are
controlled per-test via ``unittest.mock.patch`` at the lookup sites, instead
of pre-installing stub modules in sys.modules.
"""
from unittest.mock import MagicMock, patch

from app.models.platform_settings import PlatformSetting
from app.services import url_resolver
from app.services.tlds.selection import NoActiveTld


def _mock_db_with_setting(key, value):
    """Mock DB session that returns a PlatformSetting row for the given key."""
    setting = PlatformSetting(key=key, value=value)
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = setting
    return mock_db


def _mock_db_with_no_setting():
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    return mock_db


def test_get_api_base_url_returns_setting_when_present():
    """If platform_settings has api_base_url, that value wins."""
    db = _mock_db_with_setting("api_base_url", "https://custom.api.example.com")
    assert url_resolver.get_api_base_url(db) == "https://custom.api.example.com"


def test_get_api_base_url_falls_back_to_fluxvpn_api_url():
    """If no setting, fall back to settings.FLUXVPN_API_URL (NOT USER_PORTAL_URL)."""
    db = _mock_db_with_no_setting()
    with patch.object(
        url_resolver.settings, "FLUXVPN_API_URL", "https://api.operator7.example.invalid"
    ):
        result = url_resolver.get_api_base_url(db)
    assert (
        result == "https://api.operator7.example.invalid"
    ), "get_api_base_url must fall back to FLUXVPN_API_URL, not USER_PORTAL_URL"


def test_get_api_base_url_ignores_empty_setting():
    """An empty platform_settings value should not override the fallback."""
    db = _mock_db_with_setting("api_base_url", "")
    with patch.object(
        url_resolver.settings, "FLUXVPN_API_URL", "https://api.operator7.example.invalid"
    ):
        assert url_resolver.get_api_base_url(db) == "https://api.operator7.example.invalid"


# ---------------------------------------------------------------------------
# Task 1.7 — per-admin effective TLD resolution (with legacy fallback)
# ---------------------------------------------------------------------------


def test_get_subscription_base_url_backward_compatible_no_admin_id():
    """admin_id omitted -> legacy platform_settings path (no service call)."""
    db = _mock_db_with_setting(
        "subscription_base_url", "https://legacy.sub.example.com"
    )
    assert (
        url_resolver.get_subscription_base_url(db)
        == "https://legacy.sub.example.com"
    )


def test_get_subscription_base_url_uses_effective_tld_when_admin_given():
    """admin_id given + effective TLD resolved -> https://{tld.domain}."""
    db = MagicMock()
    with patch.object(
        url_resolver.TldSelectionService,
        "resolve_effective",
        return_value=MagicMock(domain="eff.example.com"),
    ):
        assert (
            url_resolver.get_subscription_base_url(db, admin_id=7)
            == "https://eff.example.com"
        )


def test_get_subscription_base_url_falls_back_when_no_active_tld():
    """admin_id given but pool empty (NoActiveTld) -> legacy fallback."""
    db = _mock_db_with_setting(
        "subscription_base_url", "https://legacy.sub.example.com"
    )
    with patch.object(
        url_resolver.TldSelectionService,
        "resolve_effective",
        side_effect=NoActiveTld("subscription"),
    ):
        assert (
            url_resolver.get_subscription_base_url(db, admin_id=7)
            == "https://legacy.sub.example.com"
        )


# ---------------------------------------------------------------------------
# resolve_admin_panel_url — per-reseller admin-panel URL emitter
# ---------------------------------------------------------------------------


def test_resolve_admin_panel_url_effective_tld():
    """Effective admin_panel TLD -> (https url, host, is_fallback False)."""
    db = MagicMock()

    def _resolve_effective(admin_id, purpose):
        assert purpose == "admin_panel"
        return MagicMock(domain="panel.acme.info")

    with patch.object(
        url_resolver.TldSelectionService,
        "resolve_effective",
        side_effect=_resolve_effective,
        autospec=False,
    ):
        url, domain, is_fallback = url_resolver.resolve_admin_panel_url(db, 7)
    assert url == "https://panel.acme.info"
    assert domain == "panel.acme.info"
    assert is_fallback is False


def test_resolve_admin_panel_url_fallback_when_no_active_tld():
    """Empty pool (NoActiveTld) -> (USER_PORTAL_URL, None, is_fallback True)."""
    db = MagicMock()
    with patch.object(
        url_resolver.TldSelectionService,
        "resolve_effective",
        side_effect=NoActiveTld("admin_panel"),
    ), patch.object(
        url_resolver.settings, "USER_PORTAL_URL", "https://panel.operator5.example.invalid"
    ):
        url, domain, is_fallback = url_resolver.resolve_admin_panel_url(db, 7)
    assert url == "https://panel.operator5.example.invalid"  # mocked settings.USER_PORTAL_URL
    assert domain is None
    assert is_fallback is True
