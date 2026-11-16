# worker_api/tests/unit/test_sub_info_node.py
import base64
from datetime import datetime
from urllib.parse import unquote
from app.services.credentials.info_node import format_info_node_label, info_uri_line

_GB = 1024 ** 3

def test_base64_prepends_info_line_and_decodes():
    # Simulate the endpoint's line assembly: info first, then real nodes.
    label = format_info_node_label(100 * _GB, 12 * _GB, datetime(2026, 9, 16), "en",
                                   now=datetime(2026, 8, 19))
    real = ["vless://uuid@ex.com:443#node1", "trojan://pw@ex.com:443#node2"]
    lines = list(real)
    if label:
        lines.insert(0, info_uri_line(label))
    encoded = base64.b64encode("\n".join(lines).encode()).decode()

    decoded = base64.b64decode(encoded).decode().splitlines()
    assert decoded[0].startswith("trojan://info@127.0.0.1:1")
    frag = decoded[0].split("#", 1)[1]
    assert unquote(frag) == "📊 88GB · 28d left"
    assert decoded[1:] == real  # real nodes preserved, in order
