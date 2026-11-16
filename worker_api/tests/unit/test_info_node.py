from datetime import datetime
from app.services.credentials.info_node import (
    format_info_node_label, info_uri_line, info_singbox_outbound,
)

_GB = 1024 ** 3
NOW = datetime(2026, 8, 19)

def test_label_limited_traffic_and_expiry_fa():
    label = format_info_node_label(100 * _GB, 12 * _GB, datetime(2026, 9, 16), "fa", now=NOW)
    assert label == "📊 88GB · 28d باقی‌مانده"

def test_label_english():
    label = format_info_node_label(100 * _GB, 12 * _GB, datetime(2026, 9, 16), "en", now=NOW)
    assert label == "📊 88GB · 28d left"

def test_label_unlimited_traffic_uses_infinity():
    label = format_info_node_label(None, 5 * _GB, datetime(2026, 9, 16), "en", now=NOW)
    assert label == "📊 ♾️ · 28d left"

def test_label_no_expiry_omits_days():
    label = format_info_node_label(100 * _GB, 12 * _GB, None, "en", now=NOW)
    assert label == "📊 88GB left"

def test_label_none_when_no_limit_and_no_expiry():
    assert format_info_node_label(None, 0, None, "en", now=NOW) is None

def test_label_expired_and_used_never_negative():
    label = format_info_node_label(50 * _GB, 60 * _GB, datetime(2026, 8, 1), "en", now=NOW)
    assert label == "📊 0GB · 0d left"

def test_label_sub_gigabyte_one_decimal():
    label = format_info_node_label(1 * _GB, int(0.7 * _GB), None, "en", now=NOW)
    assert label == "📊 0.3GB left"

def test_info_uri_line_is_display_only_localhost_with_encoded_fragment():
    line = info_uri_line("📊 88GB · 28d left")
    assert line.startswith("trojan://info@127.0.0.1:1?")
    assert line.endswith("#" + "%F0%9F%93%8A%2088GB%20%C2%B7%2028d%20left")

def test_info_singbox_outbound_shape():
    ob = info_singbox_outbound("📊 88GB · 28d left")
    assert ob["type"] == "trojan"
    assert ob["tag"] == "📊 88GB · 28d left"
    assert ob["server"] == "127.0.0.1"
    assert ob["server_port"] == 1
    assert ob["tls"]["enabled"] is True
