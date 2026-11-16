"""Phase 3 Task 3.2: FluxSpecFetcher parses /apps/appspecifications/{app}."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.services.flux.spec_fetcher import FluxSpecFetcher


def _run(coro):
    return asyncio.run(coro)


def _ch01_payload():
    """Representative appspecifications shape (ch01 live probe, design §8).
    Wrapped in the standard {status, data} envelope; fetcher must unwrap."""
    return {
        "status": "success",
        "data": {
            "instances": 6,
            "version": 8,
            "compose": [
                {"name": "ssh", "ram": 200, "cpu": 0.2, "hdd": 1, "ports": [31022]},
                {
                    "name": "shadowsocks",
                    "ram": 300,
                    "cpu": 0.2,
                    "hdd": 1,
                    "ports": [31080],
                },
                {"name": "vless", "ram": 200, "cpu": 0.2, "hdd": 1, "ports": [31443]},
                {"name": "trojan", "ram": 200, "cpu": 0.2, "hdd": 1, "ports": [31444]},
                {"name": "outline", "ram": 200, "cpu": 0.2, "hdd": 1, "ports": [31090]},
                {
                    "name": "httpproxy",
                    "ram": 200,
                    "cpu": 0.2,
                    "hdd": 1,
                    "ports": [3180],
                },
            ],
            "geolocation": ["EU"],
        },
    }


def test_fetch_spec_parses_instances_and_components():
    client = MagicMock()
    client._request = AsyncMock(return_value=_ch01_payload())
    spec = _run(FluxSpecFetcher(client).fetch_spec("ch01"))
    assert spec is not None
    assert spec["instances"] == 6
    assert len(spec["components"]) == 6
    assert {c["name"] for c in spec["components"]} == {
        "ssh",
        "shadowsocks",
        "vless",
        "trojan",
        "outline",
        "httpproxy",
    }
    assert spec["components"][0]["ports"] == [31022]
    assert spec["geolocation"] == ["EU"]


def test_fetch_spec_returns_none_on_failure():
    """A fetch exception must degrade to None (keep last known expected), never raise."""
    from app.services.flux.client import FluxCloudAPIException

    client = MagicMock()
    client._request = AsyncMock(side_effect=FluxCloudAPIException("boom"))
    assert _run(FluxSpecFetcher(client).fetch_spec("ch01")) is None


def test_fetch_spec_uses_public_unauthenticated_request():
    """appspecifications is PUBLIC — fetch must pass authenticated=False."""
    client = MagicMock()
    client._request = AsyncMock(return_value=_ch01_payload())
    _run(FluxSpecFetcher(client).fetch_spec("ch01"))
    client._request.assert_awaited_once()
    assert client._request.call_args.kwargs.get("authenticated") is False
    assert client._request.call_args.args[0] == "GET"
    assert "/apps/appspecifications/ch01" in client._request.call_args.args[1]
