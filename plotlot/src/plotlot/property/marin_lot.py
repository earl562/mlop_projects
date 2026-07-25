"""Marin County authoritative parcel lot area by APN.

The CA statewide parcel layer's polygon area is a coarse aggregation that
under-estimates Marin lots — 416 Richardson St, Sausalito reads **765 sqft**
from the statewide layer but **1,162 sqft** in Marin County's own parcel
fabric. The county layer (NAD83 State Plane Zone III, US feet) is the
authoritative cadastral boundary maintained by the County Assessor; its
``Shape__Area`` is the legal lot area and is already in square feet.

Mirrors ``marin_zoning.py`` — a Marin-specific enrichment the statewide path
calls so a Marin by-right count is built on the real lot, not a coarse estimate.
"""

from __future__ import annotations

import logging
import re

import httpx

logger = logging.getLogger(__name__)

# Marin County Parcels feature service (opendata_MarinCounty). The `Parcel`
# field is the APN with non-digits stripped (065-234-10 → 06523410); the layer
# SR is wkid 2872 (US survey feet), so Shape__Area is already square feet.
_MARIN_PARCELS_URL = (
    "https://services6.arcgis.com/T8eS7sop5hLmgRRH/arcgis/rest/services"
    "/Parcels/FeatureServer/0/query"
)


async def resolve_marin_lot_sqft(apn: str) -> float | None:
    """Return the Marin County parcel-fabric lot area (sqft) for an APN, or None.

    None on any miss/failure — the caller keeps the statewide estimate and flags
    it as unconfirmed rather than substituting a guess (fail loud, per the
    anti-hallucination doctrine).
    """
    digits = re.sub(r"\D", "", apn or "")
    if len(digits) < 8:
        return None
    params = {
        "where": f"Parcel='{digits}'",
        "outFields": "Shape__Area",
        "returnGeometry": "false",
        "f": "json",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(_MARIN_PARCELS_URL, params=params)
            resp.raise_for_status()
            features = resp.json().get("features", [])
        if not features:
            return None
        area = features[0].get("attributes", {}).get("Shape__Area")
        return float(area) if area and float(area) > 0 else None
    except Exception as exc:
        logger.debug("Marin lot lookup failed for APN %s: %s", apn, exc)
        return None
