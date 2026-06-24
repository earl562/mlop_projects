"""Playwright-based Zillow comps skill — extracts sold/rental comparables via __NEXT_DATA__.

Handles three listing types:
- "sold" → cat2.searchResults.listResults
- "rental" → cat1.searchResults.listResults
- "for_sale" → cat1.searchResults.listResults (no trailing path segment)
"""

from __future__ import annotations

import logging
from typing import Any

try:
    from playwright.async_api import async_playwright  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover — playwright not installed in dev
    async_playwright = None  # type: ignore[assignment]

from plotlot.pipeline.skills.registry import HandlerResult, register_skill

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# URL / slug construction
# ---------------------------------------------------------------------------

_ZILLOW_BASE = "https://www.zillow.com/homes"

# Realistic desktop Chrome UA + viewport (anti-detection baseline).
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
_VIEWPORT = {"width": 1920, "height": 1080}

_PAGE_TIMEOUT_MS = 30_000
_PAGE_WAIT_UNTIL = "networkidle"


def _address_to_slug(address: str) -> str:
    """Normalize an address string to a Zillow URL slug.

    Lowercases, replaces non-alphanumeric runs with a single hyphen, and
    strips leading/trailing hyphens.

    >>> _address_to_slug("123 Main St, Miami, FL 33169")
    '123-main-st-miami-fl-33169'
    """
    slug = ""
    prev_hyphen = True  # suppress leading hyphen
    for ch in address.lower():
        if ch.isalnum():
            slug += ch
            prev_hyphen = False
        elif not prev_hyphen:
            slug += "-"
            prev_hyphen = True
    return slug.rstrip("-")


def _build_zillow_url(address_slug: str, listing_type: str) -> str:
    """Build the Zillow search URL for a given address slug and listing type.

    "sold" and "rental" append a trailing path segment; "for_sale" does not.
    """
    path = f"/{listing_type}/" if listing_type in ("sold", "rental") else "/"
    return f"{_ZILLOW_BASE}/{address_slug}_rb{path}"


# ---------------------------------------------------------------------------
# __NEXT_DATA__ extraction helpers
# ---------------------------------------------------------------------------


def _extract_listings(next_data: dict[str, Any], listing_type: str) -> list[dict[str, Any]]:
    """Extract listing dicts from a parsed __NEXT_DATA__ payload.

    - "sold"  → cat2.searchResults.listResults
    - "rental" / "for_sale"  → cat1.searchResults.listResults
    """
    cat_key = "cat2" if listing_type == "sold" else "cat1"
    try:
        search_state = next_data["props"]["pageProps"]["searchPageState"]
        results: list[dict[str, Any]] = (
            search_state.get(cat_key, {}).get("searchResults", {}).get("listResults", [])
        )
        return results
    except (KeyError, TypeError):
        return []


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def normalize_zillow_listing(raw: dict[str, Any], listing_type: str) -> dict[str, Any]:
    """Normalize a single raw Zillow listing dict into the standard comp dict.

    Returns a flat dict with keys: address, price, bedrooms, bathrooms, sqft,
    lot_sqft, year_built, property_type, sold_date, latitude, longitude,
    source_url, source_id, source, listing_type.

    Args:
        raw: Raw listing object from Zillow's __NEXT_DATA__.
        listing_type: "sold", "rental", or "for_sale".
    """
    hdp = raw.get("hdpData", {}).get("homeInfo", {}) if isinstance(raw.get("hdpData"), dict) else {}
    lat_long = raw.get("latLong", {}) if isinstance(raw.get("latLong"), dict) else {}
    variable_data = (
        raw.get("variableData", {}) if isinstance(raw.get("variableData"), dict) else {}
    )

    return {
        "address": raw.get("address", ""),
        "price": raw.get("price", 0),
        "bedrooms": hdp.get("bedrooms"),
        "bathrooms": hdp.get("bathrooms"),
        "sqft": hdp.get("livingArea"),
        "lot_sqft": hdp.get("lotAreaValue"),
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
# Registered skill handler
# ---------------------------------------------------------------------------


@register_skill("fetch_zillow_comps")
async def handle_fetch_zillow_comps(inputs_json: dict[str, Any]) -> HandlerResult:
    """Scrape Zillow sold/rental comparable listings via __NEXT_DATA__ extraction.

    Args:
        inputs_json: Dictionary containing:
            - address: Full property address string (required)
            - listing_type: "sold", "rental", or "for_sale" (default "sold")
            - max_results: Maximum listings to return (default 25)

    Returns:
        HandlerResult with output_json containing:
            - comparables: list of normalized listing dicts
            - source: "zillow"
            - count: number of listings returned
            - listing_type: the listing type searched
    """
    address: str = inputs_json.get("address", "")
    listing_type: str = inputs_json.get("listing_type", "sold")
    max_results: int = inputs_json.get("max_results", 25)

    if not address:
        logger.warning("fetch_zillow_comps called without address")
        return HandlerResult(
            output_json={"comparables": [], "source": "zillow", "count": 0, "error": "No address provided"},
        )

    if async_playwright is None:
        logger.warning("playwright package not installed — cannot scrape Zillow")
        return HandlerResult(
            output_json={
                "comparables": [],
                "source": "zillow",
                "count": 0,
                "error": "playwright package not installed",
            },
        )

    slug = _address_to_slug(address)
    url = _build_zillow_url(slug, listing_type)
    logger.info("Scraping Zillow %s listings for %s", listing_type, address)

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=_UA, viewport=_VIEWPORT)
            page = await context.new_page()

            try:
                await page.goto(url, wait_until=_PAGE_WAIT_UNTIL, timeout=_PAGE_TIMEOUT_MS)

                next_data: dict[str, Any] | None = await page.evaluate("""
                    () => {
                        const el = document.getElementById('__NEXT_DATA__');
                        if (!el) return null;
                        try {
                            return JSON.parse(el.textContent);
                        } catch (_) {
                            return null;
                        }
                    }
                """)

                if not next_data:
                    logger.warning("No __NEXT_DATA__ found for %s", url)
                    raw_listings: list[dict[str, Any]] = []
                else:
                    raw_listings = _extract_listings(next_data, listing_type)

            finally:
                await browser.close()

    except Exception as exc:
        logger.exception("Zillow scrape failed for %s: %s", address, exc)
        return HandlerResult(
            output_json={
                "comparables": [],
                "source": "zillow",
                "count": 0,
                "error": str(exc),
            },
        )

    comps = [
        normalize_zillow_listing(raw, listing_type) for raw in raw_listings[:max_results]
    ]

    logger.info("Returned %d Zillow %s listings for %s", len(comps), listing_type, address)
    return HandlerResult(
        output_json={
            "comparables": comps,
            "source": "zillow",
            "count": len(comps),
            "listing_type": listing_type,
            "search_url": url,
        },
    )
