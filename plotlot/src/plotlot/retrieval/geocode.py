"""Geocodio address resolution — address to municipality + coordinates.

Uses the Geocodio API to geocode an address and extract the municipality
(city/place) for mapping into Municode configs.
"""

import logging
import re

import httpx

from plotlot.config import settings
from plotlot.observability.tracing import trace

logger = logging.getLogger(__name__)

GEOCODIO_URL = "https://api.geocod.io/v1.7/geocode"


@trace(name="geocode_address", span_type="TOOL")
async def geocode_address(address: str) -> dict | None:
    """Geocode an address and extract municipality info.

    Returns:
        Dict with keys: formatted_address, municipality, county, lat, lng, accuracy
        or None if geocoding fails.
    """
    if not settings.geocodio_api_key:
        logger.error("GEOCODIO_API_KEY not set")
        return None

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            GEOCODIO_URL,
            params={"q": address, "api_key": settings.geocodio_api_key},
        )
        resp.raise_for_status()
        data = resp.json()

    results = data.get("results", [])
    if not results:
        logger.warning("No geocoding results for: %s", address)
        return None

    top = results[0]
    components = top.get("address_components", {})
    location = top.get("location", {})

    city = components.get("city", "")
    county = components.get("county", "")

    # Geocodio returns county as "Miami-Dade County" — normalize
    county_clean = re.sub(r"\s+County$", "", county).strip()

    return {
        "formatted_address": top.get("formatted_address", address),
        "municipality": city,
        "county": county_clean,
        "lat": location.get("lat"),
        "lng": location.get("lng"),
        "accuracy": top.get("accuracy"),
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
