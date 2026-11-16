"""The /sub/{token} subscription endpoint must span EVERY active macro-region,
not just the user's primary. Regression for the all-region user who only received
their primary macro's (EU/ch01) countries."""
import base64
from unittest.mock import MagicMock, patch


def _import_endpoint():
    from app.api.v1.endpoints import end_user

    return end_user


def _make_db(user, active_regions):
    """db.query(AdminUser)->first()==user ; db.query(UserRegion)->all()==regions."""
    db = MagicMock()

    def dispatch(model):
        name = getattr(model, "__name__", str(model))
        m = MagicMock()
        if name == "AdminUser":
            m.filter.return_value.first.return_value = user
        elif name == "UserRegion":
            m.filter.return_value.all.return_value = active_regions
        return m

    db.query.side_effect = dispatch
    return db


def _make_user():
    user = MagicMock()
    user.status = "active"
    user.subscription_token = "tok123"
    user.traffic_used_bytes = 0
    user.traffic_limit_bytes = None
    user.expires_at = None
    user.display_name = None
    user.username = "faraday"
    return user


def test_base64_subscription_spans_all_active_regions():
    end_user = _import_endpoint()
    from app.core.constants import MACRO_REGIONS

    eu_country = MACRO_REGIONS["eu"]["countries"][0]
    as_country = MACRO_REGIONS["as"]["countries"][0]

    user = _make_user()
    regions = [
        MagicMock(macro_region="eu", is_primary=True, status="active"),
        MagicMock(macro_region="as", is_primary=False, status="active"),
    ]
    db = _make_db(user, regions)

    merged = {
        eu_country: {"vless": {"primary": "vless://EU-LINK", "fallbacks": []}},
        as_country: {"vless": {"primary": "vless://AS-LINK", "fallbacks": []}},
    }

    with patch.object(end_user, "ConnectionStringService") as CS:
        CS.return_value.generate_all_region_connections.return_value = merged
        resp = end_user.get_subscription(token="tok123", format="base64", db=db)

    decoded = base64.b64decode(resp.body).decode("utf-8")
    # BOTH regions present — the pre-fix code emitted only the primary (eu) macro
    assert "vless://EU-LINK" in decoded
    assert "vless://AS-LINK" in decoded
    # multi-region path used, single-macro path not used
    CS.return_value.generate_all_region_connections.assert_called_once()
    CS.return_value.generate_connection_strings.assert_not_called()


def test_singbox_subscription_uses_all_region_helper():
    end_user = _import_endpoint()

    user = _make_user()
    regions = [
        MagicMock(macro_region="eu", is_primary=True, status="active"),
        MagicMock(macro_region="na", is_primary=False, status="active"),
    ]
    db = _make_db(user, regions)

    with patch.object(end_user, "ConnectionStringService") as CS:
        CS.return_value.generate_singbox_full_config.return_value = (
            False,
            [{"tag": "x", "type": "ssh"}],
        )
        resp = end_user.get_subscription(token="tok123", format="singbox", db=db)

    assert resp.media_type == "application/json"
    CS.return_value.generate_singbox_full_config.assert_called_once()


def test_subscription_404_when_no_active_regions():
    end_user = _import_endpoint()
    from fastapi import HTTPException

    user = _make_user()
    db = _make_db(user, [])  # no active regions

    with patch.object(end_user, "ConnectionStringService"):
        try:
            end_user.get_subscription(token="tok123", format="base64", db=db)
            assert False, "expected HTTPException"
        except HTTPException as exc:
            assert exc.status_code == 404
