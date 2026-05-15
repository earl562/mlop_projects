"""Reusable ArcGIS REST API utilities.

Extracted from retrieval/property.py for use by the UniversalProvider
and existing per-county providers.
"""

from __future__ import annotations

import logging
import re

import httpx

logger = logging.getLogger(__name__)


def normalize_address(address: str) -> str:
    """Normalize an address for ArcGIS WHERE clause matching.

    Strips city/state/zip, uppercases, removes punctuation.
    '171 NE 209th Ter, Miami, FL 33179' → '171 NE 209 TER'
    """
    street = address.split(",")[0].strip().upper()
    street = re.sub(r"(\d+)(ST|ND|RD|TH)\b", r"\1", street)
    street = street.replace(".", "")
    return street


def safe_float(val: object) -> float:
    """Convert a value to float, stripping currency symbols and commas."""
    if val is None:
        return 0.0
    s = str(val).replace("$", "").replace(",", "").strip()
    if not s:
        return 0.0
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def extract_parcel_rings(feature: dict) -> list[list[float]] | None:
    """Extract outer ring from ArcGIS polygon geometry.

    ArcGIS polygon geometry: {"rings": [[[x1,y1],[x2,y2],...], ...]}
    Returns the outer ring as [[lng, lat], ...] or None if unavailable.
    Requires outSR=4326 on the query for WGS84 coordinates.
    """
    geom = feature.get("geometry", {})
    rings = geom.get("rings")
    if rings and len(rings) > 0 and len(rings[0]) >= 3:
        return rings[0]  # type: ignore[no-any-return]
    return None


def parse_lot_dimensions(legal: str) -> str:
    """Extract lot dimensions from legal description.

    'LOT SIZE 75.000 X 100' → '75 x 100'
    """
    if not legal:
        return ""
    match = re.search(r"(\d+(?:\.\d+)?)\s*[Xx]\s*(\d+(?:\.\d+)?)", legal)
    if match:
        w = match.group(1)
        h = match.group(2)
        if "." in w:
            w = w.rstrip("0").rstrip(".")
        if "." in h:
            h = h.rstrip("0").rstrip(".")
        return f"{w} x {h}"
    return ""


async def query_arcgis(
    url: str,
    where: str,
    out_fields: str = "*",
    extra_params: dict | None = None,
    limit: int | None = 5,
    timeout: float = 20.0,
) -> list[dict]:
    """Execute an ArcGIS REST query and return features."""
    params: dict[str, str] = {
        "where": where,
        "outFields": out_fields,
        "f": "json",
        "returnGeometry": "true",
    }
    if limit:
        params["resultRecordCount"] = str(limit)
    if extra_params:
        params.update(extra_params)

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    features = data.get("features", [])
    if not features:
        logger.debug("ArcGIS query returned 0 features: %s", where[:200])
    return features  # type: ignore[no-any-return]


async def spatial_query(
    url: str,
    lat: float,
    lng: float,
    out_fields: str = "*",
    out_sr: int = 4326,
    timeout: float = 20.0,
) -> list[dict]:
    """Point-in-polygon spatial query via ArcGIS REST API."""
    params = {
        "geometry": f"{lng},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": out_fields,
        "outSR": str(out_sr),
        "returnGeometry": "true",
        "f": "json",
        "resultRecordCount": "1",
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    features = data.get("features", [])
    if not features:
        logger.debug("Spatial query returned 0 features at (%.4f, %.4f)", lat, lng)
    return features  # type: ignore[no-any-return]
