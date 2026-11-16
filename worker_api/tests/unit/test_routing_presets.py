import sys
from unittest.mock import MagicMock

# Stub cloudflare (optional SDK not installed in the unit env) before importing
# app modules. setdefault so we never clobber a mock another test installed.
sys.modules.setdefault("cloudflare", MagicMock())
sys.modules.setdefault("cloudflare.types", MagicMock())
sys.modules.setdefault("cloudflare.types.dns", MagicMock())

from app.services.credentials.routing_presets import (
    PRESET_CATALOG,
    PRESET_KEYS,
    build_singbox_routing,
)

PROXY_TAGS = ["🇩🇪 User VLESS", "🇳🇱 User Trojan"]


def test_preset_keys_match_catalog():
    assert PRESET_KEYS == frozenset(PRESET_CATALOG)
    assert PRESET_KEYS == {"block_ads", "block_porn", "iran_direct"}


def test_empty_rules_produce_no_routing():
    extra, route = build_singbox_routing({}, PROXY_TAGS)
    assert extra == []
    assert route is None


def test_disabled_shaped_but_empty_lists_produce_no_routing():
    rules = {"ban_domains": [], "allow_domains": [], "presets": {}}
    extra, route = build_singbox_routing(rules, PROXY_TAGS)
    assert extra == [] and route is None


def test_ban_domain_produces_block_rule_and_selector():
    rules = {"ban_domains": ["ads.com"], "allow_domains": [], "presets": {}}
    extra, route = build_singbox_routing(rules, PROXY_TAGS)
    tags = {o["tag"] for o in extra}
    assert "proxy" in tags and "direct" in tags
    # selector proxy lists every concrete tag, first is default
    selector = next(o for o in extra if o["tag"] == "proxy")
    assert selector["type"] == "selector"
    assert selector["outbounds"] == PROXY_TAGS
    assert route["final"] == "proxy"
    # a rule references ads.com as a domain_suffix and blocks it
    assert any("ads.com" in r.get("domain_suffix", []) for r in route["rules"])


def test_allow_domain_produces_direct_rule():
    rules = {"ban_domains": [], "allow_domains": ["bank.ir"], "presets": {}}
    _, route = build_singbox_routing(rules, PROXY_TAGS)
    direct_rules = [r for r in route["rules"] if "bank.ir" in r.get("domain_suffix", [])]
    assert direct_rules, "expected a direct rule for bank.ir"


def test_allow_rules_emitted_before_ban_rules():
    rules = {"ban_domains": ["x.com"], "allow_domains": ["y.com"], "presets": {}}
    _, route = build_singbox_routing(rules, PROXY_TAGS)
    order = [r.get("domain_suffix", []) for r in route["rules"]]
    y_idx = next(i for i, s in enumerate(order) if "y.com" in s)
    x_idx = next(i for i, s in enumerate(order) if "x.com" in s)
    assert y_idx < x_idx


def test_no_routing_when_only_domain_rules_has_no_rule_set_key():
    rules = {"ban_domains": ["ads.com"], "allow_domains": [], "presets": {}}
    _, route = build_singbox_routing(rules, PROXY_TAGS)
    assert "rule_set" not in route  # no presets → no rule_set array


def test_ban_preset_emits_rule_set_rule_and_remote_definition():
    rules = {"ban_domains": [], "allow_domains": [], "presets": {"block_ads": True}}
    _, route = build_singbox_routing(rules, PROXY_TAGS)
    # a reject rule references the geosite-category-ads-all rule_set tag
    ban_rules = [r for r in route["rules"] if r.get("action") == "reject"]
    assert any("geosite-category-ads-all" in r.get("rule_set", []) for r in ban_rules)
    # the remote rule_set definition is present under route.rule_set
    defs = {rs["tag"]: rs for rs in route.get("rule_set", [])}
    assert "geosite-category-ads-all" in defs
    d = defs["geosite-category-ads-all"]
    assert d["type"] == "remote" and d["format"] == "binary"
    assert d["url"].endswith("geosite-category-ads-all.srs")
    assert d["download_detour"] == "proxy"


def test_allow_preset_emits_multiple_rule_sets():
    rules = {"presets": {"iran_direct": True}}
    _, route = build_singbox_routing(rules, PROXY_TAGS)
    direct_rules = [
        r for r in route["rules"]
        if r.get("action") == "route" and r.get("outbound") == "direct"
    ]
    rs_tags = set()
    for r in direct_rules:
        rs_tags.update(r.get("rule_set", []))
    assert {"geosite-ir", "geoip-ir"} <= rs_tags
    defs = {rs["tag"] for rs in route.get("rule_set", [])}
    assert {"geosite-ir", "geoip-ir"} <= defs


def test_no_inline_geosite_or_geoip_fields_emitted():
    # Regression guard: inline geosite/geoip rule fields were removed in
    # sing-box 1.12. Presets must express geo matching via rule_set only.
    rules = {
        "presets": {"block_ads": True, "block_porn": True, "iran_direct": True},
        "ban_domains": ["x.com"],
        "allow_domains": ["y.com"],
    }
    _, route = build_singbox_routing(rules, PROXY_TAGS)
    for r in route["rules"]:
        assert "geosite" not in r
        assert "geoip" not in r


def test_rule_set_definitions_are_deduped():
    rules = {"presets": {"iran_direct": True}}
    _, route = build_singbox_routing(rules, PROXY_TAGS)
    tags = [rs["tag"] for rs in route.get("rule_set", [])]
    assert len(tags) == len(set(tags))


def test_preset_rule_set_rules_preserve_allow_before_ban():
    rules = {"presets": {"block_ads": True, "iran_direct": True}}
    _, route = build_singbox_routing(rules, PROXY_TAGS)
    actions = [r.get("action") for r in route["rules"]]
    # the direct (allow) preset rule precedes the reject (ban) preset rule
    first_direct = next(i for i, a in enumerate(actions) if a == "route")
    first_reject = next(i for i, a in enumerate(actions) if a == "reject")
    assert first_direct < first_reject


def test_disabled_preset_is_ignored():
    rules = {"presets": {"block_ads": False}}
    extra, route = build_singbox_routing(rules, PROXY_TAGS)
    assert extra == [] and route is None


def test_empty_proxy_tags_produces_no_routing():
    """Empty proxy_tags should never emit routing, even with rules defined."""
    rules = {"ban_domains": ["ads.com"], "allow_domains": [], "presets": {}}
    extra, route = build_singbox_routing(rules, [])
    assert extra == []
    assert route is None
