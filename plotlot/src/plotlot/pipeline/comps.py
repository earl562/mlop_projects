"""Comparable sales pipeline step.

Searches ArcGIS Hub for recent sales near a subject parcel and produces two
distinct comp sets:

  1. **Land comps** — vacant parcels, used for price-per-acre, an estimated
     land-value band (25th–75th percentile), and a confidence score.
  2. **Unit (exit) comps** — improved/finished sales, used to derive the
     after-development value (ADV) per unit that feeds the residual pro forma.

Recency is enforced (sales outside the lookback window are dropped), the
candidate pool is ordered newest-first, and improved parcels are excluded from
land comps so structures don't inflate land $/acre.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
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

# Candidate field names for each datum (case-insensitive).
_PRICE_FIELDS = {"SALE_PRICE", "SALE_AMT", "SALE_AMOUNT", "PRICE", "CONSIDERATION", "TRANS_AMOUNT"}
_DATE_FIELDS = {
    "SALE_DATE",
    "TRANS_DATE",
    "SALE_DT",
    "DATE_SOLD",
    "RECORDING_DATE",
    "DOS",
    "DATEOFSALE",
}
_ADDR_FIELDS = {"SITE_ADDR", "ADDRESS", "SITUS_ADDR", "PROP_ADDR", "SITEADDR", "TRUE_SITE_ADDR"}
_LOT_FIELDS = {"LOT_SIZE", "LOT_AREA", "LAND_SQFT", "ACRES", "ACREAGE", "SQ_FOOTAGE"}
_ZONE_FIELDS = {"ZONE_CODE", "ZONING", "ZONING_CODE", "ZONE", "ZONE_CLASS"}
# Improvement signals — presence of any (> 0) marks a parcel as improved.
_UNITS_FIELDS = {
    "UNITS",
    "NO_UNITS",
    "LIVING_UNITS",
    "UNIT_COUNT",
    "NO_OF_UNITS",
    "RESIDENTIAL_UNITS",
    "BLDG_CNT",
}
_BLDG_AREA_FIELDS = {
    "BLDG_SQFT",
    "BUILDING_AREA",
    "TOT_LVG_AR",
    "TOT_LVG_AREA",
    "HEATED_AREA",
    "LIVING_AREA",
    "GLA",
    "BLDG_AREA",
    "SFLA",
}
_YEAR_FIELDS = {"YEAR_BUILT", "YR_BLT", "ACT_YR_BLT", "EFF_YR_BLT", "YRBLT", "YEARBUILT"}
_IMPRV_FIELDS = {
    "IMPR_VAL",
    "BLDG_VAL",
    "IMP_VAL",
    "IMPROVEMENT_VALUE",
    "BUILDING_VALUE",
    "JV_BLDG",
}

# Conversion constants
SQFT_PER_ACRE = 43_560
MILES_PER_DEGREE = 69.0  # approximate at mid-latitudes
_DAYS_PER_MONTH = 30.44


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested without network access)
# ---------------------------------------------------------------------------


def _haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two points in miles."""
    r = 3_958.8  # Earth radius in miles
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _percentile(sorted_vals: list[float], pct: float) -> float:
    """Linear-interpolation percentile of an ascending-sorted list.

    pct is 0–100. Returns 0.0 for an empty list.
    """
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (pct / 100.0)
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return sorted_vals[int(k)]
    return sorted_vals[lo] * (hi - k) + sorted_vals[hi] * (k - lo)


def _price_range(values: list[float]) -> tuple[float, float, float]:
    """Return (p25, median, p75) of a list of positive values."""
    vals = sorted(v for v in values if v > 0)
    if not vals:
        return 0.0, 0.0, 0.0
    return _percentile(vals, 25), _percentile(vals, 50), _percentile(vals, 75)


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


def _within_months(date_str: str, months: int, now: datetime | None = None) -> bool:
    """True if ``date_str`` (YYYY-MM-DD) is within ``months`` of ``now``.

    Unknown or unparseable dates return True (we don't exclude on missing data).
    """
    if not date_str:
        return True
    now = now or datetime.now(timezone.utc)
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return True
    cutoff = now - timedelta(days=round(months * _DAYS_PER_MONTH))
    return d >= cutoff


def _is_arms_length(price: float) -> bool:
    """Filter out non-arm's-length transactions."""
    return price > 1_000  # Exclude $0, $10, $100 transfers


def _find_field(fields: list[str], candidates: set[str]) -> str | None:
    """Find the first matching field name (case-insensitive).

    Matches exactly first, then falls back to substring/contains matching so
    DB-qualified names (e.g. "SQLGIS02.dbo.BCPA_SALES.SALE_AMOUNT") and
    suffixed names (e.g. "PRICE_1", "DOS_1") resolve against the candidate
    set. Without the substring fallback, Broward + Miami-Dade registered sources
    silently produced 0 comps because price_field/date_field were None.
    """
    upper_map = {f.upper(): f for f in fields}
    for c in candidates:
        if c in upper_map:
            return upper_map[c]
    # Substring fallback: candidate appears anywhere in the field name.
    for c in candidates:
        for upper_name, original in upper_map.items():
            if c in upper_name:
                return original
    return None


def _classify_improved(
    attrs: dict[str, Any],
    units_field: str | None,
    bldg_area_field: str | None,
    year_field: str | None,
    imprv_field: str | None,
) -> tuple[bool, int]:
    """Classify a sale as improved (has a structure) and return its unit count.

    Returns (is_improved, units). Units defaults to 1 for an improved parcel
    with no explicit unit count (i.e. a single-family home).
    """
    units = safe_float(attrs.get(units_field)) if units_field else 0.0
    bldg_area = safe_float(attrs.get(bldg_area_field)) if bldg_area_field else 0.0
    year = safe_float(attrs.get(year_field)) if year_field else 0.0
    imprv = safe_float(attrs.get(imprv_field)) if imprv_field else 0.0

    is_improved = bldg_area > 0 or year > 1800 or imprv > 0 or units >= 1
    unit_count = int(units) if units >= 1 else (1 if is_improved else 0)
    return is_improved, unit_count


def _feature_latlng(geom: dict[str, Any]) -> tuple[float, float] | None:
    """Extract a representative (lat, lng) from ArcGIS geometry.

    Handles point geometry (x/y) and polygon geometry (rings → centroid).
    """
    if not geom:
        return None
    x = geom.get("x")
    y = geom.get("y")
    if x is not None and y is not None:
        return float(y), float(x)
    rings = geom.get("rings") or geom.get("paths")
    if rings and rings[0]:
        pts = rings[0]
        lngs = [p[0] for p in pts if len(p) >= 2]
        lats = [p[1] for p in pts if len(p) >= 2]
        if lats and lngs:
            return sum(lats) / len(lats), sum(lngs) / len(lngs)
    return None


# ---------------------------------------------------------------------------
# Network steps
# ---------------------------------------------------------------------------


async def _discover_sales_dataset(
    county: str,
    state: str,
    timeout: float = 15.0,
) -> tuple[str, list[str]] | None:
    """Search ArcGIS Hub for a sales/transactions dataset in a county.

    Returns (layer_url, field_names) or None.
    """
    queries = [
        f"sales {county} {state}",
        f"transactions {county} {state}",
        f"property {county} {state} sales",
        f"assessor {county} {state}",  # some counties publish sales via the assessor
        f"parcel {county} {state}",  # parcel layers occasionally carry sale price/date
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


async def _query_nearby_sales(
    layer_url: str,
    lat: float,
    lng: float,
    radius_miles: float = 3.0,
    limit: int = 200,
    order_by: str | None = None,
    timeout: float = 20.0,
) -> list[dict[str, Any]]:
    """Query an ArcGIS layer for sales within a radius bounding box.

    Returns up to ``limit`` features, ordered newest-first when ``order_by``
    (a date field name) is supplied so the closest/most-recent survive
    downstream filtering.
    """
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
        "where": "1=1",
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
    if order_by:
        params["orderByFields"] = f"{order_by} DESC"

    async with httpx.AsyncClient(timeout=timeout) as client:
        # ArcGIS layer query endpoint is <layer_url>/query. Registered layer URLs
        # are stored as the layer resource (.../FeatureServer/0), not the query
        # endpoint. Without this suffix, ArcGIS returns service metadata (0 features).
        query_url = layer_url if layer_url.endswith("/query") else f"{layer_url}/query"
        resp = await client.get(query_url, params=params)
        resp.raise_for_status()
        data = resp.json()

    features: list[dict[str, Any]] = data.get("features", [])
    return features


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _score_confidence(land_count: int, fraction_recent_6mo: float) -> float:
    """Confidence from land-comp count and recency (see comping methodology)."""
    if land_count >= 5:
        return 0.9 if fraction_recent_6mo >= 0.5 else 0.8
    if land_count >= 3:
        return 0.75
    if land_count >= 1:
        return 0.5
    return 0.0


async def _try_rentcast_comps(
    subject: PropertyRecord, radius_miles: float, months: int
) -> CompAnalysis | None:
    """Keyed RentCast comps fallback (lazy import → no circular dependency)."""
    from plotlot.pipeline.comps_rentcast import fetch_rentcast_comps, rentcast_configured

    if not rentcast_configured():
        return None
    try:
        return await fetch_rentcast_comps(subject, radius_miles, months)
    except Exception as exc:  # noqa: BLE001
        logger.warning("RentCast comps fallback failed: %s", exc)
        return None


async def find_comparables(
    subject: PropertyRecord,
    state: str = "FL",
    radius_miles: float = 3.0,
    months: int = 12,
    max_comps: int = 5,
) -> CompAnalysis:
    """Find comparable sales near the subject and derive land value + ADV.

    Args:
        subject: The subject property record (needs lat/lng + county).
        state: Two-letter state code.
        radius_miles: Search radius in miles.
        months: Recency window — sales older than this are dropped.
        max_comps: Maximum comps to retain per set (land, unit).

    Returns:
        CompAnalysis with land comps, price range, and ADV-per-unit (when
        improved sales are available).
    """
    result = CompAnalysis()
    now = datetime.now(timezone.utc)

    if not subject.lat or not subject.lng or not subject.county:
        result.notes = ["Missing lat/lng or county — cannot search for comps"]
        return result

    # California parcels are larger and development is more spread out, and few CA
    # counties expose open sales layers — widen the net before giving up.
    if state.upper() in ("CA", "CALIFORNIA") and radius_miles <= 3.0:
        radius_miles = 5.0

    # Prefer a curated per-county source (one registry entry per market), then
    # fall back to generic ArcGIS Hub keyword discovery for unmapped counties.
    from plotlot.pipeline.comps_sources import resolve_sales_dataset

    sales_info = await resolve_sales_dataset(
        state, subject.county, subject.lat, subject.lng, radius_miles
    )
    if not sales_info:
        sales_info = await _discover_sales_dataset(subject.county, state)
    if not sales_info:
        # No open arms-length-sales layer (e.g. San Diego). Try a keyed comps API
        # (RentCast) before giving up to the regional default — gated on a key so
        # it never breaks when unconfigured, and only here so the free tier is
        # spent only where the free GIS path fails.
        rc = await _try_rentcast_comps(subject, radius_miles, months)
        if rc is not None:
            return rc
        result.notes = [f"No sales dataset found for {subject.county} County, {state}"]
        return result

    layer_url, fields = sales_info
    logger.info("Found sales dataset: %s (%d fields)", layer_url, len(fields))

    price_field = _find_field(fields, _PRICE_FIELDS)
    date_field = _find_field(fields, _DATE_FIELDS)
    addr_field = _find_field(fields, _ADDR_FIELDS)
    lot_field = _find_field(fields, _LOT_FIELDS)
    zone_field = _find_field(fields, _ZONE_FIELDS)
    units_field = _find_field(fields, _UNITS_FIELDS)
    bldg_area_field = _find_field(fields, _BLDG_AREA_FIELDS)
    year_field = _find_field(fields, _YEAR_FIELDS)
    imprv_field = _find_field(fields, _IMPRV_FIELDS)

    if not price_field:
        result.notes = ["Sales dataset found but no price field identified"]
        return result

    # Can we tell improved parcels from vacant land?
    has_improvement_signal = any((units_field, bldg_area_field, year_field, imprv_field))

    try:
        features = await _query_nearby_sales(
            layer_url, subject.lat, subject.lng, radius_miles, order_by=date_field
        )
    except Exception as e:
        logger.warning("Sales query failed: %s", e)
        result.notes = [f"Sales query failed: {e}"]
        return result

    logger.info("Found %d nearby sale features", len(features))

    land_comps: list[ComparableSale] = []
    unit_comps: list[ComparableSale] = []
    land_recent_flags: list[bool] = []

    for feat in features:
        attrs = feat.get("attributes", {})
        price = safe_float(attrs.get(price_field))
        if not _is_arms_length(price):
            continue

        sale_date = _parse_sale_date(attrs.get(date_field)) if date_field else ""
        if not _within_months(sale_date, months, now):
            continue

        latlng = _feature_latlng(feat.get("geometry", {}))
        distance = 0.0
        if latlng:
            distance = _haversine_miles(subject.lat, subject.lng, latlng[0], latlng[1])
            if distance > radius_miles:
                continue

        address = str(attrs.get(addr_field, "")) if addr_field else ""
        zoning = str(attrs.get(zone_field, "")) if zone_field else ""

        # Lot size
        lot_sqft = 0.0
        if lot_field:
            raw_lot = safe_float(attrs.get(lot_field))
            if lot_field.upper() in ("ACRES", "ACREAGE") and raw_lot > 0:
                lot_sqft = raw_lot * SQFT_PER_ACRE
            elif raw_lot > 0:
                lot_sqft = raw_lot

        is_improved, units = _classify_improved(
            attrs, units_field, bldg_area_field, year_field, imprv_field
        )

        if is_improved and has_improvement_signal:
            # Exit comp → ADV per unit (full finished-product sale price / units).
            ppu = price / units if units > 0 else price
            unit_comps.append(
                ComparableSale(
                    address=address,
                    sale_price=price,
                    sale_date=sale_date,
                    lot_size_sqft=lot_sqft,
                    zoning_code=zoning,
                    distance_miles=round(distance, 2),
                    price_per_unit=round(ppu, 2),
                )
            )
            continue

        # Land comp → price per acre. Restrict to vacant parcels when we can,
        # and to lots within ±30% of the subject for comparability.
        if subject.lot_size_sqft > 0 and lot_sqft > 0:
            ratio = lot_sqft / subject.lot_size_sqft
            if ratio < 0.7 or ratio > 1.3:
                continue

        acres = lot_sqft / SQFT_PER_ACRE if lot_sqft > 0 else 0
        ppa = price / acres if acres > 0 else 0
        land_comps.append(
            ComparableSale(
                address=address,
                sale_price=price,
                sale_date=sale_date,
                lot_size_sqft=lot_sqft,
                zoning_code=zoning,
                distance_miles=round(distance, 2),
                price_per_acre=round(ppa, 2),
            )
        )
        land_recent_flags.append(_within_months(sale_date, 6, now))

    # Sort by distance, keep the closest N of each set.
    land_comps.sort(key=lambda c: c.distance_miles)
    unit_comps.sort(key=lambda c: c.distance_miles)
    land_comps = land_comps[:max_comps]
    unit_comps = unit_comps[:max_comps]

    # --- Land value + price range ---
    ppa_values = [c.price_per_acre for c in land_comps if c.price_per_acre > 0]
    low_ppa, median_ppa, high_ppa = _price_range(ppa_values)
    result.median_price_per_acre = round(median_ppa, 2)
    result.price_per_acre_low = round(low_ppa, 2)
    result.price_per_acre_high = round(high_ppa, 2)

    if subject.lot_size_sqft > 0:
        subject_acres = subject.lot_size_sqft / SQFT_PER_ACRE
        result.estimated_land_value = round(subject_acres * median_ppa, 2)
        result.estimated_land_value_low = round(subject_acres * low_ppa, 2)
        result.estimated_land_value_high = round(subject_acres * high_ppa, 2)

    # --- ADV per unit from exit comps ---
    ppu_values = [c.price_per_unit for c in unit_comps if c.price_per_unit and c.price_per_unit > 0]
    if ppu_values:
        low_ppu, median_ppu, high_ppu = _price_range(ppu_values)
        result.adv_per_unit = round(median_ppu, 2)
        result.adv_per_unit_low = round(low_ppu, 2)
        result.adv_per_unit_high = round(high_ppu, 2)
        result.adv_source = "comps"

    result.comparables = land_comps
    result.unit_comparables = unit_comps

    # --- Confidence + notes ---
    fraction_recent = sum(land_recent_flags[:max_comps]) / len(land_comps) if land_comps else 0.0
    result.confidence = _score_confidence(len(land_comps), fraction_recent)

    if not land_comps and not unit_comps:
        result.notes.append(
            f"No qualifying comps within {radius_miles} mi over the last {months} mo "
            f"(checked {len(features)} sales)"
        )
    if not has_improvement_signal:
        result.notes.append(
            "Sales dataset lacks building fields — land/improved sales could not be "
            "separated; ADV per unit unavailable from comps"
        )
    elif not unit_comps:
        result.notes.append("No nearby improved sales found — ADV per unit unavailable from comps")

    return result
