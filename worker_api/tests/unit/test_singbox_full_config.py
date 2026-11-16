"""ConnectionStringService.generate_singbox_full_config: wire per-reseller
routing rules into the sing-box subscription payload with a backward-compat gate.

No effective rules  -> (False, bare_outbounds_list)  — unchanged behavior.
Rules present       -> (True, {"outbounds": [...], "route": {...}}).

The two dependencies are monkeypatched so no real DB rows are needed:
  - svc.generate_all_region_singbox_outbounds -> the concrete proxy outbounds
  - RoutingRulesService.get_effective_rules   -> the effective rules dict
"""
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

# Mock cloudflare before importing app modules (mirrors sibling unit tests).
sys.modules.setdefault("cloudflare", MagicMock())
sys.modules.setdefault("cloudflare.types", MagicMock())
sys.modules.setdefault("cloudflare.types.dns", MagicMock())

import pytest

from app.services.credentials.connection_string_service import ConnectionStringService


@pytest.fixture
def svc_and_user(db_session):
    svc = ConnectionStringService(db_session)
    user = SimpleNamespace(admin_id=42)
    return svc, user


def test_no_rules_returns_bare_outbounds(monkeypatch, svc_and_user):
    svc, user = svc_and_user
    monkeypatch.setattr(
        svc, "generate_all_region_singbox_outbounds",
        lambda u: [{"tag": "A"}, {"tag": "B"}],
    )
    monkeypatch.setattr(
        "app.services.credentials.connection_string_service."
        "RoutingRulesService.get_effective_rules", lambda self, admin_id: {})
    is_full, payload = svc.generate_singbox_full_config(user)
    assert is_full is False
    assert payload == [{"tag": "A"}, {"tag": "B"}]


def test_rules_return_full_config(monkeypatch, svc_and_user):
    svc, user = svc_and_user
    monkeypatch.setattr(
        svc, "generate_all_region_singbox_outbounds",
        lambda u: [{"tag": "A"}, {"tag": "B"}],
    )
    monkeypatch.setattr(
        "app.services.credentials.connection_string_service."
        "RoutingRulesService.get_effective_rules",
        lambda self, admin_id: {"ban_domains": ["ads.com"], "allow_domains": [],
                                "presets": {}})
    is_full, payload = svc.generate_singbox_full_config(user)
    assert is_full is True
    assert isinstance(payload, dict)
    tags = {o["tag"] for o in payload["outbounds"]}
    assert {"A", "B", "proxy", "direct"} <= tags   # concrete + synthetic
    assert payload["route"]["final"] == "proxy"
    assert any("ads.com" in r.get("domain_suffix", []) for r in payload["route"]["rules"])
