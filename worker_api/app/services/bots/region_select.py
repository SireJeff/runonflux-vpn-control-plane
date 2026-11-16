"""Pure logic for the multi-select region picker (no Telegram/DB deps)."""

from app.services.bots.bidi_fa import num_unit, rtl_line

# Persian names for the macro regions, in canonical display order. Used to
# describe what an "all regions" plan covers (Africa lives under "سایر").
_MACRO_FA_ORDER = ["eu", "as", "na", "row"]
_MACRO_FA = {"eu": "اروپا", "as": "آسیا", "na": "آمریکا", "row": "سایر"}
ALL_REGIONS_FA = "، ".join(_MACRO_FA[c] for c in _MACRO_FA_ORDER)


def required_region_count(
    region_count: int, all_regions: bool, healthy: list[str]
) -> int:
    """How many regions the customer must pick, clamped to what's healthy.

    all_regions -> every healthy region; fixed plan -> region_count, but never
    more than the number of healthy regions (graceful degrade).
    """
    if all_regions:
        return len(healthy)
    return min(region_count, len(healthy))


def toggle_region(selected: list[str], macro: str, max_count: int) -> list[str]:
    """Toggle ``macro`` in ``selected``; adding is blocked once at ``max_count``."""
    if macro in selected:
        return [m for m in selected if m != macro]
    if len(selected) >= max_count:
        return list(selected)  # at capacity — ignore
    return list(selected) + [macro]


def can_confirm(selected: list[str], required: int) -> bool:
    return len(selected) == required


def _gb(pkg) -> str:
    return f"{float(pkg.traffic_limit_gb):.0f}"


def package_button_label(pkg) -> str:
    """Short RTL-safe selector: traffic + price (Persian, built from data).

    Reseller plan names are English and inconsistent (e.g. "Pro · 1mo"), so the
    label is built from structured fields instead: the GB volume for a normal
    plan, or "همه مناطق" for an all-regions plan. Duration is implied by the
    menu category. Price glued to its unit via a single isolate.
    """
    price = num_unit(pkg.price_tomans, "ت")
    if pkg.all_regions:
        return rtl_line(f"🌍 همه مناطق · {price}")
    return rtl_line(f"{num_unit(_gb(pkg), 'گیگ')} · {price}")


def package_body_line(pkg) -> str:
    """Readable RTL body line; each number+unit isolated as one atom.

    Isolating "30 گیگ" / "100,000 تومان" as whole atoms (not just the digits)
    keeps each field glued and correctly ordered under RTL layout. All-regions
    plans name the macro regions they cover.
    """
    gb = num_unit(_gb(pkg), "گیگ")
    price = num_unit(pkg.price_tomans, "تومان")
    if pkg.all_regions:
        return rtl_line(f"🌍 همه مناطق ({ALL_REGIONS_FA}) — {gb} — {price}")
    return rtl_line(f"• {gb} — {price}")
