"""Pure sing-box routing translation for per-reseller ban/allow rules.

Targets modern sing-box (>= 1.11): rule actions
(`{"action": "reject"}` / `{"action": "route", "outbound": "direct"}`) and
**remote `rule_set`** for the curated geosite/geoip presets.

Why rule_set and not inline `geosite`/`geoip`: those fields were deprecated in
sing-box 1.8 and REMOVED in 1.12 (verified 2026-08-19 with `sing-box check` on
v1.13.19 — an inline-geosite config is rejected, a rule_set config is valid).
Current Hiddify/Throne cores ship >= 1.12, so presets MUST use rule_set.

VERSION-SENSITIVE CONSTANTS (the action forms + the rule_set catalog) live only
in this file — a single swap point if a future core changes the schema again.
"""

from typing import Optional

# --- version-sensitive action forms (single swap point) ---


def _block_action() -> dict:
    """Rule fragment that drops a connection (sing-box >= 1.11)."""
    return {"action": "reject"}


def _direct_action() -> dict:
    """Rule fragment that routes to the bypass (direct) outbound."""
    return {"action": "route", "outbound": "direct"}


# --- remote rule-set sources (official SagerNet rule-set branches) ---

_GEOSITE_BASE = "https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set"
_GEOIP_BASE = "https://raw.githubusercontent.com/SagerNet/sing-geoip/rule-set"


def _geosite_ruleset(category: str) -> dict:
    """A remote sing-box rule_set definition for a geosite category.

    download_detour="proxy" so the .srs is fetched THROUGH the VPN (the
    reseller's users may be in a region where the raw source is blocked)."""
    return {
        "type": "remote",
        "tag": f"geosite-{category}",
        "format": "binary",
        "url": f"{_GEOSITE_BASE}/geosite-{category}.srs",
        "download_detour": "proxy",
    }


def _geoip_ruleset(code: str) -> dict:
    """A remote sing-box rule_set definition for a geoip country code."""
    return {
        "type": "remote",
        "tag": f"geoip-{code}",
        "format": "binary",
        "url": f"{_GEOIP_BASE}/geoip-{code}.srs",
        "download_detour": "proxy",
    }


# --- preset catalog ---
# Each preset lands on the "ban" (reject) or "allow" (direct) list and pulls in
# one or more remote rule_sets. build_singbox_routing() emits, per list, a
# single rule referencing the collected rule_set tags, plus the deduped
# rule_set definitions under route.rule_set.

PRESET_CATALOG: dict[str, dict] = {
    "block_ads": {
        "list": "ban",
        "rule_sets": [_geosite_ruleset("category-ads-all")],
    },
    "block_porn": {
        "list": "ban",
        "rule_sets": [_geosite_ruleset("category-porn")],
    },
    "iran_direct": {
        "list": "allow",
        "rule_sets": [_geosite_ruleset("ir"), _geoip_ruleset("ir")],
    },
}

PRESET_KEYS = frozenset(PRESET_CATALOG)


def _clean_domains(values) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values or []:
        if not isinstance(v, str):
            continue
        d = v.strip().lower()
        if d and d not in seen:
            seen.add(d)
            out.append(d)
    return out


def build_singbox_routing(
    rules: dict, proxy_tags: list[str]
) -> tuple[list[dict], Optional[dict]]:
    """Translate a reseller rules dict into (extra_outbounds, route).

    Returns ([], None) when there is nothing to route (no proxy tags, or no
    allow/ban entries), so callers emit the unchanged bare-outbounds output.
    When routing IS emitted, route may carry a "rule_set" list (the remote
    definitions any enabled presets reference).
    """
    # Guard: empty proxy_tags means no routing at all (can't build a selector
    # with empty outbounds, and rule_set download_detour="proxy" needs it).
    if not proxy_tags:
        return [], None

    rules = rules or {}
    allow_domains = _clean_domains(rules.get("allow_domains"))
    ban_domains = _clean_domains(rules.get("ban_domains"))
    presets = rules.get("presets") or {}
    enabled_presets = [k for k in PRESET_CATALOG if presets.get(k) is True]

    allow_presets = [k for k in enabled_presets if PRESET_CATALOG[k]["list"] == "allow"]
    ban_presets = [k for k in enabled_presets if PRESET_CATALOG[k]["list"] == "ban"]

    has_anything = allow_domains or ban_domains or allow_presets or ban_presets
    if not has_anything:
        return [], None

    rule_sets: list[dict] = []
    _seen_rs: set[str] = set()

    def _collect(preset_keys: list[str]) -> list[str]:
        """Register each preset's rule_set defs (deduped) and return their tags."""
        tags: list[str] = []
        for key in preset_keys:
            for rs in PRESET_CATALOG[key]["rule_sets"]:
                if rs["tag"] not in _seen_rs:
                    _seen_rs.add(rs["tag"])
                    rule_sets.append(rs)
                if rs["tag"] not in tags:
                    tags.append(rs["tag"])
        return tags

    route_rules: list[dict] = []
    # Allow rules FIRST (allow overrides ban).
    if allow_domains:
        route_rules.append({"domain_suffix": allow_domains, **_direct_action()})
    if allow_presets:
        route_rules.append({"rule_set": _collect(allow_presets), **_direct_action()})
    # Ban rules.
    if ban_domains:
        route_rules.append({"domain_suffix": ban_domains, **_block_action()})
    if ban_presets:
        route_rules.append({"rule_set": _collect(ban_presets), **_block_action()})

    extra_outbounds: list[dict] = [
        {"type": "selector", "tag": "proxy", "outbounds": list(proxy_tags),
         "default": proxy_tags[0] if proxy_tags else None},
        {"type": "direct", "tag": "direct"},
    ]
    # Strip a None default (selector.default is optional).
    if extra_outbounds[0]["default"] is None:
        del extra_outbounds[0]["default"]

    route: dict = {"rules": route_rules, "final": "proxy"}
    if rule_sets:
        route["rule_set"] = rule_sets
    return extra_outbounds, route
