"""Bulk property search across South Florida counties via ArcGIS REST APIs.

Translates structured search parameters into county-specific ArcGIS WHERE
clauses, executes paginated queries, and normalizes results into a consistent
schema. Designed to be called by the chat agent's ``search_properties`` tool.

Architecture:
  LLM fills structured PropertySearchParams → build_where_clause() produces
  county-specific WHERE → _query_arcgis_paginated() fetches pages →
  _normalize_record() produces uniform dicts.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from plotlot.retrieval.property import (
    MDC_PROPERTY_URL,
    BROWARD_PROPERTY_URL,
    PBC_PROPERTY_URL,
    _query_arcgis,
    _safe_float,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# County field mappings
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CountyFieldMap:
    """Maps abstract property fields to county-specific ArcGIS field names."""

    county_name: str
    url: str
    land_use_code: str
    owner_name: str
    sale_date: str
    sale_date_format: str  # "string_mmddyyyy" | "none" | "epoch_ms"
    sale_price: str
    lot_size: str
    lot_size_unit: str  # "sqft" | "none" | "acres"
    address: str
    city: str
    assessed_value: str
    year_built: str
    folio: str
    out_fields: str
    needs_order_by: bool = False
    order_by_field: str | None = None


MDC_FIELDS = CountyFieldMap(
    county_name="Miami-Dade",
    url=MDC_PROPERTY_URL,
    land_use_code="DOR_CODE_CUR",
    owner_name="TRUE_OWNER1",
    sale_date="DOS_1",
    sale_date_format="string_mmddyyyy",
    sale_price="PRICE_1",
    lot_size="LOT_SIZE",
    lot_size_unit="sqft",
    address="TRUE_SITE_ADDR",
    city="TRUE_SITE_CITY",
    assessed_value="ASSESSED_VAL_CUR",
    year_built="YEAR_BUILT",
    folio="FOLIO",
    out_fields=(
        "FOLIO,TRUE_SITE_ADDR,TRUE_SITE_CITY,TRUE_OWNER1,"
        "DOR_CODE_CUR,DOR_DESC,LOT_SIZE,YEAR_BUILT,"
        "ASSESSED_VAL_CUR,PRICE_1,DOS_1"
    ),
)

BROWARD_FIELDS = CountyFieldMap(
    county_name="Broward",
    url=BROWARD_PROPERTY_URL,
    land_use_code="USE_CODE",
    owner_name="NAME_LINE_1",
    sale_date="",
    sale_date_format="none",
    sale_price="",
    lot_size="",
    lot_size_unit="none",
    address="SITUS_STREET_NUMBER",  # composite — handled in normalizer
    city="SITUS_CITY",
    assessed_value="JUST_BUILDING_VALUE",
    year_built="BLDG_YEAR_BUILT",
    folio="FOLIO_NUMBER",
    out_fields=(
        "FOLIO_NUMBER,SITUS_STREET_NUMBER,SITUS_STREET_DIRECTION,"
        "SITUS_STREET_NAME,SITUS_STREET_TYPE,SITUS_CITY,"
        "NAME_LINE_1,USE_CODE,BLDG_YEAR_BUILT,JUST_BUILDING_VALUE"
    ),
    needs_order_by=True,
    order_by_field="FOLIO_NUMBER",
)

PBC_FIELDS = CountyFieldMap(
    county_name="Palm Beach",
    url=PBC_PROPERTY_URL,
    land_use_code="PROPERTY_USE",
    owner_name="OWNER_NAME1",
    sale_date="SALE_DATE",
    sale_date_format="epoch_ms",
    sale_price="PRICE",
    lot_size="ACRES",
    lot_size_unit="acres",
    address="SITE_ADDR_STR",
    city="MUNICIPALITY",
    assessed_value="ASSESSED_VAL",
    year_built="YRBLT",
    folio="PARCEL_NUMBER",
    out_fields=(
        "PARCEL_NUMBER,SITE_ADDR_STR,MUNICIPALITY,OWNER_NAME1,"
        "PROPERTY_USE,YRBLT,ACRES,ASSESSED_VAL,PRICE,SALE_DATE"
    ),
)

_COUNTY_MAP: dict[str, CountyFieldMap] = {
    "miami-dade": MDC_FIELDS,
    "miami dade": MDC_FIELDS,
    "broward": BROWARD_FIELDS,
    "palm beach": PBC_FIELDS,
}

# Broward uses 2-letter city codes in SITUS_CITY instead of full names
BROWARD_CITY_CODES: dict[str, str] = {
    "coconut creek": "CK",
    "cooper city": "CY",
    "coral springs": "CS",
    "dania beach": "DN",
    "dania": "DN",
    "davie": "DV",
    "deerfield beach": "DB",
    "fort lauderdale": "FL",
    "hallandale beach": "HA",
    "hallandale": "HA",
    "hillsboro beach": "HB",
    "hollywood": "HW",
    "lauderdale lakes": "LP",
    "lauderdale-by-the-sea": "LS",
    "lauderhill": "LL",
    "lazy lake": "LZ",
    "lighthouse point": "LH",
    "margate": "MG",
    "miramar": "MM",
    "north lauderdale": "NL",
    "oakland park": "OP",
    "parkland": "PK",
    "pembroke park": "PI",
    "pembroke pines": "PB",
    "plantation": "PL",
    "pompano beach": "PA",
    "sea ranch lakes": "SL",
    "southwest ranches": "SW",
    "sunrise": "SU",
    "tamarac": "TM",
    "west park": "WP",
    "weston": "WM",
    "wilton manors": "WS",
}

# ---------------------------------------------------------------------------
# Land use code mapping — FL DOR codes per county
# ---------------------------------------------------------------------------

LAND_USE_CODES: dict[str, dict[str, list[str]]] = {
    "miami-dade": {
        "vacant_residential": ["0000"],
        "vacant_commercial": ["0100"],
        "single_family": ["0101", "0102"],
        "multifamily": ["0104", "0800", "0801", "0802", "0803", "0804"],
        "commercial": ["1100", "1200", "1300", "1400", "1500", "1600", "1700"],
        "industrial": ["4100", "4200", "4800", "4900"],
        "agricultural": ["5000", "5100", "5400", "5500", "5600", "5700", "5800", "5900", "6000"],
    },
    "broward": {
        "vacant_residential": ["00"],
        "vacant_commercial": ["10"],
        "single_family": ["01"],
        "multifamily": ["03", "04", "08"],
        "commercial": ["11", "12", "13", "14", "15", "16", "17"],
        "industrial": ["41", "42", "48", "49"],
        "agricultural": ["50", "51", "54", "55", "56", "57", "58", "59", "60"],
    },
    "palm beach": {
        "vacant_residential": ["00"],
        "vacant_commercial": ["10"],
        "single_family": ["01", "02"],
        "multifamily": ["03", "04", "08"],
        "commercial": ["11", "12", "13", "14", "15", "16", "17"],
        "industrial": ["41", "42", "48", "49"],
        "agricultural": ["50", "51", "54", "55", "56", "57", "58", "59", "60"],
    },
}

# ---------------------------------------------------------------------------
# Search parameters & dataset info
# ---------------------------------------------------------------------------


@dataclass
class PropertySearchParams:
    """Structured search criteria — LLM fills this, we translate to WHERE."""

    county: str
    land_use_type: str | None = None
    city: str | None = None
    max_sale_date: str | None = None  # ISO "2006-01-01"
    min_lot_size_sqft: float | None = None
    max_lot_size_sqft: float | None = None
    min_sale_price: float | None = None
    max_sale_price: float | None = None
    min_assessed_value: float | None = None
    max_assessed_value: float | None = None
    year_built_before: int | None = None
    year_built_after: int | None = None
    owner_name_contains: str | None = None
    max_results: int = 500


@dataclass
class DatasetInfo:
    """In-session bulk property search results."""

    records: list[dict]
    search_params: dict
    query_description: str
    total_available: int
    fetched_at: str


# ---------------------------------------------------------------------------
# WHERE clause builder
# ---------------------------------------------------------------------------


def _get_field_map(county: str) -> CountyFieldMap:
    """Resolve county name to field map, raising ValueError for unsupported."""
    key = county.lower().strip()
    fm = _COUNTY_MAP.get(key)
    if not fm:
        raise ValueError(f"Unsupported county: {county}. Supported: Miami-Dade, Broward, Palm Beach")
    return fm


def build_where_clause(params: PropertySearchParams) -> tuple[str, CountyFieldMap]:
    """Translate structured search params into a county-specific ArcGIS WHERE clause.

    Returns:
        (where_clause, field_map) tuple. Pure function — fully testable.
    """
    fm = _get_field_map(params.county)
    county_key = fm.county_name.lower().replace("-", " ").replace(" ", "-")
    # Normalize to key format used in LAND_USE_CODES
    if county_key == "miami dade":
        county_key = "miami-dade"
    elif county_key == "palm beach":
        county_key = "palm beach"
    else:
        county_key = county_key

    conditions: list[str] = []

    # Land use type → DOR codes
    if params.land_use_type:
        county_codes = LAND_USE_CODES.get(county_key, {})
        codes = county_codes.get(params.land_use_type, [])
        if codes:
            if len(codes) == 1:
                conditions.append(f"{fm.land_use_code}='{codes[0]}'")
            else:
                in_list = ",".join(f"'{c}'" for c in codes)
                conditions.append(f"{fm.land_use_code} IN ({in_list})")

    # City filter — Broward uses 2-letter codes
    if params.city:
        if fm.county_name == "Broward":
            city_code = BROWARD_CITY_CODES.get(params.city.lower().strip(), "")
            if city_code:
                conditions.append(f"{fm.city}='{city_code}'")
            else:
                # Try direct match (user might pass the 2-letter code)
                conditions.append(f"{fm.city}='{params.city.upper().strip()}'")
        else:
            city_upper = params.city.upper().strip()
            conditions.append(f"{fm.city}='{city_upper}'")

    # Sale date (ownership duration) — county-specific date handling
    if params.max_sale_date and fm.sale_date:
        if fm.sale_date_format == "string_mmddyyyy":
            # MDC stores dates as YYYYMMDD strings (e.g., "20060101")
            dt = datetime.fromisoformat(params.max_sale_date)
            date_str = dt.strftime("%Y%m%d")
            conditions.append(f"{fm.sale_date}<'{date_str}'")
        elif fm.sale_date_format == "epoch_ms":
            # PBC stores dates as millisecond timestamps
            dt = datetime.fromisoformat(params.max_sale_date).replace(tzinfo=timezone.utc)
            epoch_ms = int(dt.timestamp() * 1000)
            conditions.append(f"{fm.sale_date}<{epoch_ms}")

    # Lot size — handle acres vs sqft
    if params.min_lot_size_sqft is not None and fm.lot_size:
        if fm.lot_size_unit == "acres":
            acres = params.min_lot_size_sqft / 43560
            conditions.append(f"{fm.lot_size}>={acres:.4f}")
        else:
            conditions.append(f"{fm.lot_size}>={params.min_lot_size_sqft}")

    if params.max_lot_size_sqft is not None and fm.lot_size:
        if fm.lot_size_unit == "acres":
            acres = params.max_lot_size_sqft / 43560
            conditions.append(f"{fm.lot_size}<={acres:.4f}")
        else:
            conditions.append(f"{fm.lot_size}<={params.max_lot_size_sqft}")

    # Sale price
    if params.min_sale_price is not None and fm.sale_price:
        conditions.append(f"{fm.sale_price}>={params.min_sale_price}")
    if params.max_sale_price is not None and fm.sale_price:
        conditions.append(f"{fm.sale_price}<={params.max_sale_price}")

    # Assessed value
    if params.min_assessed_value is not None and fm.assessed_value:
        conditions.append(f"{fm.assessed_value}>={params.min_assessed_value}")
    if params.max_assessed_value is not None and fm.assessed_value:
        conditions.append(f"{fm.assessed_value}<={params.max_assessed_value}")

    # Year built
    if params.year_built_before is not None and fm.year_built:
        conditions.append(f"{fm.year_built}<{params.year_built_before}")
    if params.year_built_after is not None and fm.year_built:
        conditions.append(f"{fm.year_built}>{params.year_built_after}")

    # Owner name
    if params.owner_name_contains and fm.owner_name:
        name_upper = params.owner_name_contains.upper().strip()
        conditions.append(f"{fm.owner_name} LIKE '%{name_upper}%'")

    where = " AND ".join(conditions) if conditions else "1=1"
    return where, fm


# ---------------------------------------------------------------------------
# Record normalization
# ---------------------------------------------------------------------------


# Reverse mapping: Broward code → full city name
_BROWARD_CODE_TO_CITY: dict[str, str] = {v: k.title() for k, v in BROWARD_CITY_CODES.items()}


def _normalize_record(attrs: dict, geometry: dict | None, fm: CountyFieldMap) -> dict:
    """Normalize county-specific ArcGIS attributes into a standard dict."""
    # Address handling — Broward is composite
    if fm.county_name == "Broward":
        addr_parts = [
            str(attrs.get("SITUS_STREET_NUMBER") or ""),
            str(attrs.get("SITUS_STREET_DIRECTION") or ""),
            str(attrs.get("SITUS_STREET_NAME") or ""),
            str(attrs.get("SITUS_STREET_TYPE") or ""),
        ]
        address = " ".join(p for p in addr_parts if p).strip()
    else:
        address = str(attrs.get(fm.address) or "")

    # Lot size → always sqft
    raw_lot = _safe_float(attrs.get(fm.lot_size)) if fm.lot_size else 0.0
    if fm.lot_size_unit == "acres" and raw_lot > 0:
        lot_sqft = raw_lot * 43560
    else:
        lot_sqft = raw_lot

    # Sale date → ISO string
    sale_date = ""
    if fm.sale_date:
        raw_date = attrs.get(fm.sale_date)
        if raw_date:
            if fm.sale_date_format == "epoch_ms" and isinstance(raw_date, (int, float)) and raw_date > 0:
                try:
                    sale_date = datetime.fromtimestamp(raw_date / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
                except (ValueError, OSError):
                    sale_date = str(raw_date)
            else:
                sale_date = str(raw_date)

    # Year built
    raw_yb = attrs.get(fm.year_built) if fm.year_built else None
    if raw_yb is not None:
        try:
            year_built = int(raw_yb)
        except (ValueError, TypeError):
            year_built = 0
    else:
        year_built = 0

    # Coordinates
    lat = None
    lng = None
    if geometry:
        lat = geometry.get("y")
        lng = geometry.get("x")

    return {
        "folio": str(attrs.get(fm.folio) or ""),
        "address": address,
        "city": _BROWARD_CODE_TO_CITY.get(str(attrs.get(fm.city) or ""), str(attrs.get(fm.city) or "")) if fm.county_name == "Broward" else str(attrs.get(fm.city) or ""),
        "county": fm.county_name,
        "owner": str(attrs.get(fm.owner_name) or ""),
        "land_use_code": str(attrs.get(fm.land_use_code) or ""),
        "lot_size_sqft": round(lot_sqft, 1),
        "year_built": year_built,
        "assessed_value": _safe_float(attrs.get(fm.assessed_value)) if fm.assessed_value else 0.0,
        "last_sale_price": _safe_float(attrs.get(fm.sale_price)) if fm.sale_price else 0.0,
        "last_sale_date": sale_date,
        "lat": lat,
        "lng": lng,
    }


# ---------------------------------------------------------------------------
# Paginated bulk search
# ---------------------------------------------------------------------------


async def bulk_property_search(params: PropertySearchParams) -> list[dict]:
    """Execute paginated ArcGIS query and return normalized property records.

    Uses resultOffset + resultRecordCount for pagination.
    Returns list of normalized dicts with consistent keys.
    """
    where, fm = build_where_clause(params)
    max_results = min(params.max_results, 2000)
    page_size = 1000  # ArcGIS server typical max

    all_records: list[dict] = []
    offset = 0

    while len(all_records) < max_results:
        batch_size = min(page_size, max_results - len(all_records))

        extra_params: dict[str, str] = {
            "resultOffset": str(offset),
            "resultRecordCount": str(batch_size),
        }
        if fm.needs_order_by and fm.order_by_field:
            extra_params["orderByFields"] = fm.order_by_field

        try:
            features = await _query_arcgis(
                fm.url,
                where=where,
                out_fields=fm.out_fields,
                extra_params=extra_params,
                limit=None,  # We handle pagination via extra_params
            )
        except Exception as e:
            logger.warning("ArcGIS bulk query failed (offset=%d): %s", offset, e)
            break

        if not features:
            break

        for feat in features:
            if len(all_records) >= max_results:
                break
            record = _normalize_record(
                feat.get("attributes", {}),
                feat.get("geometry"),
                fm,
            )
            all_records.append(record)

        if len(all_records) >= max_results:
            break
        if len(features) < batch_size:
            break  # No more results
        offset += len(features)

    logger.info(
        "Bulk search: county=%s, where=%s, results=%d",
        fm.county_name, where[:100], len(all_records),
    )
    return all_records


# ---------------------------------------------------------------------------
# Safe filter parser — no eval(), regex-based
# ---------------------------------------------------------------------------

_FILTER_PATTERN = re.compile(
    r"(\w+)\s*(==|!=|>=|<=|>|<|contains)\s*(.+)",
    re.IGNORECASE,
)


def _parse_value(raw: str):
    """Parse a filter value — try numeric first, then string."""
    raw = raw.strip().strip("'\"")
    try:
        return float(raw)
    except ValueError:
        return raw


def _safe_filter(records: list[dict], expression: str) -> list[dict]:
    """Filter records using a safe expression parser.

    Supports: field == value, field > value, field < value, field >= value,
              field <= value, field != value, field contains value.
    Multiple conditions joined by ' and '.
    String values are case-insensitive.
    Invalid expressions return all records (graceful fallback).
    """
    if not expression or not records:
        return records

    # Split on ' and ' (case-insensitive)
    clauses = re.split(r"\s+and\s+", expression, flags=re.IGNORECASE)

    filters = []
    for clause in clauses:
        match = _FILTER_PATTERN.match(clause.strip())
        if not match:
            logger.warning("Unparseable filter clause: %s", clause)
            return records  # Graceful fallback
        field_name = match.group(1)
        operator = match.group(2)
        value = _parse_value(match.group(3))
        filters.append((field_name, operator, value))

    result = []
    for record in records:
        passes = True
        for field_name, operator, value in filters:
            record_val = record.get(field_name)
            if record_val is None:
                passes = False
                break

            # String comparison — case-insensitive
            if isinstance(value, str) and isinstance(record_val, str):
                rv = record_val.lower()
                v = value.lower()
            else:
                rv = record_val
                v = value

            try:
                if operator == "==":
                    passes = rv == v
                elif operator == "!=":
                    passes = rv != v
                elif operator == ">":
                    passes = rv > v
                elif operator == "<":
                    passes = rv < v
                elif operator == ">=":
                    passes = rv >= v
                elif operator == "<=":
                    passes = rv <= v
                elif operator.lower() == "contains":
                    passes = str(v).lower() in str(rv).lower()
                else:
                    passes = False
            except TypeError:
                passes = False

            if not passes:
                break

        if passes:
            result.append(record)

    return result


# ---------------------------------------------------------------------------
# Dataset utilities
# ---------------------------------------------------------------------------


def compute_dataset_stats(records: list[dict]) -> dict:
    """Compute summary statistics for a dataset."""
    if not records:
        return {"count": 0}

    numeric_fields = ["lot_size_sqft", "assessed_value", "last_sale_price", "year_built"]
    stats: dict = {"count": len(records)}

    for field_name in numeric_fields:
        values = [r.get(field_name, 0) for r in records if r.get(field_name)]
        if values:
            stats[field_name] = {
                "min": min(values),
                "max": max(values),
                "avg": round(sum(values) / len(values), 1),
            }

    # Unique cities
    cities = list(set(str(r.get("city", "")) for r in records if r.get("city")))
    stats["unique_cities"] = sorted(cities)[:30]

    # Unique land use codes
    codes = list(set(str(r.get("land_use_code", "")) for r in records if r.get("land_use_code")))
    stats["unique_land_use_codes"] = sorted(codes)

    return stats


def describe_search(args: dict) -> str:
    """Build a human-readable description of a search from its parameters."""
    parts = []
    if args.get("land_use_type"):
        parts.append(args["land_use_type"].replace("_", " "))
    parts.append(f"in {args.get('county', 'unknown county')}")
    if args.get("city"):
        parts.append(f"({args['city']})")
    if args.get("ownership_min_years"):
        parts.append(f"owned {args['ownership_min_years']}+ years")
    if args.get("min_lot_size_sqft"):
        parts.append(f">={args['min_lot_size_sqft']:,.0f} sqft")
    return " ".join(parts).strip().title()
