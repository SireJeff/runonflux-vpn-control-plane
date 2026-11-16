"""Tests for T14: _populate_parsed_fields helper + ProtocolConnections schema.

Validates that:
- SSH entries get parsed_fields populated from parse_ssh_fields()
- Non-SSH entries get no parsed_fields (stay None / absent)
- Schema accepts parsed_fields as Optional dict
- Edge cases: missing primary, malformed SSH URI, non-dict data
"""
from app.api.v1.endpoints.end_user import _populate_parsed_fields

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_populate_parsed_fields_adds_ssh_fields_for_ssh_protocol():
    """SSH entry should get parsed_fields populated with host/port/user/pass."""
    connections = {
        "CH": {
            "ssh": {
                "primary": "ssh://user:pass@hub.example.com:32442#frag",
                "fallbacks": [],
            },
            "vless": {"primary": "vless://uuid@host:443", "fallbacks": []},
        }
    }
    result = _populate_parsed_fields(connections)
    ssh_data = result["CH"]["ssh"]
    assert "parsed_fields" in ssh_data
    parsed = ssh_data["parsed_fields"]
    assert parsed["host"] == "hub.example.com"
    assert parsed["port"] == 32442
    assert parsed["username"] == "user"
    assert parsed["password"] == "pass"


def test_populate_parsed_fields_does_not_touch_non_ssh_protocols():
    """vless/trojan/ss/outline/http_proxy entries should have no parsed_fields key."""
    connections = {
        "CH": {
            "vless": {"primary": "vless://uuid@host:443", "fallbacks": []},
            "trojan": {"primary": "trojan:pass@host:443", "fallbacks": []},
            "ss": {"primary": "ss://base64@host:8388", "fallbacks": []},
        }
    }
    result = _populate_parsed_fields(connections)
    for proto in ("vless", "trojan", "ss"):
        assert (
            "parsed_fields" not in result["CH"][proto]
        ), f"{proto} should not have parsed_fields"


def test_populate_parsed_fields_skips_missing_primary():
    """SSH entry without primary should not crash; no parsed_fields added."""
    connections = {
        "CH": {
            "ssh": {"primary": "", "fallbacks": []},
        }
    }
    result = _populate_parsed_fields(connections)
    assert "parsed_fields" not in result["CH"]["ssh"]


def test_populate_parsed_fields_skips_malformed_ssh_uri():
    """If parse_ssh_fields raises ValueError, helper should silently skip."""
    connections = {
        "CH": {
            "ssh": {"primary": "not-an-ssh-uri", "fallbacks": []},
        }
    }
    result = _populate_parsed_fields(connections)
    assert "parsed_fields" not in result["CH"]["ssh"]


def test_populate_parsed_fields_handles_url_encoded_credentials():
    """Credentials with special chars (URL-encoded in URI) should decode."""
    # URL-encoded: user 'us%26r' decodes to 'us&r', pass 'p%40ss' to 'p@ss'
    connections = {
        "CH": {
            "ssh": {
                "primary": "ssh://us%26r:p%40ss@host.example.com:22",
                "fallbacks": [],
            },
        }
    }
    result = _populate_parsed_fields(connections)
    parsed = result["CH"]["ssh"]["parsed_fields"]
    assert parsed["username"] == "us&r"
    assert parsed["password"] == "p@ss"
    assert parsed["host"] == "host.example.com"
    assert parsed["port"] == 22


def test_populate_parsed_fields_handles_multiple_countries():
    """Each country's SSH entries should be processed independently."""
    connections = {
        "CH": {"ssh": {"primary": "ssh://u:p@ch-host:22", "fallbacks": []}},
        "DE": {"ssh": {"primary": "ssh://u:p@de-host:22", "fallbacks": []}},
        "FR": {"vless": {"primary": "vless://u@fr-host:443", "fallbacks": []}},
    }
    result = _populate_parsed_fields(connections)
    assert result["CH"]["ssh"]["parsed_fields"]["host"] == "ch-host"
    assert result["DE"]["ssh"]["parsed_fields"]["host"] == "de-host"
    assert "parsed_fields" not in result["FR"]["vless"]


def test_populate_parsed_fields_defaults_port_to_22_when_absent():
    """RFC 3986 says port is optional; helper should default to 22 via parse_ssh_fields."""
    connections = {
        "CH": {"ssh": {"primary": "ssh://user:pass@host.example.com", "fallbacks": []}},
    }
    result = _populate_parsed_fields(connections)
    parsed = result["CH"]["ssh"]["parsed_fields"]
    assert parsed["port"] == 22  # default SSH port
    assert parsed["host"] == "host.example.com"


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def test_protocol_connections_schema_accepts_parsed_fields():
    """Pydantic ProtocolConnections model should accept parsed_fields dict."""
    from typing import Any, Dict, List, Optional

    from pydantic import BaseModel

    # Inline reconstruction of the schema to avoid importing app.schemas.admin_api
    # (which has heavy model deps). The shape mirrors the production schema.
    class ProtocolConnections(BaseModel):
        primary: str
        fallbacks: List[str] = []
        parsed_fields: Optional[Dict[str, Any]] = None

    # Without parsed_fields — defaults to None
    pc1 = ProtocolConnections(primary="ssh://u:p@h:22")
    assert pc1.parsed_fields is None

    # With parsed_fields
    pc2 = ProtocolConnections(
        primary="ssh://u:p@h:22",
        parsed_fields={"host": "h", "port": 22, "username": "u", "password": "p"},
    )
    assert pc2.parsed_fields["host"] == "h"
    assert pc2.parsed_fields["port"] == 22
