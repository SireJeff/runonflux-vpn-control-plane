"""
Global constants for FluxVPN Platform
"""

# Country to Region mapping for FDM
# Maps ISO 3166-1 alpha-2 country codes to region codes
COUNTRY_TO_REGION = {
    # Americas
    "US": "us",
    "CA": "us",
    "BR": "us",
    "MX": "us",
    "AR": "us",
    "CL": "us",
    "CO": "us",
    # Europe
    "NL": "eu",
    "DE": "eu",
    "FR": "eu",
    "GB": "eu",
    "FI": "eu",
    "CH": "eu",
    "ES": "eu",
    "IT": "eu",
    "PL": "eu",
    "SE": "eu",
    "NO": "eu",
    "DK": "eu",
    "BE": "eu",
    "AT": "eu",
    # Asia-Pacific
    "SG": "ap",
    "JP": "ap",
    "HK": "ap",
    "AU": "ap",
    "KR": "ap",
    "IN": "ap",
    "TH": "ap",
    "MY": "ap",
    "TW": "ap",
    "ID": "ap",
    "VN": "ap",
    # Middle East
    "AE": "me",
    "TR": "me",
    "SA": "me",
    "IL": "me",
    "IR": "me",
    "QA": "me",
    # Africa
    "ZA": "af",
    "NG": "af",
    "EG": "af",
    "KE": "af",
    "MA": "af",
}

# All supported regions
SUPPORTED_REGIONS = list(set(COUNTRY_TO_REGION.values()))

# Default region for unknown countries
DEFAULT_REGION = "eu"

# ISO 3166-1 alpha-2 country code -> display name
COUNTRY_NAMES = {
    "US": "United States",
    "CA": "Canada",
    "BR": "Brazil",
    "MX": "Mexico",
    "AR": "Argentina",
    "CL": "Chile",
    "CO": "Colombia",
    "NL": "Netherlands",
    "DE": "Germany",
    "FR": "France",
    "GB": "United Kingdom",
    "FI": "Finland",
    "CH": "Switzerland",
    "ES": "Spain",
    "IT": "Italy",
    "PL": "Poland",
    "SE": "Sweden",
    "NO": "Norway",
    "DK": "Denmark",
    "BE": "Belgium",
    "AT": "Austria",
    "SG": "Singapore",
    "JP": "Japan",
    "HK": "Hong Kong",
    "AU": "Australia",
    "KR": "South Korea",
    "IN": "India",
    "TH": "Thailand",
    "MY": "Malaysia",
    "TW": "Taiwan",
    "ID": "Indonesia",
    "VN": "Vietnam",
    "AE": "UAE",
    "TR": "Turkey",
    "SA": "Saudi Arabia",
    "IL": "Israel",
    "IR": "Iran",
    "QA": "Qatar",
    "ZA": "South Africa",
    "NG": "Nigeria",
    "EG": "Egypt",
    "KE": "Kenya",
    "MA": "Morocco",
    "PT": "Portugal",
    "IE": "Ireland",
    "LU": "Luxembourg",
    "CZ": "Czech Republic",
    "RO": "Romania",
    "BG": "Bulgaria",
    "HU": "Hungary",
    "UA": "Ukraine",
    "RS": "Serbia",
    "HR": "Croatia",
    "SK": "Slovakia",
    "SI": "Slovenia",
    "LT": "Lithuania",
    "LV": "Latvia",
    "EE": "Estonia",
    "GR": "Greece",
    "PH": "Philippines",
    "KW": "Kuwait",
    "BH": "Bahrain",
    "OM": "Oman",
    "PK": "Pakistan",
    "BD": "Bangladesh",
    "LK": "Sri Lanka",
    "MM": "Myanmar",
    "KH": "Cambodia",
    "LA": "Laos",
    "PE": "Peru",
    "GH": "Ghana",
    "TN": "Tunisia",
    "NZ": "New Zealand",
    "CO": "Colombia",
    "AR": "Argentina",
    "CL": "Chile",
    "PY": "Paraguay",
    "UY": "Uruguay",
    "BO": "Bolivia",
    "EC": "Ecuador",
    "VE": "Venezuela",
}


def get_country_name(country_code: str) -> str:
    """Get display name for a country code. Falls back to the code itself."""
    return COUNTRY_NAMES.get(country_code.upper(), country_code.upper())


def get_region(country_code: str) -> str:
    """
    Get region code from country code.

    Args:
        country_code: ISO 3166-1 alpha-2 country code (e.g., 'US', 'NL')

    Returns:
        Region code ('us', 'eu', 'ap', 'me', 'af')
    """
    return COUNTRY_TO_REGION.get(country_code.upper(), DEFAULT_REGION)


# ============================================================================
# MACRO REGIONS (user-facing grouping)
# ============================================================================

MACRO_REGIONS = {
    "eu": {
        "name": "Europe",
        "flag": "🇪🇺",
        "countries": [
            "NL",
            "CH",
            "DE",
            "FR",
            "GB",
            "PL",
            "SE",
            "FI",
            "NO",
            "DK",
            "IT",
            "ES",
            "PT",
            "IE",
            "AT",
            "BE",
            "LU",
            "CZ",
            "RO",
            "BG",
            "HU",
            "UA",
            "RS",
            "HR",
            "SK",
            "SI",
            "LT",
            "LV",
            "EE",
            "GR",
        ],
    },
    "as": {
        "name": "Asia",
        "flag": "🌏",
        "countries": [
            "SG",
            "JP",
            "HK",
            "KR",
            "IN",
            "AE",
            "TR",
            "TH",
            "MY",
            "PH",
            "ID",
            "VN",
            "TW",
            "IL",
            "SA",
            "QA",
            "KW",
            "BH",
            "OM",
            "PK",
            "BD",
            "LK",
            "MM",
            "KH",
            "LA",
        ],
    },
    "na": {
        "name": "North America",
        "flag": "🌎",
        "countries": ["US", "CA", "MX"],
    },
    "row": {
        "name": "Rest of World",
        "flag": "🌍",
        "countries": [
            "BR",
            "AR",
            "CL",
            "CO",
            "PE",
            "PY",
            "UY",
            "BO",
            "EC",
            "VE",
            "AU",
            "NZ",
            "ZA",
            "NG",
            "EG",
            "KE",
            "GH",
            "MA",
            "TN",
        ],
    },
}

# Reverse lookup: country code → macro region code
COUNTRY_TO_MACRO: dict[str, str] = {}
for _macro_code, _info in MACRO_REGIONS.items():
    for _country in _info["countries"]:
        COUNTRY_TO_MACRO[_country] = _macro_code

CDN_PREFIXES = [
    "cdn",
    "media",
    "api",
    "static",
    "assets",
    "img",
    "data",
    "files",
    "dl",
    "cache",
    "content",
    "store",
    "stream",
    "portal",
    "web",
    "app",
    "cloud",
    "node",
    "hub",
    "link",
    "edge",
    "core",
    "relay",
    "gate",
    "mesh",
    "grid",
    "vault",
    "nexus",
]


def country_flag(code: str) -> str:
    """Generate Unicode flag emoji from ISO 3166-1 alpha-2 country code.

    Uses Regional Indicator Symbols (U+1F1E6..U+1F1FF).
    Each letter maps to chr(0x1F1E6 - ord('A') + ord(letter)).
    Example: 'CH' → 🇨🇭
    """
    return "".join(chr(0x1F1E6 - 65 + ord(c)) for c in code.upper())


def get_macro_region_name(macro_code: str) -> str:
    """Get display name for a macro region code. Falls back to the code itself."""
    info = MACRO_REGIONS.get(macro_code.lower())
    return str(info["name"]) if info else macro_code.upper()
