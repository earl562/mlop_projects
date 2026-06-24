"""SeleniumBase UC+CDP-powered Zillow comps skill.

Uses SeleniumBase's ``SB(uc=True) + activate_cdp_mode()`` for maximum stealth,
bypassing PerimeterX bot detection via ``gui_click_and_hold("#px-captcha")``.

Supports Daniel Kleyman's deal-path comping methodology:
- **land** → sold land with similar acreage (establishes land basis)
- **new_build** → sold homes built within last year (ARV for Path 1/2)
- **renovated** → sold homes with renovation indicators (ARV for Path 1/2)
- **small_mf** → sold duplexes / 2-4 unit buildings (ARV for Path 2)
- **rental** → rental listings (NOI for Path 3, ≥5 units)

Each scenario builds a Zillow ``searchQueryState`` JSON with the appropriate
``filterState`` to filter by property type, lot size, year built, etc.

URLs search by ZIP code area to get search result pages (not property detail
redirects). Cookie reuse between scenarios avoids re-triggering CAPTCHAs.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.parse
from typing import Any

from plotlot.pipeline.skills.browser_manager import run_stealth_fetch
from plotlot.pipeline.skills.registry import HandlerResult, register_skill

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# URL construction
# ---------------------------------------------------------------------------

_ZILLOW_BASE = "https://www.zillow.com/homes"
_ZIP_RE = re.compile(r"\b(\d{5})\b")
_CURRENT_YEAR = 2026


def _extract_zip(address: str) -> str | None:
    """Extract a 5-digit ZIP code from an address string.

    >>> _extract_zip("123 Main St, Miami, FL 33169")
    '33169'
    """
    match = _ZIP_RE.search(address)
    return match.group(1) if match else None


# ---------------------------------------------------------------------------
# Kleyman deal-path filter states
# ---------------------------------------------------------------------------

# Common "sold" filter — disables all for-sale statuses, enables recently sold.
_SOLD_BASE: dict[str, Any] = {
    "isRecentlySold": {"value": True},
    "isForSaleByAgent": {"value": False},
    "isForSaleByOwner": {"value": False},
    "isNewConstruction": {"value": False},
    "isAuction": {"value": False},
    "isForSaleForeclosure": {"value": False},
    "isComingSoon": {"value": False},
}

# Property type exclusions (all false by default, enable what's needed).
_ALL_TYPES_OFF: dict[str, Any] = {
    "isSingleFamily": {"value": False},
    "isCondo": {"value": False},
    "isTownhouse": {"value": False},
    "isMultiFamily": {"value": False},
    "isLotLand": {"value": False},
    "isManufactured": {"value": False},
}


def _build_filter_state(scenario: str, **kwargs: Any) -> dict[str, Any]:
    """Build Zillow filterState for a Kleyman deal-path comp scenario.

    Args:
        scenario: One of "land", "new_build", "renovated", "small_mf", "rental".
        **kwargs: Extra params (e.g., min_acres, max_acres for land).

    Returns:
        filterState dict for Zillow's searchQueryState.
    """
    fs: dict[str, Any] = dict(_ALL_TYPES_OFF)

    if scenario == "land":
        fs["isLotLand"] = {"value": True}
        fs.update(_SOLD_BASE)
        fs["doz"] = {"value": "12m"}
        fs["sortSelection"] = {"value": "days"}
        min_acres = kwargs.get("min_acres")
        max_acres = kwargs.get("max_acres")
        if min_acres is not None or max_acres is not None:
            fs["lotSize"] = {
                "min": min_acres,
                "max": max_acres,
                "units": "acres",
            }

    elif scenario == "new_build":
        fs["isSingleFamily"] = {"value": True}
        fs.update(_SOLD_BASE)
        fs["built"] = {"min": _CURRENT_YEAR - 1, "max": _CURRENT_YEAR}
        fs["doz"] = {"value": "12m"}
        fs["sortSelection"] = {"value": "days"}

    elif scenario == "renovated":
        fs["isSingleFamily"] = {"value": True}
        fs.update(_SOLD_BASE)
        fs["keywords"] = {"value": "renovated"}
        fs["doz"] = {"value": "12m"}
        fs["sortSelection"] = {"value": "days"}

    elif scenario == "small_mf":
        fs["isMultiFamily"] = {"value": True}
        fs.update(_SOLD_BASE)
        fs["doz"] = {"value": "12m"}
        fs["sortSelection"] = {"value": "days"}

    elif scenario == "rental":
        fs["isForRent"] = {"value": True}
        fs["isForSaleByAgent"] = {"value": False}
        fs["isForSaleByOwner"] = {"value": False}
        fs["isNewConstruction"] = {"value": False}
        fs["isAuction"] = {"value": False}
        fs["isForSaleForeclosure"] = {"value": False}
        fs["isComingSoon"] = {"value": False}
        fs["sortSelection"] = {"value": "days"}
        fs["isSingleFamily"] = {"value": True}
        fs["isCondo"] = {"value": True}
        fs["isTownhouse"] = {"value": True}
        fs["isMultiFamily"] = {"value": True}

    return fs


def _build_zillow_url(zip_code: str, filter_state: dict[str, Any]) -> str:
    """Build a Zillow search URL with searchQueryState.

    Args:
        zip_code: 5-digit ZIP code to search in.
        filter_state: filterState dict from _build_filter_state().

    Returns:
        Full Zillow URL with encoded searchQueryState.
    """
    sqs = {
        "pagination": {},
        "isMapVisible": False,
        "isListVisible": True,
        "filterState": filter_state,
        "usersSearchTerm": str(zip_code),
    }
    encoded = urllib.parse.quote(json.dumps(sqs, separators=(",", ":")))
    return f"{_ZILLOW_BASE}/{zip_code}_rb/?searchQueryState={encoded}"


# ---------------------------------------------------------------------------
# __NEXT_DATA__ extraction
# ---------------------------------------------------------------------------

_NEXT_DATA_JS = """
(() => {
    const el = document.getElementById('__NEXT_DATA__');
    if (!el) return null;
    try { return JSON.parse(el.textContent); } catch(_) { return null; }
})()
"""


def _extract_listings(next_data: dict[str, Any], scenario: str) -> list[dict[str, Any]]:
    """Extract listing dicts from __NEXT_DATA__.

    When using searchQueryState, Zillow may place results in cat1 or cat2
    depending on the filter combination. We check both and return whichever
    has results, preferring cat2 for sold scenarios and cat1 for rentals.
    """
    try:
        search_state = next_data["props"]["pageProps"]["searchPageState"]
    except (KeyError, TypeError):
        return []

    cat1_results = (
        search_state.get("cat1", {}).get("searchResults", {}).get("listResults", [])
    )
    cat2_results = (
        search_state.get("cat2", {}).get("searchResults", {}).get("listResults", [])
    )

    is_sold = scenario in ("land", "new_build", "renovated", "small_mf")
    if is_sold:
        return cat2_results if cat2_results else cat1_results
    return cat1_results if cat1_results else cat2_results


def _parse_price(raw_price: Any) -> int:
    """Parse Zillow price value into a numeric integer.

    Handles int, float, and string formats like "$4,700/mo" or "$30,000".
    """
    if isinstance(raw_price, (int, float)):
        return int(raw_price)
    if isinstance(raw_price, str):
        # Strip $, commas, /mo, /mo, and trailing text
        cleaned = raw_price.replace("$", "").replace(",", "").split("/")[0].strip()
        try:
            return int(float(cleaned))
        except (ValueError, TypeError):
            return 0
    return 0


def _extract_sold_price(raw: dict[str, Any], hdp: dict[str, Any]) -> int:
    """Extract sold price from multiple possible Zillow fields.

    Recently-sold listings may store price in:
    1. raw["price"] (top-level, sometimes populated)
    2. hdp["lastSoldPrice"] (homeInfo)
    3. hdp["zestimate"] (fallback estimate)
    4. raw["hdpData"]["priceInfo"]["salePrice"]
    """
    for source in (
        raw.get("price"),
        hdp.get("lastSoldPrice"),
        hdp.get("zestimate"),
        raw.get("hdpData", {}).get("priceInfo", {}).get("salePrice") if isinstance(raw.get("hdpData"), dict) else None,
    ):
        parsed = _parse_price(source)
        if parsed > 0:
            return parsed
    return 0


def normalize_zillow_listing(raw: dict[str, Any], listing_type: str) -> dict[str, Any]:
    """Normalize a raw Zillow listing dict into the standard comp dict.

    Args:
        raw: Raw listing object from Zillow's __NEXT_DATA__.
        listing_type: Scenario name (land, new_build, renovated, small_mf, rental).
    """
    hdp = raw.get("hdpData", {}).get("homeInfo", {}) if isinstance(raw.get("hdpData"), dict) else {}
    lat_long = raw.get("latLong", {}) if isinstance(raw.get("latLong"), dict) else {}
    variable_data = (
        raw.get("variableData", {}) if isinstance(raw.get("variableData"), dict) else {}
    )

    is_sold = listing_type in ("land", "new_build", "renovated", "small_mf")
    price = _extract_sold_price(raw, hdp) if is_sold else _parse_price(raw.get("price", 0))

    return {
        "address": raw.get("address", ""),
        "price": price,
        "bedrooms": hdp.get("bedrooms"),
        "bathrooms": hdp.get("bathrooms"),
        "sqft": hdp.get("livingArea"),
        "lot_sqft": hdp.get("lotAreaValue"),
        "lot_area_units": hdp.get("lotAreaUnits"),
        "year_built": hdp.get("yearBuilt"),
        "property_type": hdp.get("homeType"),
        "sold_date": variable_data.get("sold_date"),
        "latitude": lat_long.get("latitude"),
        "longitude": lat_long.get("longitude"),
        "source_url": raw.get("detailUrl", ""),
        "source_id": str(raw.get("zpid", "")),
        "source": "zillow",
        "listing_type": listing_type,
    }


# ---------------------------------------------------------------------------
# Extraction function (passed to run_stealth_fetch)
# ---------------------------------------------------------------------------


def _make_extract_fn(scenario: str, max_results: int) -> Any:
    """Create a sync extraction function for the SB instance.

    Returns a function that:
    1. Evaluates __NEXT_DATA__ JS on the page
    2. Extracts and normalizes listings
    3. Returns dict with comparables, count, listing_type
    """

    def extract(sb: Any) -> dict[str, Any]:
        next_data_raw = sb.cdp.evaluate(_NEXT_DATA_JS)

        if isinstance(next_data_raw, str):
            try:
                next_data = json.loads(next_data_raw)
            except (json.JSONDecodeError, TypeError):
                next_data = None
        else:
            next_data = next_data_raw

        if not next_data or not isinstance(next_data, dict):
            logger.warning("No __NEXT_DATA__ found for scenario=%s", scenario)
            return {"comparables": [], "count": 0, "listing_type": scenario}

        raw_listings = _extract_listings(next_data, scenario)
        comps = [
            normalize_zillow_listing(raw, scenario)
            for raw in raw_listings[:max_results]
        ]

        logger.info(
            "Extracted %d %s listings (raw: %d)",
            len(comps), scenario, len(raw_listings),
        )
        return {
            "comparables": comps,
            "count": len(comps),
            "listing_type": scenario,
        }

    return extract


# ---------------------------------------------------------------------------
# Registered skill handler
# ---------------------------------------------------------------------------

_VALID_SCENARIOS = frozenset({
    "land", "new_build", "renovated", "small_mf", "rental", "sold", "for_sale",
})


@register_skill("fetch_zillow_comps")
async def handle_fetch_zillow_comps(inputs_json: dict[str, Any]) -> HandlerResult:
    """Scrape Zillow comparables using SeleniumBase UC+CDP stealth mode.

    Supports Daniel Kleyman's deal-path comping methodology with scenario-
    specific Zillow filterState:

    - ``land``: sold land with similar acreage (land basis for land deals)
    - ``new_build``: sold homes built within last year (ARV for Path 1/2)
    - ``renovated``: sold homes with renovation keyword (ARV for Path 1/2)
    - ``small_mf``: sold duplexes/2-4 unit buildings (ARV for Path 2)
    - ``rental``: rental listings (NOI for Path 3, ≥5 units)
    - ``sold``: general recently sold (backwards compat → new_build)
    - ``for_sale``: active for-sale listings (backwards compat → rental)

    Args:
        inputs_json: Dictionary containing:
            - address: Full property address string (required, must include ZIP)
            - listing_type: Scenario name (default "rental")
            - max_results: Maximum listings to return (default 25)
            - min_acres: Min acreage for land scenario (optional)
            - max_acres: Max acreage for land scenario (optional)
            - headless: Run headless (default False — headed is stealthier)
            - cookies: Reusable session cookies from prior scrape (optional)

    Returns:
        HandlerResult with output_json containing:
            - comparables: list of normalized listing dicts
            - source: "zillow"
            - count: number of listings returned
            - listing_type: the scenario searched
            - search_url: the URL scraped
            - cookies: session cookies for reuse (if available)
    """
    address: str = inputs_json.get("address", "")
    scenario: str = inputs_json.get("listing_type", "rental")
    max_results: int = inputs_json.get("max_results", 25)
    headless: bool = inputs_json.get("headless", False)
    cookies_in: list[dict[str, Any]] | None = inputs_json.get("cookies")

    # Backwards compat: map old listing types to scenarios
    if scenario == "sold":
        scenario = "new_build"
    elif scenario == "for_sale":
        scenario = "rental"

    if scenario not in _VALID_SCENARIOS:
        logger.warning("Unknown scenario '%s' — defaulting to 'rental'", scenario)
        scenario = "rental"

    if not address:
        logger.warning("fetch_zillow_comps called without address")
        return HandlerResult(
            output_json={"comparables": [], "source": "zillow", "count": 0, "error": "No address provided"},
        )

    zip_code = _extract_zip(address)
    if not zip_code:
        logger.warning("No ZIP code found in address: %s", address)
        return HandlerResult(
            output_json={
                "comparables": [],
                "source": "zillow",
                "count": 0,
                "error": f"No ZIP code in address: {address}",
            },
        )

    # Build filter state for the Kleyman scenario
    filter_kwargs: dict[str, Any] = {}
    if scenario == "land":
        filter_kwargs["min_acres"] = inputs_json.get("min_acres")
        filter_kwargs["max_acres"] = inputs_json.get("max_acres")

    filter_state = _build_filter_state(scenario, **filter_kwargs)
    url = _build_zillow_url(zip_code, filter_state)

    logger.info("Scraping Zillow %s comps for ZIP %s (from %s)", scenario, zip_code, address)

    extract_fn = _make_extract_fn(scenario, max_results)
    result = await run_stealth_fetch(
        url,
        extract_fn,
        use_chromium=True,
        headless=headless,
        ad_block=True,
        locale="en",
        cookies=cookies_in,
    )

    if "error" in result:
        return HandlerResult(
            output_json={
                "comparables": [],
                "source": "zillow",
                "count": 0,
                "error": result["error"],
                "listing_type": scenario,
                "search_url": url,
            },
        )

    data = result.get("data", {})
    comps = data.get("comparables", [])

    output: dict[str, Any] = {
        "comparables": comps,
        "source": "zillow",
        "count": len(comps),
        "listing_type": scenario,
        "search_url": url,
        "captcha_solved": result.get("captcha_solved", False),
        "title": result.get("title", ""),
    }

    if result.get("cookies"):
        output["cookies"] = result["cookies"]

    logger.info(
        "Returned %d Zillow %s comps for ZIP %s (CAPTCHA solved: %s)",
        len(comps), scenario, zip_code, result.get("captcha_solved", False),
    )

    return HandlerResult(output_json=output)
