"""Fix 2: global ValueError->400 and ConfigurationError->500 handlers,
plus dns_provider raising ConfigurationError for server misconfig."""

import pytest

from app.core.exceptions import ConfigurationError
from app.services.fdm.dns_provider import create_dns_client


def test_value_error_handler_returns_400(app, client):
    @app.get("/__test_value_error__")
    def _boom():
        raise ValueError("boom")

    resp = client.get("/__test_value_error__")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "boom"


def test_configuration_error_handler_returns_500(app, client):
    @app.get("/__test_config_error__")
    def _boom():
        raise ConfigurationError("misconfigured")

    resp = client.get("/__test_config_error__")
    assert resp.status_code == 500


def test_unknown_dns_provider_raises_configuration_error():
    with pytest.raises(ConfigurationError):
        create_dns_client(provider="bogus", domain="example.com")
