from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.services.usage.adapters import (
    SSHUsageAdapter,
    UsageAdapterError,
    resolve_usage_adapter,
)


def test_resolve_usage_adapter_supports_phase1_protocols():
    assert resolve_usage_adapter("ssh") is not None
    assert resolve_usage_adapter("shadowsocks") is not None
    assert resolve_usage_adapter("vless") is not None
    assert resolve_usage_adapter("trojan") is not None
    assert resolve_usage_adapter("outline") is not None
    assert resolve_usage_adapter("http_proxy") is not None
    assert resolve_usage_adapter("unsupported") is None


def test_ssh_adapter_normalizes_protocol_specific_fields(monkeypatch):
    adapter = SSHUsageAdapter()
    instance = SimpleNamespace(
        ip_address="127.0.0.1",
        protocol=SimpleNamespace(default_port=22, exposed_port=None),
    )

    payload = {
        "records": [
            {
                "user_id": 100,
                "upload_bytes": 10,
                "download_bytes": 20,
                "connected_at": datetime.now(timezone.utc)
                .replace(tzinfo=None)
                .isoformat(),
            }
        ]
    }
    monkeypatch.setattr(adapter, "fetch_payload", lambda _: payload)

    records = adapter.collect(instance)

    assert len(records) == 1
    assert records[0].user_id == 100
    assert records[0].bytes_uploaded == 10
    assert records[0].bytes_downloaded == 20


def test_adapter_raises_on_invalid_payload(monkeypatch):
    adapter = SSHUsageAdapter()
    instance = SimpleNamespace(
        ip_address="127.0.0.1",
        protocol=SimpleNamespace(default_port=22, exposed_port=None),
    )

    monkeypatch.setattr(adapter, "fetch_payload", lambda _: {"records": "bad"})

    with pytest.raises(UsageAdapterError):
        adapter.collect(instance)
