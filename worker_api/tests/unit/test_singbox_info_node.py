from datetime import datetime
from types import SimpleNamespace
from app.services.credentials.connection_string_service import ConnectionStringService

_GB = 1024 ** 3

class _StubUser(SimpleNamespace):
    pass

def _svc_with(monkeypatch, outbounds, rules):
    svc = ConnectionStringService.__new__(ConnectionStringService)
    svc.db = None  # bare instance: RoutingRulesService is module-patched below
    monkeypatch.setattr(svc, "generate_all_region_singbox_outbounds",
                        lambda user: list(outbounds), raising=False)
    # Neutralize routing so no rule_set is emitted for the no-rules case.
    import app.services.credentials.connection_string_service as mod
    monkeypatch.setattr(mod, "RoutingRulesService",
                        lambda db: SimpleNamespace(get_effective_rules=lambda admin_id: rules))
    return svc

def test_singbox_prepends_info_and_excludes_it_from_routing(monkeypatch):
    real = [{"type": "vless", "tag": "🇨🇭 u VLESS", "server": "ex.com"}]
    svc = _svc_with(monkeypatch, real, rules={})
    user = _StubUser(admin_id=1, traffic_limit_bytes=100 * _GB,
                     traffic_used_bytes=12 * _GB, expires_at=datetime(2026, 9, 16),
                     language="en")
    is_full, payload = svc.generate_singbox_full_config(user)
    assert is_full is False
    assert payload[0]["server"] == "127.0.0.1"        # info node first
    assert payload[0]["tag"].startswith("📊")
    assert payload[1:] == real                          # real nodes preserved

def test_singbox_info_node_absent_when_no_sub_data(monkeypatch):
    real = [{"type": "vless", "tag": "t", "server": "ex.com"}]
    svc = _svc_with(monkeypatch, real, rules={})
    user = _StubUser(admin_id=1, traffic_limit_bytes=None,
                     traffic_used_bytes=0, expires_at=None, language="en")
    is_full, payload = svc.generate_singbox_full_config(user)
    assert payload == real                               # nothing prepended
