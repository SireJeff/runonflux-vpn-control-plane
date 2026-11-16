def test_userinfo_total_semantics():
    from app.api.v1.endpoints.end_user import _format_userinfo_total

    # NULL limit = unlimited -> non-zero sentinel
    assert _format_userinfo_total(None) != 0
    # 0 = blocked / zero quota -> stays 0 (full bar)
    assert _format_userinfo_total(0) == 0
    # positive limit passes through unchanged
    assert _format_userinfo_total(10 * 1073741824) == 10 * 1073741824
