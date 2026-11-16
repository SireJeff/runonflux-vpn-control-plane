"""Regression: Rest-of-World (row) macro-region completeness.

row01's Paraguay (PY) Flux deployment was healthy but UNROUTABLE — the macro is
resolved at SERVE time by iterating ``MACRO_REGIONS[macro]["countries"]`` (see
``connection_string_service.generate_connection_strings``), and PY plus the
other LatAm/RoW codes UY/BO/EC/VE were missing from the row list, so row users
never received a connection string for those countries.

These tests lock in:
  * the five codes route to ``row`` via the auto-built ``COUNTRY_TO_MACRO``
    inversion (constants.py builds it from ``MACRO_REGIONS``),
  * no ISO code appears in two macros — the inversion silently overwrites on a
    collision, so a duplicate would be a latent routing bug with NO runtime
    signal; asserting the source lists are disjoint is the only guard,
  * display names resolve so ``get_country_name`` does not fall back to the
    bare code (e.g. "PY" instead of "Paraguay") in the connection list.
"""
from app.core.constants import (
    COUNTRY_NAMES,
    COUNTRY_TO_MACRO,
    MACRO_REGIONS,
    get_country_name,
)

# LatAm/RoW codes added to the row macro for routability + completeness.
NEW_ROW_COUNTRIES = ["PY", "UY", "BO", "EC", "VE"]


def test_new_row_countries_route_to_row():
    """Each added code must invert to the 'row' macro."""
    for code in NEW_ROW_COUNTRIES:
        assert (
            COUNTRY_TO_MACRO.get(code) == "row"
        ), "%s should route to 'row', got %r" % (code, COUNTRY_TO_MACRO.get(code))


def test_new_row_countries_exclusive_to_row():
    """No added code may also be claimed by eu/as/na (that would be a conflict)."""
    for code in NEW_ROW_COUNTRIES:
        for macro in ("eu", "as", "na"):
            assert (
                code not in MACRO_REGIONS[macro]["countries"]
            ), "%s must be exclusive to 'row' (also listed in %s)" % (code, macro)


def test_no_country_in_two_macros():
    """Every ISO code belongs to exactly one macro region.

    ``COUNTRY_TO_MACRO`` is built by an inversion loop that silently overwrites
    on collision, so a duplicate would map the code to only the LAST macro — a
    silent, hard-to-spot routing bug. Asserting the source lists are disjoint is
    the only way to catch it.
    """
    seen: dict[str, str] = {}
    for macro, info in MACRO_REGIONS.items():
        for code in info["countries"]:
            assert code not in seen, "%s listed in both %s and %s" % (
                code,
                seen[code],
                macro,
            )
            seen[code] = macro


def test_new_row_countries_have_display_names():
    """get_country_name must resolve each added code (no bare-code fallback)."""
    expected = {
        "PY": "Paraguay",
        "UY": "Uruguay",
        "BO": "Bolivia",
        "EC": "Ecuador",
        "VE": "Venezuela",
    }
    for code, name in expected.items():
        assert code in COUNTRY_NAMES, "%s missing from COUNTRY_NAMES" % code
        assert get_country_name(code) == name, "%s display name %r != expected %r" % (
            code,
            get_country_name(code),
            name,
        )
