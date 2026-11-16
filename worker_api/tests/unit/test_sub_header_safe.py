import base64

from app.api.v1.endpoints.end_user import _header_safe_title


def test_ascii_title_unchanged():
    # ASCII titles stay raw so every client reads them as-is.
    t = "seneca_24e3 - FluxVPN | 5GB left | 12d"
    assert _header_safe_title(t) == t


def test_latin1_title_stays_raw():
    # Latin-1 (e.g. accented) is header-legal — keep raw.
    t = "Café VPN - FluxVPN"
    assert _header_safe_title(t) == t


def test_persian_title_base64_encoded_and_header_safe():
    # Persian (non-latin-1) name must NOT crash the header; carry via base64: prefix.
    t = "بابک - FluxVPN | 5GB left"
    out = _header_safe_title(t)
    assert out.startswith("base64:")
    # Round-trips back to the original title.
    assert base64.b64decode(out[len("base64:"):]).decode("utf-8") == t
    # The invariant that prevents the 500: the header value is latin-1 encodable.
    out.encode("latin-1")


def test_result_is_always_latin1_encodable():
    for t in ["plain", "بابک", "日本語 VPN", "emoji 🚀 name", "Ünïcodé"]:
        _header_safe_title(t).encode("latin-1")  # must not raise
