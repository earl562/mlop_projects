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
from typing import Any, Literal, assert_never

import anyio
import httpx

from plotlot.core.types import CompAnalysis, ComparableSale, PropertyRecord
from plotlot.observability.tracing import start_otel_span
from plotlot.property.arcgis_utils import safe_float

logger = logging.getLogger(__name__)
COMPS_QUERY_MAX_ATTEMPTS = 3
COMPS_QUERY_BASE_DELAY_SECONDS = 1.0
COMPS_QUERY_TIMEOUT = httpx.Timeout(8.0, connect=4.0)

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
_CITY_FIELDS = {"TRUE_SITE_CITY", "SITE_CITY", "SITUS_CITY", "CITY", "MUNICIPALITY"}
_LOT_FIELDS = {
    "LOT_SIZE",
    "LOT_AREA",
    "LAND_SQFT",
    "ACRES",
    "ACREAGE",
    "SQ_FOOTAGE",
    "SHAPE.STAREA()",
    "SHAPE__AREA",
    "SHAPE_AREA",
}
_ZONE_FIELDS = {"ZONE_CODE", "ZONING", "ZONING_CODE", "ZONE", "ZONE_CLASS"}
_LAND_USE_FIELDS = {"DOR_CODE_CUR", "LAND_USE_CODE", "LAND_USE", "USE_CODE", "PROPERTY_TYPE"}
_IDENTIFIER_FIELDS = {"FOLIO", "FOLIO_NUMBER", "PARCEL_NUMBER", "PARCEL_ID"}
# Improvement signals — presence of any (> 0) marks a parcel as improved.
_UNITS_FIELDS = {
    "UNITS",
    "NO_UNITS",
    "LIVING_UNITS",
    "UNIT_COUNT",
    "NO_OF_UNITS",
    "RESIDENTIAL_UNITS",
    "BLDG_UNITS",
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


def _is_transient_comps_query_error(error: Exception) -> bool:
    match error:
        case httpx.TimeoutException():
            return True
        case httpx.NetworkError():
            return True
        case httpx.HTTPStatusError() as status_error:
            return (
                status_error.response.status_code == 429 or status_error.response.status_code >= 500
            )
        case _:
            return False


# Conversion constants
SQFT_PER_ACRE = 43_560
MILES_PER_DEGREE = 69.0  # approximate at mid-latitudes
_DAYS_PER_MONTH = 30.44
type ComparabilityStatus = Literal["match", "mismatch", "unknown"]
BROWARD_PROPERTY_INFO_QUERY_URL = (
    "https://gisweb-adapters.bcpa.net/arcgis/rest/services/BCPA_EXTERNAL_JAN26/MapServer/36/query"
)
BROWARD_COMP_ENRICH_FIELDS = (
    "FOLIO_NUMBER",
    "SITUS_STREET_NUMBER",
    "SITUS_STREET_DIRECTION",
    "SITUS_STREET_NAME",
    "SITUS_STREET_TYPE",
    "SITUS_STREET_POST_DIR",
    "SITUS_UNIT_NUMBER",
    "BLDG_UNITS",
    "BLDG_ADJ_SQ_FOOTAGE",
    "UNDER_AIR_SQFT",
    "BLDG_YEAR_BUILT",
    "JUST_BUILDING_VALUE",
)
MIAMI_DADE_COMP_ENRICH_FIELDS = (
    "FOLIO",
    "TRUE_SITE_ADDR",
    "TRUE_SITE_CITY",
    "DOR_CODE_CUR",
    "DOR_DESC",
    "LOT_SIZE",
)


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


def _allows_single_unit_exit_comp(subject: PropertyRecord) -> bool:
    zoning = (subject.zoning_code or "").upper().replace(" ", "")
    low_density_prefixes = ("RS", "R-1", "R1", "RE", "RH", "SF", "SFR")
    if subject.living_units == 1:
        return True
    return any(zoning.startswith(prefix) for prefix in low_density_prefixes)


def _is_vacant_single_family_subject(subject: PropertyRecord) -> bool:
    zoning = (subject.zoning_code or "").upper().replace(" ", "")
    land_text = f"{subject.land_use_code} {subject.land_use_description}".upper()
    is_low_density = any(
        zoning.startswith(prefix) for prefix in ("RS", "R-1", "R1", "RE", "RH", "SF", "SFR")
    )
    is_vacant = "VACANT" in land_text
    return is_low_density and is_vacant


def _filter_vacant_single_family_unit_comps(
    subject: PropertyRecord,
    unit_comps: list[ComparableSale],
) -> list[ComparableSale]:
    selected, _selection_note = _select_vacant_single_family_unit_comps(subject, unit_comps)
    return selected


def _select_vacant_single_family_unit_comps(
    subject: PropertyRecord,
    unit_comps: list[ComparableSale],
) -> tuple[list[ComparableSale], str | None]:
    if not _is_vacant_single_family_subject(subject):
        return unit_comps, None

    filtered = [
        comp for comp in unit_comps if comp.lot_size_sqft > 0 and (comp.price_per_unit or 0.0) > 0
    ]
    if not filtered:
        return [], None

    median = _percentile(
        sorted(comp.price_per_unit for comp in filtered if comp.price_per_unit is not None),
        50,
    )
    if median > 0:
        lower_bound = median * 0.5
        upper_bound = median * 2.0
        bounded = [
            comp
            for comp in filtered
            if comp.price_per_unit is not None and lower_bound <= comp.price_per_unit <= upper_bound
        ]
        if bounded:
            filtered = bounded
    lot_size_filtered = _filter_unit_comps_by_subject_lot_size(subject, filtered)
    local_cluster = _prioritize_local_unit_comp_cluster(lot_size_filtered)
    prioritized = _prioritize_recent_new_build_unit_comps(subject, filtered)
    if prioritized:
        if _prefer_local_unit_cluster_over_recent_new_builds(
            recent_new_builds=prioritized,
            local_cluster=local_cluster,
        ):
            return (
                local_cluster,
                "Recent new-build sales appear to come from a higher-priced nearby micro-market; using closer improved sales for exit pricing.",
            )
        return prioritized, None
    if local_cluster:
        return local_cluster, None
    if len(lot_size_filtered) >= 2:
        return lot_size_filtered, None
    return filtered, None


def _filter_vacant_single_family_land_comps(
    subject: PropertyRecord,
    land_comps: list[ComparableSale],
    unit_comps: list[ComparableSale],
) -> tuple[list[ComparableSale], list[ComparableSale]]:
    if not _is_vacant_single_family_subject(subject):
        return land_comps, []

    unit_price_values = sorted(
        comp.price_per_unit
        for comp in unit_comps
        if comp.price_per_unit is not None and comp.price_per_unit > 0
    )
    if not unit_price_values:
        return land_comps, []

    median_unit_price = _percentile(unit_price_values, 50)
    max_land_sale_price = median_unit_price * 0.65
    filtered = [comp for comp in land_comps if comp.sale_price <= max_land_sale_price]
    rejected = [comp for comp in land_comps if comp.sale_price > max_land_sale_price]
    prioritized = _prioritize_local_land_comp_cluster(filtered)
    if prioritized:
        return prioritized, rejected
    return filtered, rejected


def _prioritize_recent_new_build_unit_comps(
    subject: PropertyRecord,
    unit_comps: list[ComparableSale],
) -> list[ComparableSale]:
    recent_builds = [
        comp for comp in unit_comps if _is_recent_new_build_year(comp.adjustments.get("year_built"))
    ]
    similar_recent_builds = _filter_unit_comps_by_subject_lot_size(subject, recent_builds)
    if len(similar_recent_builds) >= 2:
        return similar_recent_builds
    return []


def _count_recent_new_build_unit_comps(unit_comps: list[ComparableSale]) -> int:
    return sum(
        1 for comp in unit_comps if _is_recent_new_build_year(comp.adjustments.get("year_built"))
    )


def _filter_unit_comps_by_subject_lot_size(
    subject: PropertyRecord,
    unit_comps: list[ComparableSale],
) -> list[ComparableSale]:
    if subject.lot_size_sqft <= 0:
        return unit_comps
    filtered: list[ComparableSale] = []
    for comp in unit_comps:
        if comp.lot_size_sqft <= 0:
            continue
        ratio = comp.lot_size_sqft / subject.lot_size_sqft
        if 0.25 <= ratio <= 1.6:
            filtered.append(comp)
    return filtered


def _prioritize_local_unit_comp_cluster(
    unit_comps: list[ComparableSale],
) -> list[ComparableSale]:
    nearby = [comp for comp in unit_comps if comp.distance_miles <= 0.75]
    if len(nearby) >= 2:
        return nearby
    return []


def _prefer_local_unit_cluster_over_recent_new_builds(
    *,
    recent_new_builds: list[ComparableSale],
    local_cluster: list[ComparableSale],
) -> bool:
    if len(recent_new_builds) < 2 or len(local_cluster) < 2:
        return False

    recent_prices = sorted(
        comp.price_per_unit for comp in recent_new_builds if comp.price_per_unit is not None
    )
    local_prices = sorted(
        comp.price_per_unit for comp in local_cluster if comp.price_per_unit is not None
    )
    if len(recent_prices) < 2 or len(local_prices) < 2:
        return False

    recent_median = _percentile(recent_prices, 50)
    local_median = _percentile(local_prices, 50)
    if local_median <= 0:
        return False

    far_recent_builds = all(comp.distance_miles >= 1.0 for comp in recent_new_builds)
    premium_gap = recent_median >= local_median * 1.2
    return far_recent_builds and premium_gap


def _prioritize_local_land_comp_cluster(
    land_comps: list[ComparableSale],
) -> list[ComparableSale]:
    nearby = [comp for comp in land_comps if comp.distance_miles <= 0.75]
    if len(nearby) >= 2:
        return nearby
    return []


def _is_recent_new_build_year(value: float | None) -> bool:
    if not isinstance(value, int | float) or value <= 0:
        return False
    current_year = datetime.now(timezone.utc).year
    return int(value) >= current_year - 1


def _polygon_area_sqft(geom: dict[str, Any]) -> float:
    rings = geom.get("rings")
    if not isinstance(rings, list) or not rings:
        return 0.0
    outer_ring = rings[0]
    if not isinstance(outer_ring, list) or len(outer_ring) < 3:
        return 0.0

    latitudes = [point[1] for point in outer_ring if isinstance(point, list) and len(point) >= 2]
    if not latitudes:
        return 0.0
    avg_lat_rad = math.radians(sum(latitudes) / len(latitudes))
    feet_per_degree_lat = 364000.0
    feet_per_degree_lng = feet_per_degree_lat * math.cos(avg_lat_rad)

    projected: list[tuple[float, float]] = []
    for point in outer_ring:
        if not isinstance(point, list) or len(point) < 2:
            continue
        lng, lat = point[0], point[1]
        projected.append((float(lng) * feet_per_degree_lng, float(lat) * feet_per_degree_lat))
    if len(projected) < 3:
        return 0.0

    area = 0.0
    for index, (x1, y1) in enumerate(projected):
        x2, y2 = projected[(index + 1) % len(projected)]
        area += (x1 * y2) - (x2 * y1)
    return abs(area) / 2.0


def _is_broward_subject(subject: PropertyRecord) -> bool:
    return (subject.county or "").strip().casefold() == "broward"


def _is_miami_dade_subject(subject: PropertyRecord) -> bool:
    county = (subject.county or "").strip().casefold()
    return county in {"miami-dade", "miami dade"}


def _extend_miami_dade_sales_fields(fields: list[str]) -> list[str]:
    extended = list(fields)
    for field in MIAMI_DADE_COMP_ENRICH_FIELDS:
        if field not in extended:
            extended.append(field)
    return extended


def _extend_broward_sales_fields(fields: list[str]) -> list[str]:
    extended = list(fields)
    for field in ("ADDRESS", *BROWARD_COMP_ENRICH_FIELDS):
        if field not in extended:
            extended.append(field)
    return extended


def _broward_comp_folio(attrs: dict[str, Any]) -> str:
    return str(
        attrs.get("SQLGIS02.dbo.BCPA_SALES.FOLIO_NUMBER")
        or attrs.get("SQLGIS02.DATALAYER.Parcel_Polygons.FOLIO")
        or attrs.get("FOLIO_NUMBER")
        or attrs.get("FOLIO")
        or ""
    ).strip()


def _format_broward_address(attrs: dict[str, Any]) -> str:
    parts = [
        str(attrs.get("SITUS_STREET_NUMBER") or "").strip(),
        str(attrs.get("SITUS_STREET_DIRECTION") or "").strip(),
        str(attrs.get("SITUS_STREET_NAME") or "").strip(),
        str(attrs.get("SITUS_STREET_TYPE") or "").strip(),
        str(attrs.get("SITUS_STREET_POST_DIR") or "").strip(),
        str(attrs.get("SITUS_UNIT_NUMBER") or "").strip(),
    ]
    return " ".join(part for part in parts if part)


async def _enrich_broward_sales_features(
    features: list[dict[str, Any]],
    timeout: float = 20.0,
) -> list[dict[str, Any]]:
    folios = sorted(
        {
            _broward_comp_folio(feature.get("attributes", {}))
            for feature in features
            if _broward_comp_folio(feature.get("attributes", {}))
        }
    )
    if not folios:
        return features
    rows: list[dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            for start in range(0, len(folios), 40):
                batch = folios[start : start + 40]
                where = "FOLIO_NUMBER IN ({})".format(", ".join(f"'{folio}'" for folio in batch))
                params = {
                    "where": where,
                    "outFields": ",".join(BROWARD_COMP_ENRICH_FIELDS),
                    "returnGeometry": "false",
                    "f": "json",
                }
                response = await client.get(BROWARD_PROPERTY_INFO_QUERY_URL, params=params)
                response.raise_for_status()
                data = response.json()
                batch_rows = data.get("features", [])
                if isinstance(batch_rows, list):
                    rows.extend(batch_rows)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Broward sales enrichment failed: %s", exc)
        return features
    if not rows:
        return features
    by_folio: dict[str, dict[str, Any]] = {}
    for row in rows:
        attrs = row.get("attributes", {})
        if not isinstance(attrs, dict):
            continue
        folio = str(attrs.get("FOLIO_NUMBER") or "").strip()
        if not folio:
            continue
        enriched = dict(attrs)
        address = _format_broward_address(attrs)
        if address:
            enriched["ADDRESS"] = address
        by_folio[folio] = enriched
    if not by_folio:
        return features
    enriched_features: list[dict[str, Any]] = []
    for feature in features:
        attrs = feature.get("attributes", {})
        if not isinstance(attrs, dict):
            enriched_features.append(feature)
            continue
        folio = _broward_comp_folio(attrs)
        if not folio or folio not in by_folio:
            enriched_features.append(feature)
            continue
        merged = dict(feature)
        merged["attributes"] = {**attrs, **by_folio[folio]}
        enriched_features.append(merged)
    return enriched_features


def _clean_comp_address(value: object) -> str:
    return " ".join(str(value or "").split()).strip()


def _looks_like_identifier(value: str) -> bool:
    stripped = value.strip()
    if not stripped:
        return False
    return stripped.replace("-", "").isdigit()


def _resolved_comp_address(
    attrs: dict[str, Any],
    *,
    addr_field: str | None,
    identifier_field: str | None,
) -> str:
    candidates: list[str] = []
    if addr_field:
        candidates.append(_clean_comp_address(attrs.get(addr_field, "")))
    for key in ("TRUE_SITE_ADDR", "ADDRESS", "SITE_ADDR", "SITUS_ADDR", "PROP_ADDR", "SITEADDR"):
        candidates.append(_clean_comp_address(attrs.get(key, "")))

    for candidate in candidates:
        if candidate and not _looks_like_identifier(candidate):
            return candidate

    if identifier_field:
        identifier_candidate = _clean_comp_address(attrs.get(identifier_field, ""))
        if identifier_candidate:
            return identifier_candidate
    return ""


def _address_sort_penalty(address: str) -> int:
    return 1 if _looks_like_identifier(address) else 0


def _apply_identifier_address_penalty(score: float, address: str) -> float:
    if not _looks_like_identifier(address):
        return score
    return round(max(score - 0.03, 0.0), 3)


def _miami_dade_comp_folio(attrs: dict[str, Any]) -> str:
    return str(attrs.get("FOLIO") or "").strip()


async def _enrich_miami_dade_sales_features(
    features: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    from plotlot.retrieval.property import MDC_PROPERTY_URL, _query_arcgis

    folios = sorted(
        {
            _miami_dade_comp_folio(feature.get("attributes", {}))
            for feature in features
            if _miami_dade_comp_folio(feature.get("attributes", {}))
        }
    )
    if not folios:
        return features

    rows: list[dict[str, Any]] = []
    try:
        for start in range(0, len(folios), 40):
            batch = folios[start : start + 40]
            where = "FOLIO IN ({})".format(", ".join(f"'{folio}'" for folio in batch))
            rows.extend(
                await _query_arcgis(
                    MDC_PROPERTY_URL,
                    where=where,
                    out_fields=",".join(MIAMI_DADE_COMP_ENRICH_FIELDS),
                    extra_params={"outSR": "4326", "returnGeometry": "false"},
                    limit=None,
                )
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Miami-Dade sales enrichment failed: %s", exc)
        return features

    by_folio: dict[str, dict[str, Any]] = {}
    for row in rows:
        attrs = row.get("attributes", {})
        if not isinstance(attrs, dict):
            continue
        folio = _miami_dade_comp_folio(attrs)
        if not folio:
            continue
        enriched = dict(attrs)
        if "TRUE_SITE_ADDR" in enriched and enriched["TRUE_SITE_ADDR"]:
            enriched.setdefault("ADDRESS", enriched["TRUE_SITE_ADDR"])
        if "TRUE_SITE_CITY" in enriched and enriched["TRUE_SITE_CITY"]:
            enriched.setdefault("CITY", enriched["TRUE_SITE_CITY"])
        if "DOR_CODE_CUR" in enriched and enriched["DOR_CODE_CUR"]:
            enriched.setdefault("LAND_USE_CODE", enriched["DOR_CODE_CUR"])
        by_folio[folio] = enriched
    if not by_folio:
        return features

    enriched_features: list[dict[str, Any]] = []
    for feature in features:
        attrs = feature.get("attributes", {})
        if not isinstance(attrs, dict):
            enriched_features.append(feature)
            continue
        folio = _miami_dade_comp_folio(attrs)
        if not folio or folio not in by_folio:
            enriched_features.append(feature)
            continue
        merged = dict(feature)
        merged["attributes"] = {**attrs, **by_folio[folio]}
        enriched_features.append(merged)
    return enriched_features


def _comparability_status(subject_value: str, comp_value: str) -> ComparabilityStatus:
    subject = " ".join(subject_value.strip().casefold().split())
    comp = " ".join(comp_value.strip().casefold().split())
    if not subject or not comp:
        return "unknown"
    return "match" if subject == comp else "mismatch"


def _zoning_comparability_status(subject_zoning: str, comp_zoning: str) -> ComparabilityStatus:
    return _comparability_status(subject_zoning, comp_zoning)


def _municipality_comparability_status(
    subject_municipality: str,
    comp_municipality: str,
) -> ComparabilityStatus:
    return _comparability_status(subject_municipality, comp_municipality)


def _zoning_is_comparable(subject_zoning: str, comp_zoning: str) -> bool:
    return _zoning_comparability_status(subject_zoning, comp_zoning) == "match"


def _municipality_is_comparable(subject_municipality: str, comp_municipality: str) -> bool:
    return _municipality_comparability_status(subject_municipality, comp_municipality) == "match"


def _comparability_score(
    status: ComparabilityStatus,
    *,
    mismatch_score: float,
    unknown_score: float,
) -> float:
    match status:
        case "match":
            return 1.0
        case "mismatch":
            return mismatch_score
        case "unknown":
            return unknown_score
        case unreachable:
            assert_never(unreachable)


def _comp_adjustments(
    *,
    zoning_status: ComparabilityStatus,
    lot_size_matches: bool,
    municipality_status: ComparabilityStatus,
    year_built: float | None = None,
) -> dict[str, float]:
    adjustments: dict[str, float] = {}
    match zoning_status:
        case "mismatch":
            adjustments["zoning_mismatch"] = 1.0
        case "unknown":
            adjustments["zoning_unknown"] = 1.0
        case "match":
            pass
        case unreachable:
            assert_never(unreachable)
    if not lot_size_matches:
        adjustments["lot_size_outside_band"] = 1.0
    match municipality_status:
        case "mismatch":
            adjustments["municipality_mismatch"] = 1.0
        case "unknown":
            adjustments["municipality_unknown"] = 1.0
        case "match":
            pass
        case unreachable:
            assert_never(unreachable)
    if isinstance(year_built, int | float) and year_built > 0:
        adjustments["year_built"] = float(year_built)
    return adjustments


def _distance_qualification_score(distance_miles: float) -> float:
    if distance_miles <= 0.75:
        return 1.0
    if distance_miles <= 1.5:
        return 0.9
    if distance_miles <= 3.0:
        return 0.75
    if distance_miles <= 5.0:
        return 0.6
    return 0.45


def _recency_qualification_score(sale_date: str, now: datetime) -> float:
    if _within_months(sale_date, 6, now):
        return 1.0
    if _within_months(sale_date, 12, now):
        return 0.85
    if _within_months(sale_date, 24, now):
        return 0.7
    return 0.5


def _lot_size_similarity_score(subject_lot_sqft: float, comp_lot_sqft: float) -> float:
    if subject_lot_sqft <= 0 or comp_lot_sqft <= 0:
        return 0.5
    ratio = comp_lot_sqft / subject_lot_sqft
    if 0.85 <= ratio <= 1.15:
        return 1.0
    if 0.7 <= ratio <= 1.3:
        return 0.85
    if 0.5 <= ratio <= 1.6:
        return 0.65
    return 0.35


def _land_comp_qualification_score(
    *,
    subject_lot_sqft: float,
    comp_lot_sqft: float,
    zoning_status: ComparabilityStatus,
    municipality_status: ComparabilityStatus,
    distance_miles: float,
    sale_date: str,
    now: datetime,
) -> float:
    zoning_score = _comparability_score(
        zoning_status,
        mismatch_score=0.35,
        unknown_score=0.1,
    )
    municipality_score = _comparability_score(
        municipality_status,
        mismatch_score=0.45,
        unknown_score=0.1,
    )
    lot_score = _lot_size_similarity_score(subject_lot_sqft, comp_lot_sqft)
    distance_score = _distance_qualification_score(distance_miles)
    recency_score = _recency_qualification_score(sale_date, now)
    score = (
        (zoning_score * 0.3)
        + (municipality_score * 0.2)
        + (lot_score * 0.2)
        + (distance_score * 0.15)
        + (recency_score * 0.15)
    )
    if zoning_status == "unknown" or municipality_status == "unknown":
        score = min(score, 0.65)
    return round(score, 3)


def _unit_comp_qualification_score(
    *,
    subject_lot_sqft: float,
    comp_lot_sqft: float,
    municipality_status: ComparabilityStatus,
    distance_miles: float,
    sale_date: str,
    now: datetime,
) -> float:
    municipality_score = _comparability_score(
        municipality_status,
        mismatch_score=0.45,
        unknown_score=0.1,
    )
    lot_score = _lot_size_similarity_score(subject_lot_sqft, comp_lot_sqft)
    distance_score = _distance_qualification_score(distance_miles)
    recency_score = _recency_qualification_score(sale_date, now)
    score = (
        (municipality_score * 0.3)
        + (lot_score * 0.25)
        + (distance_score * 0.25)
        + (recency_score * 0.2)
    )
    if municipality_status == "unknown":
        score = min(score, 0.65)
    return round(score, 3)


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
    where: str = "1=1",
    timeout: httpx.Timeout | float = COMPS_QUERY_TIMEOUT,
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

    page_size = min(limit, 250)
    base_params = {
        "where": where,
        "geometry": str(envelope).replace("'", '"'),
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "outSR": "4326",
        "returnGeometry": "true",
        "f": "json",
    }
    if order_by:
        base_params["orderByFields"] = f"{order_by} DESC"

    features: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=timeout) as client:
        query_url = layer_url if layer_url.endswith("/query") else f"{layer_url}/query"
        with start_otel_span(
            "comps.query_nearby_sales",
            {
                "plotlot.layer_url": query_url,
                "plotlot.radius_miles": radius_miles,
                "plotlot.limit": limit,
                "plotlot.page_size": page_size,
            },
        ) as span:
            for offset in range(0, limit, page_size):
                params = {
                    **base_params,
                    "resultRecordCount": str(min(page_size, limit - offset)),
                    "resultOffset": str(offset),
                }
                for attempt in range(1, COMPS_QUERY_MAX_ATTEMPTS + 1):
                    try:
                        resp = await client.get(query_url, params=params)
                        resp.raise_for_status()
                        data = resp.json()
                        batch = data.get("features", [])
                        if not isinstance(batch, list) or not batch:
                            if span:
                                span.set_attribute("plotlot.last_offset", offset)
                                span.set_attribute("plotlot.total_features", len(features))
                            return features
                        features.extend(batch)
                        if span:
                            span.set_attribute("plotlot.last_offset", offset)
                            span.set_attribute("plotlot.total_features", len(features))
                        if len(batch) < page_size:
                            return features
                        break
                    except Exception as exc:
                        if (
                            _is_transient_comps_query_error(exc)
                            and attempt < COMPS_QUERY_MAX_ATTEMPTS
                        ):
                            delay = COMPS_QUERY_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
                            logger.warning(
                                "Transient comps query failure for %s offset=%d (attempt %d/%d): %s; retrying in %.1fs",
                                query_url,
                                offset,
                                attempt,
                                COMPS_QUERY_MAX_ATTEMPTS,
                                exc,
                                delay,
                            )
                            await anyio.sleep(delay)
                            continue
                        if span:
                            span.set_attribute("plotlot.last_offset", offset)
                            span.set_attribute("plotlot.failed_attempt", attempt)
                        raise

    return features


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _sales_query_limit(
    *,
    vacant_single_family_subject: bool,
    months: int,
    radius_miles: float,
) -> int:
    if not vacant_single_family_subject:
        return 800
    if months >= 24 and radius_miles > 3.0:
        return 400
    if months >= 24:
        return 800
    return 800


def _score_confidence(land_count: int, fraction_recent_6mo: float) -> float:
    """Confidence from land-comp count and recency (see comping methodology)."""
    if land_count >= 5:
        return 0.9 if fraction_recent_6mo >= 0.5 else 0.8
    if land_count >= 3:
        return 0.75
    if land_count >= 1:
        return 0.5
    return 0.0


def _vacant_land_sales_where_clause(
    *,
    subject: PropertyRecord,
    land_use_field: str | None,
) -> str | None:
    if not _is_vacant_single_family_subject(subject):
        return None
    if land_use_field is None:
        return None
    raw_subject_code = str(subject.land_use_code or "").strip()
    vacant_codes = {"0081"}
    if raw_subject_code:
        vacant_codes.add(raw_subject_code)
    if "MIAMI-DADE" in str(subject.county or "").upper():
        vacant_codes.add("0066")
    quoted_codes = ", ".join(f"'{code}'" for code in sorted(vacant_codes))
    return f"{land_use_field} IN ({quoted_codes})"


def _select_strong_relaxed_vacant_land_comps(
    relaxed_land_comps: list[ComparableSale],
) -> list[ComparableSale]:
    strong_comps = [
        comp
        for comp in relaxed_land_comps
        if float(comp.adjustments.get("qualification_score", 0.0)) >= 0.55
    ]
    nearby_strong_comps = [comp for comp in strong_comps if comp.distance_miles <= 3.5]
    if len(nearby_strong_comps) >= 2:
        return nearby_strong_comps
    if len(strong_comps) >= 2:
        return strong_comps
    return []


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
    from plotlot.pipeline.comps_sources import get_sales_source, resolve_sales_dataset

    curated_sales_source = get_sales_source(state, subject.county)
    sales_info = await resolve_sales_dataset(
        state, subject.county, subject.lat, subject.lng, radius_miles
    )
    if sales_info and curated_sales_source is not None:
        result.sales_source_type = "curated_arcgis"
    if not sales_info:
        sales_info = await _discover_sales_dataset(subject.county, state)
        if sales_info:
            result.sales_source_type = "discovered_arcgis"
    if not sales_info:
        result.notes = [
            f"No sales dataset found for {subject.county} County, {state}",
            "Open-data-only comps path: use county/ArcGIS sales data or public listing evidence.",
        ]
        return result

    layer_url, fields = sales_info
    if _is_miami_dade_subject(subject):
        fields = _extend_miami_dade_sales_fields(fields)
    if _is_broward_subject(subject):
        fields = _extend_broward_sales_fields(fields)
    logger.info("Found sales dataset: %s (%d fields)", layer_url, len(fields))

    price_field = _find_field(fields, _PRICE_FIELDS)
    date_field = _find_field(fields, _DATE_FIELDS)
    addr_field = _find_field(fields, _ADDR_FIELDS)
    city_field = _find_field(fields, _CITY_FIELDS)
    identifier_field = _find_field(fields, _IDENTIFIER_FIELDS)
    lot_field = _find_field(fields, _LOT_FIELDS)
    zone_field = _find_field(fields, _ZONE_FIELDS)
    land_use_field = _find_field(fields, _LAND_USE_FIELDS)
    units_field = _find_field(fields, _UNITS_FIELDS)
    bldg_area_field = _find_field(fields, _BLDG_AREA_FIELDS)
    year_field = _find_field(fields, _YEAR_FIELDS)
    imprv_field = _find_field(fields, _IMPRV_FIELDS)

    if not price_field:
        result.notes = ["Sales dataset found but no price field identified"]
        return result

    # Can we tell improved parcels from vacant land?
    has_improvement_signal = any((units_field, bldg_area_field, year_field, imprv_field))

    vacant_single_family_subject = _is_vacant_single_family_subject(subject)

    try:
        query_limit = _sales_query_limit(
            vacant_single_family_subject=vacant_single_family_subject,
            months=months,
            radius_miles=radius_miles,
        )
        vacant_land_where = None
        if vacant_single_family_subject and months >= 24 and radius_miles > 3.0:
            vacant_land_where = _vacant_land_sales_where_clause(
                subject=subject,
                land_use_field=land_use_field,
            )
        features = await _query_nearby_sales(
            layer_url,
            subject.lat,
            subject.lng,
            radius_miles,
            limit=query_limit,
            order_by=date_field,
            where=vacant_land_where or "1=1",
        )
        if _is_miami_dade_subject(subject):
            features = await _enrich_miami_dade_sales_features(features)
        if _is_broward_subject(subject):
            features = await _enrich_broward_sales_features(features)
    except Exception as e:
        logger.warning("Sales query failed: %s", e)
        result.notes = [f"Sales query failed: {e}"]
        return result

    logger.info("Found %d nearby sale features", len(features))

    land_comps: list[ComparableSale] = []
    unit_comps: list[ComparableSale] = []
    land_recent_flags: list[bool] = []
    relaxed_land_comps: list[ComparableSale] = []
    relaxed_unit_comps: list[ComparableSale] = []
    relaxed_land_recent_flags: list[bool] = []

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

        address = _resolved_comp_address(
            attrs,
            addr_field=addr_field,
            identifier_field=identifier_field,
        )
        comp_municipality = _clean_comp_address(attrs.get(city_field, "")) if city_field else ""
        zoning = str(attrs.get(zone_field, "")) if zone_field else ""
        if not address:
            continue
        zoning_status = _zoning_comparability_status(subject.zoning_code, zoning)
        municipality_status = _municipality_comparability_status(
            subject.municipality,
            comp_municipality,
        )
        zoning_matches = zoning_status == "match"
        municipality_matches = municipality_status == "match"

        # Lot size
        lot_sqft = 0.0
        if lot_field:
            raw_lot = safe_float(attrs.get(lot_field))
            if lot_field.upper() in ("ACRES", "ACREAGE") and raw_lot > 0:
                lot_sqft = raw_lot * SQFT_PER_ACRE
            elif raw_lot > 0:
                lot_sqft = raw_lot
        if lot_sqft <= 0:
            lot_sqft = _polygon_area_sqft(feat.get("geometry", {}))

        is_improved, units = _classify_improved(
            attrs, units_field, bldg_area_field, year_field, imprv_field
        )
        year_built_value = safe_float(attrs.get(year_field)) if year_field else 0.0

        if is_improved and has_improvement_signal:
            if units <= 1 and not _allows_single_unit_exit_comp(subject):
                continue
            # Exit comp → ADV per unit (full finished-product sale price / units).
            ppu = price / units if units > 0 else price
            unit_comp = ComparableSale(
                address=address,
                sale_price=price,
                sale_date=sale_date,
                lot_size_sqft=lot_sqft,
                zoning_code=zoning,
                distance_miles=round(distance, 2),
                price_per_unit=round(ppu, 2),
                adjustments=_comp_adjustments(
                    zoning_status=zoning_status,
                    lot_size_matches=True,
                    municipality_status=municipality_status,
                    year_built=year_built_value,
                ),
            )
            unit_comp.adjustments["qualification_score"] = _unit_comp_qualification_score(
                subject_lot_sqft=subject.lot_size_sqft,
                comp_lot_sqft=lot_sqft,
                municipality_status=municipality_status,
                distance_miles=distance,
                sale_date=sale_date,
                now=now,
            )
            unit_comp.adjustments["qualification_score"] = _apply_identifier_address_penalty(
                float(unit_comp.adjustments["qualification_score"]),
                address,
            )
            if _looks_like_identifier(address):
                unit_comp.adjustments["identifier_only_address"] = 1.0
            if zoning_matches and municipality_matches:
                unit_comps.append(unit_comp)
            else:
                relaxed_unit_comps.append(unit_comp)
            continue

        # Land comp → price per acre. Restrict to vacant parcels when we can,
        # and to lots within ±30% of the subject for comparability.
        lot_size_matches = True
        if subject.lot_size_sqft > 0 and lot_sqft > 0:
            ratio = lot_sqft / subject.lot_size_sqft
            if ratio < 0.7 or ratio > 1.3:
                lot_size_matches = False

        acres = lot_sqft / SQFT_PER_ACRE if lot_sqft > 0 else 0
        ppa = price / acres if acres > 0 else 0
        land_adjustments = _comp_adjustments(
            zoning_status=zoning_status,
            lot_size_matches=lot_size_matches,
            municipality_status=municipality_status,
        )
        land_adjustments["qualification_score"] = _land_comp_qualification_score(
            subject_lot_sqft=subject.lot_size_sqft,
            comp_lot_sqft=lot_sqft,
            zoning_status=zoning_status,
            municipality_status=municipality_status,
            distance_miles=distance,
            sale_date=sale_date,
            now=now,
        )
        land_adjustments["qualification_score"] = _apply_identifier_address_penalty(
            float(land_adjustments["qualification_score"]),
            address,
        )
        if _looks_like_identifier(address):
            land_adjustments["identifier_only_address"] = 1.0
        land_comp = ComparableSale(
            address=address,
            sale_price=price,
            sale_date=sale_date,
            lot_size_sqft=lot_sqft,
            zoning_code=zoning,
            distance_miles=round(distance, 2),
            price_per_acre=round(ppa, 2),
            adjustments=land_adjustments,
        )
        is_recent = _within_months(sale_date, 6, now)
        if zoning_matches and lot_size_matches and municipality_matches:
            land_comps.append(land_comp)
            land_recent_flags.append(is_recent)
        else:
            relaxed_land_comps.append(land_comp)
            relaxed_land_recent_flags.append(is_recent)

    # Sort by distance, keep the closest N of each set.
    land_comps.sort(
        key=lambda c: (
            -float(c.adjustments.get("qualification_score", 0.0)),
            _address_sort_penalty(c.address),
            c.distance_miles,
        )
    )
    unit_comps.sort(key=lambda c: c.distance_miles)
    relaxed_land_comps.sort(
        key=lambda c: (
            -float(c.adjustments.get("qualification_score", 0.0)),
            _address_sort_penalty(c.address),
            c.distance_miles,
        )
    )
    relaxed_unit_comps.sort(key=lambda c: c.distance_miles)
    used_relaxed_land = False
    used_relaxed_unit = False
    if not land_comps and relaxed_land_comps:
        if vacant_single_family_subject:
            promoted_land_comps = _select_strong_relaxed_vacant_land_comps(relaxed_land_comps)
            if promoted_land_comps:
                land_comps = promoted_land_comps[:max_comps]
                promoted_ids = {id(comp) for comp in land_comps}
                land_recent_flags = [
                    is_recent
                    for comp, is_recent in zip(
                        relaxed_land_comps, relaxed_land_recent_flags, strict=False
                    )
                    if id(comp) in promoted_ids
                ]
                used_relaxed_land = True
            else:
                result.notes.append(
                    "No reliable vacant-land comps within 24 months; using nearby improved single-family sales for exit pricing only."
                )
        else:
            land_comps = relaxed_land_comps[:max_comps]
            land_recent_flags = relaxed_land_recent_flags[: len(land_comps)]
            used_relaxed_land = True
    if not unit_comps and relaxed_unit_comps:
        unit_comps = relaxed_unit_comps[:max_comps]
        used_relaxed_unit = True
    land_comps = land_comps[:max_comps]
    unit_comps, unit_selection_note = _select_vacant_single_family_unit_comps(
        subject,
        unit_comps[:max_comps],
    )
    if unit_selection_note is not None:
        result.notes.append(unit_selection_note)
    if vacant_single_family_subject and unit_comps:
        recent_new_build_count = _count_recent_new_build_unit_comps(unit_comps)
        if recent_new_build_count == 0:
            result.notes.append(
                "No recent same-market new-build sales were available; using renovated or older improved sales for exit pricing."
            )
        elif recent_new_build_count == 1 and len(unit_comps) > 1:
            result.notes.append(
                "Only one recent same-market new-build sale was available; blending older improved sales for exit pricing."
            )
    filtered_land_comps, rejected_land_comps = _filter_vacant_single_family_land_comps(
        subject,
        land_comps,
        unit_comps,
    )
    if rejected_land_comps:
        result.notes.append(
            "Removed outlier vacant-land comps whose sale prices exceeded the nearby finished-home pricing band: "
            + ", ".join(comp.address for comp in rejected_land_comps)
            + "."
        )
    land_comps = filtered_land_comps

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
        result.exit_comp_source_type = result.sales_source_type

    result.comparables = land_comps
    result.unit_comparables = unit_comps
    result.rejected_land_comparables = rejected_land_comps
    result.used_relaxed_land_comps = used_relaxed_land
    result.used_relaxed_unit_comps = used_relaxed_unit

    # --- Confidence + notes ---
    fraction_recent = sum(land_recent_flags[:max_comps]) / len(land_comps) if land_comps else 0.0
    result.confidence = _score_confidence(len(land_comps), fraction_recent)
    if (
        vacant_single_family_subject
        and not land_comps
        and len(unit_comps) >= 2
        and result.adv_per_unit is not None
        and result.adv_per_unit > 0
    ):
        result.confidence = 0.55
    if used_relaxed_land or used_relaxed_unit:
        result.confidence = min(result.confidence, 0.45)

    if not land_comps and not unit_comps:
        result.notes.append(
            f"No qualifying comps within {radius_miles} mi over the last {months} mo "
            f"(checked {len(features)} sales)"
        )
    if used_relaxed_land:
        result.notes.append(
            "Using lower-confidence fallback land comps outside the exact zoning or lot-size filters."
        )
    if used_relaxed_unit:
        result.notes.append(
            "Using lower-confidence fallback improved sales outside the exact zoning filter."
        )
    if not has_improvement_signal:
        result.notes.append(
            "Sales dataset lacks building fields — land/improved sales could not be "
            "separated; ADV per unit unavailable from comps"
        )
    elif not unit_comps:
        result.notes.append("No nearby improved sales found — ADV per unit unavailable from comps")

    return result
