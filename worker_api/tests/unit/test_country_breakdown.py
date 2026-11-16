"""Tests for ConnectionStringService.generate_country_breakdown."""
from unittest.mock import MagicMock

from app.services.credentials.connection_string_service import ConnectionStringService


def test_country_breakdown_returns_dict_keyed_by_country_code():
    """Output should be {country_code: {protocol_name: {primary: uri}}}."""
    svc = ConnectionStringService(db=MagicMock())

    # Mock the underlying generate_connection_strings to return predictable data
    svc.generate_connection_strings = MagicMock(
        return_value={
            "NL": {
                "ssh": {"primary": "ssh://u:p@h:1"},
                "vless": {"primary": "vless://u@h:2"},
            },
            "CH": {"ssh": {"primary": "ssh://u:p@h2:1"}},
        }
    )

    user = MagicMock()
    result = svc.generate_country_breakdown(user, macro_region="eu")

    assert "NL" in result
    assert "CH" in result
    assert result["NL"]["ssh"]["primary"] == "ssh://u:p@h:1"
    assert result["NL"]["vless"]["primary"] == "vless://u@h:2"


def test_country_breakdown_passes_increment_load_false():
    """generate_connection_strings should be called with increment_load=False
    (we're just displaying, not actually load-balancing)."""
    svc = ConnectionStringService(db=MagicMock())
    svc.generate_connection_strings = MagicMock(return_value={})

    user = MagicMock()
    svc.generate_country_breakdown(user, macro_region="eu")

    svc.generate_connection_strings.assert_called_once()
    args, kwargs = svc.generate_connection_strings.call_args
    assert kwargs.get("increment_load") is False


def test_country_breakdown_empty_when_no_countries():
    svc = ConnectionStringService(db=MagicMock())
    svc.generate_connection_strings = MagicMock(return_value={})
    user = MagicMock()
    result = svc.generate_country_breakdown(user, macro_region="eu")
    assert result == {}
