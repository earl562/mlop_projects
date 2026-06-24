"""HUD Fair Market Rents API client for rental comparable analysis.

Fetches Fair Market Rents from HUD USER API to estimate achievable rents
for each unit type in a development. Uses county FIPS lookup and in-memory
caching with 30-minute TTL.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from plotlot.config import settings
from plotlot.core.types import RentalComp, RentalCompSet, UnitMixEntry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HUD API configuration
# ---------------------------------------------------------------------------
_HUD_FMR_BASE = "https://www.huduser.gov/hudapi/public/fmr"
_HUD_FMR_DATA = f"{_HUD_FMR_BASE}/data"
_CACHE_TTL_SECONDS = 1800  # 30 minutes

_rental_cache: dict[str, tuple[float, RentalCompSet]] = {}


def _cache_get(key: str) -> RentalCompSet | None:
    """Return cached RentalCompSet if fresh, or None."""
    entry = _rental_cache.get(key)
    if entry is None:
        return None
    ts, comp_set = entry
    if time.time() - ts > _CACHE_TTL_SECONDS:
        del _rental_cache[key]
        return None
    return comp_set


def _cache_set(key: str, comp_set: RentalCompSet) -> None:
    _rental_cache[key] = (time.time(), comp_set)


# ---------------------------------------------------------------------------
# County FIPS lookup — maps (normalized_county, state_code) → 5-digit FIPS
#
# Normalized county = lowercase, underscores/hyphens → spaces, stripped.
# ---------------------------------------------------------------------------

_COUNTY_FIPS_MAP: dict[tuple[str, str], str] = {
    # ── Florida (67 counties) ──────────────────────────────────────────
    ("alachua", "FL"): "12001",
    ("baker", "FL"): "12003",
    ("bay", "FL"): "12005",
    ("bradford", "FL"): "12007",
    ("brevard", "FL"): "12009",
    ("broward", "FL"): "12011",
    ("calhoun", "FL"): "12013",
    ("charlotte", "FL"): "12015",
    ("citrus", "FL"): "12017",
    ("clay", "FL"): "12019",
    ("collier", "FL"): "12021",
    ("columbia", "FL"): "12023",
    ("de soto", "FL"): "12027",
    ("desoto", "FL"): "12027",
    ("dixie", "FL"): "12029",
    ("duval", "FL"): "12031",
    ("escambia", "FL"): "12033",
    ("flagler", "FL"): "12035",
    ("franklin", "FL"): "12037",
    ("gadsden", "FL"): "12039",
    ("gilchrist", "FL"): "12041",
    ("glades", "FL"): "12043",
    ("gulf", "FL"): "12045",
    ("hamilton", "FL"): "12047",
    ("hardee", "FL"): "12049",
    ("hendry", "FL"): "12051",
    ("hernando", "FL"): "12053",
    ("highlands", "FL"): "12055",
    ("hillsborough", "FL"): "12057",
    ("holmes", "FL"): "12059",
    ("indian river", "FL"): "12061",
    ("jackson", "FL"): "12063",
    ("jefferson", "FL"): "12065",
    ("lafayette", "FL"): "12067",
    ("lake", "FL"): "12069",
    ("lee", "FL"): "12071",
    ("leon", "FL"): "12073",
    ("levy", "FL"): "12075",
    ("liberty", "FL"): "12077",
    ("madison", "FL"): "12079",
    ("manatee", "FL"): "12081",
    ("marion", "FL"): "12083",
    ("martin", "FL"): "12085",
    ("miami dade", "FL"): "12086",
    ("miami-dade", "FL"): "12086",
    ("monroe", "FL"): "12087",
    ("nassau", "FL"): "12089",
    ("okaloosa", "FL"): "12091",
    ("okeechobee", "FL"): "12093",
    ("orange", "FL"): "12095",
    ("osceola", "FL"): "12097",
    ("palm beach", "FL"): "12099",
    ("pasco", "FL"): "12101",
    ("pinellas", "FL"): "12103",
    ("polk", "FL"): "12105",
    ("putnam", "FL"): "12107",
    ("santa rosa", "FL"): "12113",
    ("sarasota", "FL"): "12115",
    ("seminole", "FL"): "12117",
    ("st johns", "FL"): "12109",
    ("st. johns", "FL"): "12109",
    ("st lucie", "FL"): "12111",
    ("st. lucie", "FL"): "12111",
    ("sumter", "FL"): "12119",
    ("suwannee", "FL"): "12121",
    ("taylor", "FL"): "12123",
    ("union", "FL"): "12125",
    ("volusia", "FL"): "12127",
    ("wakulla", "FL"): "12129",
    ("walton", "FL"): "12131",
    ("washington", "FL"): "12133",
    # ── North Carolina ──────────────────────────────────────────────────
    ("alamance", "NC"): "37001",
    ("alexander", "NC"): "37003",
    ("alleghany", "NC"): "37005",
    ("anson", "NC"): "37007",
    ("ashe", "NC"): "37009",
    ("avery", "NC"): "37011",
    ("beaufort", "NC"): "37013",
    ("bertie", "NC"): "37015",
    ("bladen", "NC"): "37017",
    ("brunswick", "NC"): "37019",
    ("buncombe", "NC"): "37021",
    ("burke", "NC"): "37023",
    ("cabarrus", "NC"): "37025",
    ("caldwell", "NC"): "37027",
    ("camden", "NC"): "37029",
    ("carteret", "NC"): "37031",
    ("caswell", "NC"): "37033",
    ("catawba", "NC"): "37035",
    ("chatham", "NC"): "37037",
    ("cherokee", "NC"): "37039",
    ("chowan", "NC"): "37041",
    ("clay", "NC"): "37043",
    ("cleveland", "NC"): "37045",
    ("columbus", "NC"): "37047",
    ("craven", "NC"): "37049",
    ("cumberland", "NC"): "37051",
    ("currituck", "NC"): "37053",
    ("dare", "NC"): "37055",
    ("davidson", "NC"): "37057",
    ("davie", "NC"): "37059",
    ("duplin", "NC"): "37061",
    ("durham", "NC"): "37063",
    ("edgecombe", "NC"): "37065",
    ("forsyth", "NC"): "37067",
    ("franklin", "NC"): "37069",
    ("gaston", "NC"): "37071",
    ("gates", "NC"): "37073",
    ("graham", "NC"): "37075",
    ("granville", "NC"): "37077",
    ("greene", "NC"): "37079",
    ("guilford", "NC"): "37081",
    ("halifax", "NC"): "37083",
    ("harnett", "NC"): "37085",
    ("haywood", "NC"): "37087",
    ("henderson", "NC"): "37089",
    ("hertford", "NC"): "37091",
    ("hoke", "NC"): "37093",
    ("hyde", "NC"): "37095",
    ("iredell", "NC"): "37097",
    ("jackson", "NC"): "37099",
    ("johnston", "NC"): "37101",
    ("jones", "NC"): "37103",
    ("lee", "NC"): "37105",
    ("lenoir", "NC"): "37107",
    ("lincoln", "NC"): "37109",
    ("macon", "NC"): "37113",
    ("madison", "NC"): "37115",
    ("martin", "NC"): "37117",
    ("mcdowell", "NC"): "37111",
    ("mecklenburg", "NC"): "37119",
    ("mitchell", "NC"): "37121",
    ("montgomery", "NC"): "37123",
    ("moore", "NC"): "37125",
    ("nash", "NC"): "37127",
    ("new hanover", "NC"): "37129",
    ("northampton", "NC"): "37131",
    ("onslow", "NC"): "37133",
    ("orange", "NC"): "37135",
    ("pamlico", "NC"): "37137",
    ("pasquotank", "NC"): "37139",
    ("pender", "NC"): "37141",
    ("perquimans", "NC"): "37143",
    ("person", "NC"): "37145",
    ("pitt", "NC"): "37147",
    ("polk", "NC"): "37149",
    ("randolph", "NC"): "37151",
    ("richmond", "NC"): "37153",
    ("robeson", "NC"): "37155",
    ("rockingham", "NC"): "37157",
    ("rowan", "NC"): "37159",
    ("rutherford", "NC"): "37161",
    ("sampson", "NC"): "37163",
    ("scotland", "NC"): "37165",
    ("stanly", "NC"): "37167",
    ("stokes", "NC"): "37169",
    ("surry", "NC"): "37171",
    ("swain", "NC"): "37173",
    ("transylvania", "NC"): "37175",
    ("tyrrell", "NC"): "37177",
    ("union", "NC"): "37179",
    ("vance", "NC"): "37181",
    ("wake", "NC"): "37183",
    ("warren", "NC"): "37185",
    ("washington", "NC"): "37187",
    ("watauga", "NC"): "37189",
    ("wayne", "NC"): "37191",
    ("wilkes", "NC"): "37193",
    ("wilson", "NC"): "37195",
    ("yadkin", "NC"): "37197",
    ("yancey", "NC"): "37199",
    # ── California (major metros) ──────────────────────────────────────
    ("alameda", "CA"): "06001",
    ("butte", "CA"): "06007",
    ("contra costa", "CA"): "06013",
    ("fresno", "CA"): "06019",
    ("kern", "CA"): "06029",
    ("los angeles", "CA"): "06037",
    ("marin", "CA"): "06041",
    ("monterey", "CA"): "06053",
    ("orange", "CA"): "06059",
    ("placer", "CA"): "06061",
    ("riverside", "CA"): "06065",
    ("sacramento", "CA"): "06067",
    ("san bernardino", "CA"): "06071",
    ("san diego", "CA"): "06073",
    ("san francisco", "CA"): "06075",
    ("san joaquin", "CA"): "06077",
    ("san luis obispo", "CA"): "06079",
    ("san mateo", "CA"): "06081",
    ("santa barbara", "CA"): "06083",
    ("santa clara", "CA"): "06085",
    ("santa cruz", "CA"): "06087",
    ("sonoma", "CA"): "06097",
    ("stanislaus", "CA"): "06099",
    ("ventura", "CA"): "06111",
    ("yolo", "CA"): "06113",
    # ── Texas (major metros) ───────────────────────────────────────────
    ("bexar", "TX"): "48029",
    ("collin", "TX"): "48085",
    ("dallas", "TX"): "48113",
    ("denton", "TX"): "48121",
    ("el paso", "TX"): "48141",
    ("fort bend", "TX"): "48157",
    ("harris", "TX"): "48201",
    ("hidalgo", "TX"): "48215",
    ("montgomery", "TX"): "48339",
    ("tarrant", "TX"): "48439",
    ("travis", "TX"): "48453",
    ("williamson", "TX"): "48491",
    # ── Georgia (ATL metro) ────────────────────────────────────────────
    ("clayton", "GA"): "13063",
    ("cobb", "GA"): "13067",
    ("de kalb", "GA"): "13089",
    ("dekalb", "GA"): "13089",
    ("fulton", "GA"): "13121",
    ("gwinnett", "GA"): "13135",
    # ── New York ───────────────────────────────────────────────────────
    ("bronx", "NY"): "36005",
    ("kings", "NY"): "36047",
    ("new york", "NY"): "36061",
    ("queens", "NY"): "36081",
    ("richmond", "NY"): "36085",
    ("westchester", "NY"): "36119",
    # ── Illinois (Chicago metro) ───────────────────────────────────────
    ("cook", "IL"): "17031",
    ("du page", "IL"): "17043",
    ("dupage", "IL"): "17043",
    ("kane", "IL"): "17089",
    ("lake", "IL"): "17097",
    ("will", "IL"): "17197",
    # ── Other major metros ─────────────────────────────────────────────
    ("arapahoe", "CO"): "08005",
    ("denver", "CO"): "08031",
    ("jefferson", "CO"): "08059",
    ("clark", "NV"): "32003",
    ("king", "WA"): "53033",
    ("maricopa", "AZ"): "04013",
    ("multnomah", "OR"): "41051",
    ("davidson", "TN"): "47037",
    ("hennepin", "MN"): "27053",
    ("wayne", "MI"): "26163",
    ("oakland", "MI"): "26125",
    ("cuayahoga", "OH"): "39035",
    ("cuyahoga", "OH"): "39035",
    ("franklin", "OH"): "39049",
    ("hamilton", "OH"): "39061",
    ("suffolk", "MA"): "25025",
    ("middlesex", "MA"): "25017",
    ("salt lake", "UT"): "49035",
    ("district of columbia", "DC"): "11001",
    ("washington", "DC"): "11001",
    ("baltimore", "MD"): "24510",
    ("montgomery", "MD"): "24031",
    ("prince george's", "MD"): "24033",
    ("prince georges", "MD"): "24033",
    ("fairfax", "VA"): "51059",
    ("arlington", "VA"): "51013",
    ("philadelphia", "PA"): "42101",
    ("allegheny", "PA"): "42003",
    ("jackson", "MO"): "29095",
    ("st. louis", "MO"): "29189",
    ("st louis", "MO"): "29189",
    ("st. louis city", "MO"): "29510",
    ("milwaukee", "WI"): "53079",
    ("shelby", "TN"): "47157",
    ("oklahoma", "OK"): "40109",
    ("tulsa", "OK"): "40143",
    ("jefferson", "AL"): "01073",
    ("orleans", "LA"): "22071",
    ("jefferson", "LA"): "22051",
    ("palm beach", "PR"): "72000",
    ("san juan", "PR"): "72127",
}


def _normalize_county(county: str) -> str:
    """Normalize a county name for FIPS lookup.

    Lowercases, replaces underscores/hyphens with spaces, strips whitespace,
    removes 'county' suffix, and collapses runs of whitespace.
    """
    normalized = county.lower().strip()
    normalized = normalized.replace("_", " ").replace("-", " ")
    # Remove " county" suffix if present
    if normalized.endswith(" county"):
        normalized = normalized[: -len(" county")]
    # Collapse whitespace
    normalized = " ".join(normalized.split())
    return normalized


def _lookup_fips(county: str, state: str) -> str | None:
    """Look up 5-digit county FIPS code from the static map.

    Returns None if the county is not in the lookup map.
    """
    key = (_normalize_county(county), state.upper())
    fips = _COUNTY_FIPS_MAP.get(key)
    if fips is None and " " in key[0]:
        # Retry without spaces (e.g. "stjohns" for "st johns")
        compact = key[0].replace(" ", "").replace(".", "")
        compact_key = (compact, key[1])
        fips = _COUNTY_FIPS_MAP.get(compact_key)
    return fips


# ---------------------------------------------------------------------------
# HUD FMR API client
# ---------------------------------------------------------------------------


def _parse_fmr_entry(
    entry: dict[str, Any],
    county: str,
    state: str,
) -> list[RentalComp]:
    """Parse one HUD FMR data entry into RentalComp objects.

    Each HUD entry covers an entire county/area with rent levels by
    bedroom count. We create one RentalComp per unit type.
    """
    comps: list[RentalComp] = []
    county_name = entry.get("county_name", county)
    area_name = entry.get("area_name", "")
    year = str(entry.get("year", ""))

    unit_types = [
        ("studio", 0, 1.0, 450, "efficiency", "Efficiency"),
        ("1BR", 1, 1.0, 700, "one_bedroom", "One-Bedroom"),
        ("2BR", 2, 1.5, 950, "two_bedroom", "Two-Bedroom"),
        ("3BR", 3, 2.0, 1200, "three_bedroom", "Three-Bedroom"),
        ("4BR+", 4, 2.5, 1500, "four_bedroom", "Four-Bedroom"),
    ]

    for unit_type, beds, baths, default_sqft, field_name, hud_field_name in unit_types:
        rent = entry.get(field_name, 0) or entry.get(hud_field_name, 0)
        if isinstance(rent, (int, float)) and rent > 0:
            monthly_rent = float(rent)
            comps.append(
                RentalComp(
                    property_name=f"{county_name} HUD FMR ({year})",
                    address=area_name or f"{county}, {state}",
                    bedrooms=beds,
                    bathrooms=baths,
                    sqft=default_sqft,
                    monthly_rent=monthly_rent,
                    rent_per_sqft=round(monthly_rent / default_sqft, 2) if default_sqft > 0 else 0.0,
                    unit_type=unit_type,
                    source="HUD FMR",
                    last_updated=str(year),
                )
            )

    return comps


def _build_comp_set(
    comps: list[RentalComp],
    source: str = "HUD FMR",
) -> RentalCompSet:
    """Build an aggregated RentalCompSet from a list of RentalComps."""
    if not comps:
        return RentalCompSet(comps=[], comp_count=0, source=source)

    rents = [c.monthly_rent for c in comps if c.monthly_rent > 0]
    rents_per_sqft = [c.rent_per_sqft for c in comps if c.rent_per_sqft > 0]
    sqfts = [c.sqft for c in comps if c.sqft > 0]

    rents_sorted = sorted(rents)
    median_rent = _median(rents_sorted) if rents_sorted else 0.0
    avg_rent = round(sum(rents) / len(rents), 2) if rents else 0.0

    rents_per_sqft_sorted = sorted(rents_per_sqft)
    median_rent_per_sqft = _median(rents_per_sqft_sorted) if rents_per_sqft_sorted else 0.0
    avg_rent_per_sqft = round(sum(rents_per_sqft) / len(rents_per_sqft), 2) if rents_per_sqft else 0.0

    avg_sqft = round(sum(sqfts) / len(sqfts), 2) if sqfts else 0.0

    return RentalCompSet(
        comps=comps,
        comp_count=len(comps),
        avg_rent=avg_rent,
        median_rent=median_rent,
        avg_rent_per_sqft=avg_rent_per_sqft,
        median_rent_per_sqft=median_rent_per_sqft,
        avg_sqft=avg_sqft,
        rent_range_low=rents_sorted[0] if rents_sorted else 0.0,
        rent_range_high=rents_sorted[-1] if rents_sorted else 0.0,
        confidence=_confidence_from_count(len(comps)),
        source=source,
    )


def _median(sorted_values: list[float]) -> float:
    """Compute median from a sorted list of values."""
    n = len(sorted_values)
    if n == 0:
        return 0.0
    mid = n // 2
    if n % 2 == 0:
        return round((sorted_values[mid - 1] + sorted_values[mid]) / 2, 2)
    return sorted_values[mid]


def _confidence_from_count(count: int) -> float:
    """Simple confidence heuristic based on comp count."""
    if count >= 5:
        return 0.9
    if count >= 3:
        return 0.75
    if count >= 1:
        return 0.5
    return 0.0


async def fetch_rental_comps(
    county: str = "",
    state: str = "FL",
    zip_code: str = "",
    year: str = "2026",
) -> RentalCompSet:
    """Fetch Fair Market Rents from HUD USER API for a given location.

    Looks up county FIPS code from the internal _COUNTY_FIPS_MAP, queries
    the HUD FMR API with Bearer token auth, parses rent data per unit type,
    and returns an aggregated RentalCompSet. Results are cached in-memory
    for 30 minutes.

    Args:
        county: County name (e.g. "miami_dade", "Broward", "Mecklenburg")
        state: Two-letter state code (default "FL")
        zip_code: ZIP code (unused for HUD FMR — kept for API compatibility;
                  FMR data is county-level, not ZIP-level)
        year: FMR data year (default "2024")

    Returns:
        RentalCompSet with per-unit-type rent estimates and aggregate stats.
    """
    cache_key = f"{_normalize_county(county)}_{state.upper()}_{year}"
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.debug("Rental cache hit for %s", cache_key)
        return cached

    if not settings.hud_api_key:
        logger.warning("HUD API key not configured — returning empty RentalCompSet")
        empty = RentalCompSet(source="HUD FMR (unconfigured)")
        _cache_set(cache_key, empty)
        return empty

    fips = _lookup_fips(county, state)
    if not fips:
        logger.warning(
            "No FIPS code found for county=%s state=%s — check _COUNTY_FIPS_MAP",
            county, state,
        )
        empty = RentalCompSet(
            source="HUD FMR (FIPS lookup failed)",
            comps=[],
            comp_count=0,
        )
        _cache_set(cache_key, empty)
        return empty

    logger.info("Fetching HUD FMR for FIPS=%s (%s, %s)", fips, county, state)

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                f"{_HUD_FMR_DATA}/{fips}99999",
                headers={
                    "Authorization": f"Bearer {settings.hud_api_key}",
                    "Accept": "application/json",
                },
                params={"year": year},
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        logger.error("HUD API HTTP error (FIPS=%s): %s", fips, e)
        empty = RentalCompSet(
            source=f"HUD FMR (HTTP {e.response.status_code})",
            comps=[],
            comp_count=0,
        )
        _cache_set(cache_key, empty)
        return empty
    except Exception as e:
        logger.error("HUD API request failed (FIPS=%s): %s", fips, e)
        empty = RentalCompSet(
            source="HUD FMR (request error)",
            comps=[],
            comp_count=0,
        )
        _cache_set(cache_key, empty)
        return empty

    if not isinstance(data, dict):
        logger.warning("HUD API returned unexpected response type: %s", type(data))
        empty = RentalCompSet(source="HUD FMR (unexpected response)")
        _cache_set(cache_key, empty)
        return empty

    entries = data.get("data", [])
    if isinstance(entries, dict):
        # HUD API returns {"data": {"basicdata": [...], "county_name": "..."}}
        basicdata = entries.get("basicdata", [])
        if isinstance(basicdata, list) and basicdata:
            entries = basicdata
        elif "fmr_value" in entries or "county_name" in entries:
            entries = [entries]
        else:
            logger.warning("HUD FMR response has no basicdata entries for FIPS=%s", fips)
            empty = RentalCompSet(source="HUD FMR (no data)")
            _cache_set(cache_key, empty)
            return empty
    elif not isinstance(entries, list) or not entries:
        if "fmr_value" in data or "county_name" in data:
            entries = [data]
        else:
            logger.warning("HUD FMR response has no data entries for FIPS=%s", fips)
            empty = RentalCompSet(source="HUD FMR (no data)")
            _cache_set(cache_key, empty)
            return empty

    all_comps: list[RentalComp] = []
    for entry in entries:
        if isinstance(entry, dict):
            all_comps.extend(_parse_fmr_entry(entry, county, state))

    comp_set = _build_comp_set(all_comps)
    logger.info(
        "HUD FMR: %d rental comps for %s, %s (FIPS=%s)",
        comp_set.comp_count, county, state, fips,
    )
    _cache_set(cache_key, comp_set)
    return comp_set


# ---------------------------------------------------------------------------
# Default unit mix generation
# ---------------------------------------------------------------------------

_UNIT_MIX_DEFAULTS: dict[str, list[dict[str, Any]]] = {
    "multifamily": [
        {"unit_type": "studio", "bedrooms": 0, "bathrooms": 1.0, "sqft": 500, "pct": 5.0},
        {"unit_type": "1BR", "bedrooms": 1, "bathrooms": 1.0, "sqft": 750, "pct": 40.0},
        {"unit_type": "2BR", "bedrooms": 2, "bathrooms": 1.5, "sqft": 1050, "pct": 40.0},
        {"unit_type": "3BR", "bedrooms": 3, "bathrooms": 2.0, "sqft": 1300, "pct": 15.0},
    ],
    "commercial_mf": [
        {"unit_type": "studio", "bedrooms": 0, "bathrooms": 1.0, "sqft": 550, "pct": 10.0},
        {"unit_type": "1BR", "bedrooms": 1, "bathrooms": 1.0, "sqft": 800, "pct": 45.0},
        {"unit_type": "2BR", "bedrooms": 2, "bathrooms": 2.0, "sqft": 1100, "pct": 35.0},
        {"unit_type": "3BR", "bedrooms": 3, "bathrooms": 2.0, "sqft": 1400, "pct": 10.0},
    ],
    "single_family": [
        {"unit_type": "3BR", "bedrooms": 3, "bathrooms": 2.0, "sqft": 1800, "pct": 100.0},
    ],
    "land": [],
    "commercial": [],
}


def default_unit_mix(
    property_type: str = "multifamily",
    max_units: int = 0,
) -> list[UnitMixEntry]:
    """Generate a default unit mix for a development.

    Applies a standard distribution of unit types based on the property
    type, scaled to the maximum allowable unit count. For single-family
    and land, returns a simple breakdown. For commercial, returns an
    empty list (commercial is not unit-count-based).

    Args:
        property_type: One of "multifamily", "commercial_mf", "single_family",
                       "land", "commercial"
        max_units: Maximum allowable dwelling units (used for unit_count
                   distribution)

    Returns:
        List of UnitMixEntry with unit counts proportional to max_units.
    """
    defaults = _UNIT_MIX_DEFAULTS.get(property_type, _UNIT_MIX_DEFAULTS["multifamily"])

    if not defaults or max_units <= 0:
        return []

    if property_type in ("single_family", "land"):
        return [
            UnitMixEntry(
                unit_type=entry["unit_type"],
                bedrooms=entry["bedrooms"],
                bathrooms=entry["bathrooms"],
                sqft=entry["sqft"],
                unit_count=max_units,
                percentage_of_total=100.0,
            )
            for entry in defaults
        ]

    entries: list[UnitMixEntry] = []
    allocated = 0

    for i, entry in enumerate(defaults):
        pct = entry["pct"]
        if i == len(defaults) - 1:
            count = max_units - allocated
        else:
            count = max(0, round(max_units * pct / 100))
        allocated += count

        if count > 0:
            entries.append(
                UnitMixEntry(
                    unit_type=entry["unit_type"],
                    bedrooms=entry["bedrooms"],
                    bathrooms=entry["bathrooms"],
                    sqft=entry["sqft"],
                    unit_count=count,
                    percentage_of_total=round(count / max_units * 100, 1) if max_units > 0 else 0.0,
                )
            )

    if allocated < max_units:
        remainder = max_units - allocated
        if entries:
            entries[-1].unit_count += remainder
            entries[-1].percentage_of_total = round(
                entries[-1].unit_count / max_units * 100, 1
            )

    return entries
