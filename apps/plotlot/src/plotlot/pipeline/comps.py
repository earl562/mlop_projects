"""Comparable sales pipeline step.

Searches ArcGIS Hub for recent land sales near a subject parcel and
calculates price-per-acre, ADV per unit, and estimated land value.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any

import httpx

from plotlot.core.types import CompAnalysis, ComparableSale, PropertyRecord
from plotlot.property.arcgis_utils import safe_float

logger = logging.getLogger(__name__)

# ArcGIS Hub search for sales datasets
_HUB_API = "https://hub.arcgis.com/api/v3/datasets"

_SALES_FIELD_KEYWORDS = {
    "SALE_PRICE",
    "SALE_DATE",
    "SALE_AMT",
    "PRICE",
    "TRANS_DATE",
    "TRANS_AMOUNT",
    "OR_BOOK",
    "CONSIDERATION",
    "QUALIFIED",
    "SALE_TYPE",
}
_SALES_NAME_KEYWORDS = {"sale", "transaction", "transfer", "recorded", "deed"}

# Conversion constants
SQFT_PER_ACRE = 43_560
MILES_PER_DEGREE = 69.0  # approximate at mid-latitudes


def _haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two points in miles."""
    r = 3_958.8  # Earth radius in miles
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


async def _discover_sales_dataset(
    county: str,
    state: str,
    timeout: float = 15.0,
) -> tuple[str, list[str]] | None:
    """Search ArcGIS Hub for sales/transactions dataset in a county.

    Returns (layer_url, field_names) or None.
    """
    queries = [
        f"sales {county} {state}",
        f"transactions {county} {state}",
        f"property {county} {state} sales",
    ]
    async with httpx.AsyncClient(timeout=timeout) as client:
        for q in queries:
            try:
                resp = await client.get(
                    _HUB_API,
                    params={
                        "q": q,
                        "filter[type]": "Feature Service",
                        "page[size]": "5",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception:
                logger.debug("Hub sales search failed for: %s", q)
                continue

            for ds in data.get("data", []):
                attrs = ds.get("attributes", {})
                name = (attrs.get("name") or "").lower()
                fields_raw = attrs.get("fields", [])
                if isinstance(fields_raw, list):
                    field_names = [
                        f.get("name", "") if isinstance(f, dict) else str(f) for f in fields_raw
                    ]
                else:
                    field_names = []

                upper_fields = {f.upper() for f in field_names}
                # Score: how many sales keywords match?
                score = len(upper_fields & _SALES_FIELD_KEYWORDS)
                name_bonus = sum(2 for kw in _SALES_NAME_KEYWORDS if kw in name)
                total = score + name_bonus

                if total >= 3:
                    url = attrs.get("url", "")
                    if url:
                        return url, field_names

    return None


def _find_field(fields: list[str], candidates: set[str]) -> str | None:
    """Find the first matching field name (case-insensitive)."""
    upper_map = {f.upper(): f for f in fields}
    for c in candidates:
        if c in upper_map:
            return upper_map[c]
    return None


async def _query_nearby_sales(
    layer_url: str,
    lat: float,
    lng: float,
    radius_miles: float = 3.0,
    months: int = 12,
    limit: int = 20,
    timeout: float = 20.0,
) -> list[dict[str, Any]]:
    """Query ArcGIS layer for recent sales within radius."""
    # Build bounding box from radius
    lat_delta = radius_miles / MILES_PER_DEGREE
    lng_delta = radius_miles / (MILES_PER_DEGREE * math.cos(math.radians(lat)))

    envelope = {
        "xmin": lng - lng_delta,
        "ymin": lat - lat_delta,
        "xmax": lng + lng_delta,
        "ymax": lat + lat_delta,
        "spatialReference": {"wkid": 4326},
    }

    params = {
        "geometry": str(envelope).replace("'", '"'),
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "outSR": "4326",
        "returnGeometry": "true",
        "f": "json",
        "resultRecordCount": str(limit),
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(layer_url, params=params)
        resp.raise_for_status()
        data = resp.json()

    features: list[dict[str, Any]] = data.get("features", [])
    return features


def _parse_sale_date(val: object) -> str:
    """Parse ArcGIS date value (epoch ms or string) to YYYY-MM-DD."""
    if val is None:
        return ""
    if isinstance(val, (int, float)) and val > 1_000_000_000:
        # Epoch milliseconds
        try:
            dt = datetime.fromtimestamp(val / 1000, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d")
        except (ValueError, OSError):
            return ""
    return str(val)[:10]


def _is_arms_length(price: float) -> bool:
    """Filter out non-arm's-length transactions."""
    return price > 1_000  # Exclude $0, $10, $100 transfers


async def find_comparables(
    subject: PropertyRecord,
    state: str = "FL",
    radius_miles: float = 3.0,
    months: int = 12,
    max_comps: int = 5,
) -> CompAnalysis:
    """Find comparable land sales near the subject property.

    Args:
        subject: The subject property record
        state: Two-letter state code
        radius_miles: Search radius in miles
        months: How far back to look for sales
        max_comps: Maximum comparable sales to return

    Returns:
        CompAnalysis with comparable sales and metrics
    """
    result = CompAnalysis()

    if not subject.lat or not subject.lng or not subject.county:
        result.notes = ["Missing lat/lng or county — cannot search for comps"]
        return result

    # Discover sales dataset
    sales_info = await _discover_sales_dataset(subject.county, state)
    if not sales_info:
        result.notes = [f"No sales dataset found for {subject.county} County, {state}"]
        return result

    layer_url, fields = sales_info
    logger.info("Found sales dataset: %s (%d fields)", layer_url, len(fields))

    # Find relevant field names
    price_field = _find_field(
        fields, {"SALE_PRICE", "SALE_AMT", "PRICE", "CONSIDERATION", "TRANS_AMOUNT"}
    )
    date_field = _find_field(
        fields, {"SALE_DATE", "TRANS_DATE", "SALE_DT", "DATE_SOLD", "RECORDING_DATE"}
    )
    addr_field = _find_field(
        fields, {"SITE_ADDR", "ADDRESS", "SITUS_ADDR", "PROP_ADDR", "SITEADDR", "TRUE_SITE_ADDR"}
    )
    lot_field = _find_field(
        fields, {"LOT_SIZE", "LOT_AREA", "LAND_SQFT", "ACRES", "ACREAGE", "SQ_FOOTAGE"}
    )
    zone_field = _find_field(fields, {"ZONE_CODE", "ZONING", "ZONING_CODE", "ZONE", "ZONE_CLASS"})

    if not price_field:
        result.notes = ["Sales dataset found but no price field identified"]
        return result

    # Query nearby features
    try:
        features = await _query_nearby_sales(
            layer_url, subject.lat, subject.lng, radius_miles, months
        )
    except Exception as e:
        logger.warning("Sales query failed: %s", e)
        result.notes = [f"Sales query failed: {e}"]
        return result

    logger.info("Found %d nearby sale features", len(features))

    # Process features into ComparableSale objects
    comps: list[ComparableSale] = []
    for feat in features:
        attrs = feat.get("attributes", {})
        price = safe_float(attrs.get(price_field))

        if not _is_arms_length(price):
            continue

        # Get lot size
        lot_sqft = 0.0
        if lot_field:
            raw_lot = safe_float(attrs.get(lot_field))
            field_upper = lot_field.upper()
            if field_upper in ("ACRES", "ACREAGE") and raw_lot > 0:
                lot_sqft = raw_lot * SQFT_PER_ACRE
            elif raw_lot > 0:
                lot_sqft = raw_lot

        # Filter by lot size similarity (±30% of subject)
        if subject.lot_size_sqft > 0 and lot_sqft > 0:
            ratio = lot_sqft / subject.lot_size_sqft
            if ratio < 0.7 or ratio > 1.3:
                continue

        # Calculate distance
        geom = feat.get("geometry", {})
        feat_lat = geom.get("y") or geom.get("lat")
        feat_lng = geom.get("x") or geom.get("lng") or geom.get("lon")
        distance = 0.0
        if feat_lat and feat_lng:
            distance = _haversine_miles(subject.lat, subject.lng, feat_lat, feat_lng)
            if distance > radius_miles:
                continue

        sale_date = _parse_sale_date(attrs.get(date_field)) if date_field else ""
        address = str(attrs.get(addr_field, "")) if addr_field else ""
        zoning = str(attrs.get(zone_field, "")) if zone_field else ""

        acres = lot_sqft / SQFT_PER_ACRE if lot_sqft > 0 else 0
        ppa = price / acres if acres > 0 else 0

        comp = ComparableSale(
            address=address,
            sale_price=price,
            sale_date=sale_date,
            lot_size_sqft=lot_sqft,
            zoning_code=zoning,
            distance_miles=round(distance, 2),
            price_per_acre=round(ppa, 2),
        )
        comps.append(comp)

    # Sort by distance (closer = better), take top N
    comps.sort(key=lambda c: c.distance_miles)
    comps = comps[:max_comps]

    if not comps:
        result.notes = [
            f"No qualifying comps found within {radius_miles} mi (checked {len(features)} sales)"
        ]
        return result

    # Calculate aggregate metrics
    prices_per_acre = [c.price_per_acre for c in comps if c.price_per_acre > 0]
    if prices_per_acre:
        prices_per_acre.sort()
        mid = len(prices_per_acre) // 2
        if len(prices_per_acre) % 2 == 0:
            result.median_price_per_acre = (prices_per_acre[mid - 1] + prices_per_acre[mid]) / 2
        else:
            result.median_price_per_acre = prices_per_acre[mid]

    # Estimated land value = subject acres × median price/acre
    if result.median_price_per_acre > 0 and subject.lot_size_sqft > 0:
        subject_acres = subject.lot_size_sqft / SQFT_PER_ACRE
        result.estimated_land_value = round(subject_acres * result.median_price_per_acre, 2)

    result.comparables = comps

    # Confidence scoring
    n = len(comps)
    if n >= 5:
        result.confidence = 0.9
    elif n >= 3:
        result.confidence = 0.75
    elif n >= 1:
        result.confidence = 0.5
    else:
        result.confidence = 0.0

    return result
