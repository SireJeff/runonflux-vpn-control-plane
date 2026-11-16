from types import SimpleNamespace

import pytest

from app.services.usage.live_connections import (
    LiveConnectionError,
    SSHLiveConnectionAdapter,
    resolve_live_connection_adapter,
)


def test_resolve_live_connection_adapter_supported_protocols():
    assert resolve_live_connection_adapter("ssh") is not None
    assert resolve_live_connection_adapter("shadowsocks") is not None
    assert resolve_live_connection_adapter("vless") is not None
    assert resolve_live_connection_adapter("trojan") is not None
    assert resolve_live_connection_adapter("outline") is not None
    assert resolve_live_connection_adapter("http_proxy") is not None
    assert resolve_live_connection_adapter("unknown") is None


def test_ssh_live_adapter_normalizes_sessions(monkeypatch):
    adapter = SSHLiveConnectionAdapter()
    instance = SimpleNamespace(
        ip_address="127.0.0.1",
        protocol=SimpleNamespace(default_port=22, exposed_port=None),
    )

    monkeypatch.setattr(
        adapter,
        "fetch_payload",
        lambda _: {"users": [{"user_id": 7, "sessions": 3}]},
    )

    samples = adapter.collect(instance)
    assert len(samples) == 1
    assert samples[0].user_id == 7
    assert samples[0].active_connections == 3


def test_live_adapter_raises_on_invalid_payload(monkeypatch):
    adapter = SSHLiveConnectionAdapter()
    instance = SimpleNamespace(
        ip_address="127.0.0.1",
        protocol=SimpleNamespace(default_port=22, exposed_port=None),
    )

    monkeypatch.setattr(adapter, "fetch_payload", lambda _: {"users": "invalid"})
    with pytest.raises(LiveConnectionError):
        adapter.collect(instance)
