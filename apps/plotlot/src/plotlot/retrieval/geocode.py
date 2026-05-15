"""Geocodio address resolution — address to municipality + coordinates.

Uses the Geocodio API (primary) with US Census Geocoder fallback.
Fallback chain: Geocodio → Census Geocoder (free, no API key needed).

Includes in-memory cache with 1hr TTL (Care Access pattern: 86% cost reduction).
"""

import hashlib
import logging
import re
import time

import httpx

from plotlot.config import settings
from plotlot.observability.tracing import trace

logger = logging.getLogger(__name__)

GEOCODIO_URL = "https://api.geocod.io/v1.7/geocode"
CENSUS_GEOCODER_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"

# In-memory geocode cache — 1hr TTL, SHA256 key
_geocode_cache: dict[str, tuple[dict | None, float]] = {}
GEOCODE_CACHE_TTL = 3600  # 1 hour


def _cache_key(address: str) -> str:
    """Generate a stable cache key from an address."""
    normalized = address.strip().lower()
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


async def _census_geocode(address: str) -> dict | None:
    """Geocode an address using the free US Census Geocoder API.

    This is the fallback provider — no API key required.

    Returns:
        Dict with keys: formatted_address, municipality, county, lat, lng, accuracy
        or None if the Census geocoder fails or returns no matches.
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                CENSUS_GEOCODER_URL,
                params={
                    "address": address,
                    "benchmark": "Public_AR_Current",
                    "format": "json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        logger.warning("Census geocoder request failed for: %s", address[:40], exc_info=True)
        return None

    matches = data.get("result", {}).get("addressMatches", [])
    if not matches:
        logger.warning("Census geocoder returned no matches for: %s", address[:40])
        return None

    top = matches[0]
    coords = top.get("coordinates", {})
    matched_address = top.get("matchedAddress", address)

    # Census returns addressComponents with city, state, etc.
    components = top.get("addressComponents", {})
    city = components.get("city", "")

    # Census does not return county directly in the geocoder response —
    # extract from tigerLine or leave empty for downstream enrichment
    county = ""

    return {
        "formatted_address": matched_address,
        "municipality": city,
        "county": county,
        "lat": coords.get("y"),  # Census uses y for latitude
        "lng": coords.get("x"),  # Census uses x for longitude
        "accuracy": None,
        "accuracy_type": "census_geocoder",
        "geocode_provider": "census",
    }


@trace(name="geocode_address", span_type="TOOL")
async def geocode_address(address: str) -> dict | None:
    """Geocode an address and extract municipality info.

    Fallback chain: Geocodio (primary) → US Census Geocoder (free).

    Returns:
        Dict with keys: formatted_address, municipality, county, lat, lng, accuracy
        or None if all providers fail.
    """
    # Check cache first
    key = _cache_key(address)
    if key in _geocode_cache:
        cached_result, cached_time = _geocode_cache[key]
        if time.monotonic() - cached_time < GEOCODE_CACHE_TTL:
            logger.info("Geocode cache hit for: %s", address[:40])
            return cached_result

    # --- Provider 1: Geocodio (primary) ---
    result = await _geocodio_geocode(address)
    if result:
        result["geocode_provider"] = "geocodio"
        logger.info("Geocoded via Geocodio: %s", address[:40])
        _geocode_cache[key] = (result, time.monotonic())
        return result

    # --- Provider 2: US Census Geocoder (fallback) ---
    logger.info("Geocodio failed, falling back to Census geocoder for: %s", address[:40])
    result = await _census_geocode(address)
    if result:
        logger.info("Geocoded via Census geocoder: %s", address[:40])
        _geocode_cache[key] = (result, time.monotonic())
        return result

    logger.error("All geocoding providers failed for: %s", address[:40])
    return None


async def _geocodio_geocode(address: str) -> dict | None:
    """Geocode via Geocodio API. Returns None on failure or missing API key."""
    if not settings.geocodio_api_key:
        logger.warning("GEOCODIO_API_KEY not set — skipping Geocodio")
        return None

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                GEOCODIO_URL,
                params={"q": address, "api_key": settings.geocodio_api_key},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        logger.warning("Geocodio request failed for: %s", address[:40], exc_info=True)
        return None

    results = data.get("results", [])
    if not results:
        logger.warning("No Geocodio results for: %s", address)
        return None

    top = results[0]
    components = top.get("address_components", {})
    location = top.get("location", {})

    city = components.get("city", "")
    county = components.get("county", "")
    state = components.get("state", "")

    # Geocodio returns county as "Miami-Dade County" — normalize
    county_clean = re.sub(r"\s+County$", "", county).strip()

    return {
        "formatted_address": top.get("formatted_address", address),
        "municipality": city,
        "county": county_clean,
        "state": state,
        "lat": location.get("lat"),
        "lng": location.get("lng"),
        "accuracy": top.get("accuracy"),  # numeric score (0-1)
        "accuracy_type": top.get("accuracy_type", ""),  # string type (rooftop, etc.)
    }


def address_to_municipality_key(municipality: str) -> str:
    """Convert a municipality name from Geocodio to a Municode config key.

    'Miramar' → 'miramar'
    'Fort Lauderdale' → 'fort_lauderdale'
    'Miami Gardens' → 'miami_gardens'
    """
    key = municipality.lower().strip()
    key = re.sub(r"[^a-z0-9\s]", " ", key)
    key = re.sub(r"\s+", "_", key.strip())
    return key


def county_to_key(county: str) -> str:
    """Convert a county name from Geocodio to our county key.

    'Miami-Dade' → 'miami_dade'
    'Broward' → 'broward'
    'Palm Beach' → 'palm_beach'
    """
    key = county.lower().strip()
    key = re.sub(r"[^a-z0-9\s]", " ", key)
    key = re.sub(r"\s+", "_", key.strip())
    return key
