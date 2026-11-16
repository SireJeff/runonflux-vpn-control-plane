from unittest.mock import MagicMock


def test_generate_all_region_connections_covers_all_active_regions():
    from app.services.credentials.connection_string_service import (
        ConnectionStringService,
    )

    db = MagicMock()
    r_eu = MagicMock(macro_region="eu", status="active")
    r_as = MagicMock(macro_region="as", status="active")
    # active-region query -> .all() returns both rows
    db.query.return_value.filter.return_value.all.return_value = [r_eu, r_as]

    svc = ConnectionStringService(db)
    user = MagicMock(id=1)

    def fake_gen(u, macro, increment_load=True):
        return {f"{macro}-country": {"ssh": {"primary": macro, "fallbacks": []}}}

    svc.generate_connection_strings = MagicMock(side_effect=fake_gen)

    result = svc.generate_all_region_connections(user)

    # one call per active region, merged output contains BOTH regions' countries
    assert svc.generate_connection_strings.call_count == 2
    assert "eu-country" in result and "as-country" in result
    assert result["as-country"]["ssh"]["primary"] == "as"


def test_generate_all_region_connections_empty_when_no_regions():
    from app.services.credentials.connection_string_service import (
        ConnectionStringService,
    )

    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []
    svc = ConnectionStringService(db)
    svc.generate_connection_strings = MagicMock()

    result = svc.generate_all_region_connections(MagicMock(id=1))

    assert result == {}
    svc.generate_connection_strings.assert_not_called()


def test_generate_all_region_singbox_covers_all_active_regions():
    from app.services.credentials.connection_string_service import (
        ConnectionStringService,
    )

    db = MagicMock()
    r_eu = MagicMock(macro_region="eu", status="active")
    r_as = MagicMock(macro_region="as", status="active")
    db.query.return_value.filter.return_value.all.return_value = [r_eu, r_as]

    svc = ConnectionStringService(db)
    user = MagicMock(id=1)

    svc.generate_singbox_outbounds = MagicMock(
        side_effect=lambda u, macro: [{"tag": f"{macro}-ssh", "type": "ssh"}]
    )

    result = svc.generate_all_region_singbox_outbounds(user)

    # one call per active region, outbounds concatenated across BOTH regions
    assert svc.generate_singbox_outbounds.call_count == 2
    assert {o["tag"] for o in result} == {"eu-ssh", "as-ssh"}


def test_generate_all_region_singbox_dedups_duplicate_macro():
    from app.services.credentials.connection_string_service import (
        ConnectionStringService,
    )

    db = MagicMock()
    r_eu1 = MagicMock(macro_region="eu", status="active")
    r_eu2 = MagicMock(macro_region="eu", status="active")
    db.query.return_value.filter.return_value.all.return_value = [r_eu1, r_eu2]

    svc = ConnectionStringService(db)
    svc.generate_singbox_outbounds = MagicMock(return_value=[{"tag": "eu"}])

    result = svc.generate_all_region_singbox_outbounds(MagicMock(id=1))

    # duplicate macro collapsed to a single generation call
    assert svc.generate_singbox_outbounds.call_count == 1
    assert result == [{"tag": "eu"}]
