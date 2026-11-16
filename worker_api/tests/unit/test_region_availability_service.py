from unittest.mock import MagicMock, patch


def test_healthy_macro_codes_filters_zero_capacity():
    from app.services.regions import availability

    # eu has 2 healthy NL domains, others zero
    fake_counts = {"NL": 2}
    with patch.object(
        availability, "_healthy_country_counts", return_value=fake_counts
    ):
        codes = availability.healthy_macro_codes(MagicMock())

    assert "eu" in codes  # NL ∈ eu
    assert "na" not in codes  # no US/CA/MX healthy


def test_macro_region_availability_shape():
    from app.services.regions import availability

    with patch.object(availability, "_healthy_country_counts", return_value={"SG": 3}):
        result = availability.macro_region_availability(MagicMock())

    as_entry = next(r for r in result if r["code"] == "as")
    assert as_entry["healthy_instances"] == 3
    assert {"code", "name", "flag", "healthy_instances", "countries"} <= set(as_entry)
    assert all(c["healthy_instances"] > 0 for c in as_entry["countries"])
