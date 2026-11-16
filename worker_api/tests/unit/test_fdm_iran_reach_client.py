"""CheckHostClient HTTP contract, using httpx.MockTransport (no respx: CI
doesn't install it)."""

import asyncio

import httpx

from app.services.fdm.iran_reach import CheckHostClient

NODES = ["ir1.node.check-host.net", "de1.node.check-host.net"]


def _client(handler):
    """A CheckHostClient whose requests go to handler; returns (client, seen)."""
    seen = []

    def record(request):
        seen.append(request)
        return handler(request)

    return CheckHostClient(transport=httpx.MockTransport(record)), seen


def test_submit_sends_target_nodes_and_a_browser_user_agent():
    client, seen = _client(
        lambda r: httpx.Response(200, json={"ok": 1, "request_id": "abc123"})
    )

    rid = asyncio.run(client.submit_tcp("1.2.3.4:30519", NODES))

    assert rid == "abc123"
    req = seen[-1]
    assert req.url.host == "check-host.net"
    assert req.url.path == "/check-tcp"
    assert req.url.params.get_list("host") == ["1.2.3.4:30519"]
    assert req.url.params.get_list("node") == NODES
    assert req.headers["Accept"] == "application/json"
    # check-host answers Python's default UA with HTTP 403.
    assert req.headers["User-Agent"].startswith("Mozilla/5.0")


def test_submit_returns_none_when_rate_limited():
    client, _ = _client(lambda r: httpx.Response(429, text="Too many requests"))
    assert asyncio.run(client.submit_tcp("1.2.3.4:1", NODES)) is None


def test_submit_returns_none_on_network_error():
    def boom(request):
        raise httpx.ConnectTimeout("boom", request=request)

    client, _ = _client(boom)
    assert asyncio.run(client.submit_tcp("1.2.3.4:1", NODES)) is None


def test_fetch_result_returns_the_per_node_dict():
    payload = {"ir1.node.check-host.net": [{"error": "Connection timed out"}]}
    client, seen = _client(lambda r: httpx.Response(200, json=payload))
    assert asyncio.run(client.fetch_result("abc123")) == payload
    assert seen[-1].url.path == "/check-result/abc123"


def test_fetch_result_returns_none_on_non_json_body():
    client, _ = _client(lambda r: httpx.Response(200, text="<html>"))
    assert asyncio.run(client.fetch_result("abc123")) is None
