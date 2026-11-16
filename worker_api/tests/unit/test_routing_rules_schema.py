import sys
from unittest.mock import MagicMock

# Mock cloudflare before importing app modules
sys.modules.setdefault('cloudflare', MagicMock())
sys.modules.setdefault('cloudflare.types', MagicMock())
sys.modules.setdefault('cloudflare.types.dns', MagicMock())

import pytest
from pydantic import ValidationError

from app.schemas.routing_rules import RoutingRulesUpdate


def test_valid_payload_normalizes_domains():
    m = RoutingRulesUpdate(
        is_enabled=True,
        ban_domains=["  Ads.COM ", "ads.com", "x.io"],
        allow_domains=["Bank.IR"],
        presets={"iran_direct": True},
    )
    assert m.ban_domains == ["ads.com", "x.io"]  # lowered, stripped, deduped
    assert m.allow_domains == ["bank.ir"]
    assert m.presets == {"iran_direct": True}


def test_rejects_domain_with_scheme_or_path():
    with pytest.raises(ValidationError):
        RoutingRulesUpdate(is_enabled=True, ban_domains=["https://x.com"],
                           allow_domains=[], presets={})
    with pytest.raises(ValidationError):
        RoutingRulesUpdate(is_enabled=True, ban_domains=["x.com/path"],
                           allow_domains=[], presets={})
    with pytest.raises(ValidationError):
        RoutingRulesUpdate(is_enabled=True, ban_domains=["bad domain"],
                           allow_domains=[], presets={})


def test_rejects_unknown_preset_key():
    with pytest.raises(ValidationError):
        RoutingRulesUpdate(is_enabled=True, ban_domains=[], allow_domains=[],
                           presets={"not_a_preset": True})


def test_empty_lists_allowed():
    m = RoutingRulesUpdate(is_enabled=False, ban_domains=[], allow_domains=[], presets={})
    assert m.ban_domains == [] and m.presets == {}
