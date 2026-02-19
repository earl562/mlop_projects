"""Multi-county property lookup via ArcGIS REST APIs.

Queries county Property Appraiser open data to get real property records:
folio, zoning code, lot size, building info, owner, valuations.

Supported counties:
  - Miami-Dade: ArcGIS FeatureServer (8Pc9XBTAsYuxx9Ny)
  - Broward: ArcGIS MapServer (BCPA)
  - Palm Beach: ArcGIS FeatureServer (ZWOoUZbtaYePLlPw)

All endpoints are public, no authentication required.
"""

import logging
import re

import httpx

from plotlot.core.types import PropertyRecord
from plotlot.observability.tracing import start_span, trace

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Miami-Dade County
# ---------------------------------------------------------------------------

MDC_PROPERTY_URL = (
    "https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/ArcGIS/rest/services"
    "/PaGISView_gdb/FeatureServer/0/query"
)
MDC_MUNICIPAL_ZONING_URL = (
    "https://gisweb.miamidade.gov/arcgis/rest/services"
    "/LandManagement/MD_Zoning/MapServer/2/query"
)
MDC_UNINCORPORATED_ZONING_URL = (
    "https://gisweb.miamidade.gov/arcgis/rest/services"
    "/LandManagement/MD_Zoning/MapServer/1/query"
)
MDC_PROPERTY_FIELDS = (
    "FOLIO,TRUE_SITE_ADDR,TRUE_SITE_CITY,TRUE_OWNER1,"
    "DOR_CODE_CUR,DOR_DESC,BEDROOM_COUNT,BATHROOM_COUNT,"
    "HALF_BATHROOM_COUNT,FLOOR_COUNT,UNIT_COUNT,"
    "BUILDING_ACTUAL_AREA,BUILDING_HEATED_AREA,LOT_SIZE,"
    "YEAR_BUILT,ASSESSED_VAL_CUR,PRICE_1,DOS_1,LEGAL"
)

# ---------------------------------------------------------------------------
# Broward County
# ---------------------------------------------------------------------------

BROWARD_PROPERTY_URL = (
    "https://gisweb-adapters.bcpa.net/arcgis/rest/services"
    "/BCPA_EXTERNAL_JAN26/MapServer/36/query"
)
BROWARD_PARCELS_URL = (
    "https://gisweb-adapters.bcpa.net/arcgis/rest/services"
    "/BCPA_EXTERNAL_JAN26/MapServer/16/query"
)
BROWARD_ZONING_URL = (
    "https://gisweb-adapters.bcpa.net/arcgis/rest/services"
    "/BCPA_EXTERNAL_JAN26/MapServer/9/query"
)
BROWARD_PROPERTY_FIELDS = (
    "FOLIO_NUMBER,SITUS_STREET_NUMBER,SITUS_STREET_DIRECTION,"
    "SITUS_STREET_NAME,SITUS_STREET_TYPE,SITUS_CITY,"
    "NAME_LINE_1,USE_CODE,BLDG_USE_CODE,BLDG_YEAR_BUILT,"
    "BLDG_ADJ_SQ_FOOTAGE,UNDER_AIR_SQFT,"
    "JUST_BUILDING_VALUE"
)

# ---------------------------------------------------------------------------
# Palm Beach County
# ---------------------------------------------------------------------------

PBC_PROPERTY_URL = (
    "https://services1.arcgis.com/ZWOoUZbtaYePLlPw/arcgis/rest/services"
    "/Parcels_and_Property_Details_WebMercator/FeatureServer/0/query"
)
PBC_PROPERTY_FIELDS = (
    "PARCEL_NUMBER,SITE_ADDR_STR,MUNICIPALITY,OWNER_NAME1,"
    "PROPERTY_USE,YRBLT,ACRES,ASSESSED_VAL,TOTAL_MARKET,"
    "PRICE,SALE_DATE,LEGAL1"
)
PBC_ZONING_URL = (
    "https://maps.co.palm-beach.fl.us/arcgis/rest/services"
    "/OpenData/Planning_Open_Data/MapServer/9/query"
)


def _normalize_address(address: str) -> str:
    """Normalize an address for ArcGIS WHERE clause matching.

    Strips city/state/zip, uppercases, removes punctuation.
    '171 NE 209th Ter, Miami, FL 33179' → '171 NE 209 TER'
    """
    # Take only street address (before first comma)
    street = address.split(",")[0].strip().upper()
    # Remove ordinal suffixes (209TH → 209, 1ST → 1)
    street = re.sub(r"(\d+)(ST|ND|RD|TH)\b", r"\1", street)
    # Remove periods
    street = street.replace(".", "")
    return street


def _safe_float(val) -> float:
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


def _parse_lot_dimensions(legal: str) -> str:
    """Extract lot dimensions from legal description.

    'LOT SIZE 75.000 X 100' → '75 x 100'
    """
    if not legal:
        return ""
    match = re.search(r"(\d+(?:\.\d+)?)\s*[Xx]\s*(\d+(?:\.\d+)?)", legal)
    if match:
        w = match.group(1)
        h = match.group(2)
        # Strip unnecessary decimal zeros: 75.000 → 75, 75.500 → 75.5
        if "." in w:
            w = w.rstrip("0").rstrip(".")
        if "." in h:
            h = h.rstrip("0").rstrip(".")
        return f"{w} x {h}"
    return ""


async def _query_arcgis(
    url: str,
    where: str,
    out_fields: str = "*",
    extra_params: dict | None = None,
    limit: int | None = 5,
) -> list[dict]:
    """Execute an ArcGIS REST query and return features."""
    with start_span(name="arcgis_query", span_type="TOOL") as span:
        span.set_inputs({"url": url, "where": where[:200], "limit": limit})

        params = {
            "where": where,
            "outFields": out_fields,
            "f": "json",
            "returnGeometry": "true",
        }
        # Some MapServer tables (e.g., Broward BCPA) error on resultRecordCount
        # without orderByFields — only include limit when explicitly set
        if limit:
            params["resultRecordCount"] = str(limit)
        if extra_params:
            params.update(extra_params)

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        features = data.get("features", [])
        if not features:
            logger.debug("ArcGIS query returned 0 features: %s", where)
        span.set_outputs({"feature_count": len(features)})
        return features


async def _spatial_query_zoning(
    url: str, lat: float, lng: float,
) -> tuple[str, str]:
    """Point-in-polygon spatial query to get zoning code for coordinates."""
    with start_span(name="spatial_query_zoning", span_type="TOOL") as span:
        span.set_inputs({"url": url, "lat": lat, "lng": lng})

        params = {
            "geometry": f"{lng},{lat}",
            "geometryType": "esriGeometryPoint",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "*",
            "f": "json",
            "returnGeometry": "false",
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()

            features = data.get("features", [])
            if not features:
                span.set_outputs({"zoning_code": "", "zoning_desc": ""})
                return "", ""

            attrs = features[0].get("attributes", {})
            # Check multiple possible field names; strip whitespace since some
            # layers return " " (space) for empty values
            zone = ""
            for key in ("ZONE", "ZONING", "ZONE_", "ZONE_NAME", "FCODE"):
                val = str(attrs.get(key) or "").strip()
                if val:
                    zone = val
                    break
            desc = ""
            for key in ("ZONE_DESC", "ZONING_DESC", "SHORT_DESC", "DESCRIPTION", "FNAME"):
                val = str(attrs.get(key) or "").strip()
                if val:
                    desc = val
                    break
            span.set_outputs({"zoning_code": zone, "zoning_desc": desc})
            return zone, desc
        except Exception as e:
            logger.warning("Zoning spatial query failed: %s", e)
            span.set_outputs({"error": str(e)})
            return "", ""


# ---------------------------------------------------------------------------
# Miami-Dade lookup
# ---------------------------------------------------------------------------

async def _lookup_miami_dade(address: str, lat: float | None, lng: float | None) -> PropertyRecord | None:
    """Look up property in Miami-Dade County."""
    with start_span(name="lookup_miami_dade", span_type="TOOL") as span:
        span.set_inputs({"address": address, "lat": lat, "lng": lng})
        street = _normalize_address(address)

        features = await _query_arcgis(
            MDC_PROPERTY_URL,
            where=f"TRUE_SITE_ADDR LIKE '%{street}%'",
            out_fields=MDC_PROPERTY_FIELDS,
        )
        if not features:
            # Try shorter match (first two tokens)
            tokens = street.split()
            if len(tokens) >= 2:
                short = " ".join(tokens[:2])
                features = await _query_arcgis(
                    MDC_PROPERTY_URL,
                    where=f"TRUE_SITE_ADDR LIKE '%{short}%'",
                    out_fields=MDC_PROPERTY_FIELDS,
                )
        if not features:
            span.set_outputs({"error": "no_features_found"})
            return None

        attrs = features[0].get("attributes", {})
        geom = features[0].get("geometry", {})

        # Get coordinates from feature if not provided
        feat_lat = lat or geom.get("y")
        feat_lng = lng or geom.get("x")

        # Spatial zoning query — try municipal layer first (covers incorporated cities),
        # fall back to unincorporated layer (has richer ZONE_DESC field)
        zoning_code, zoning_desc = "", ""
        if feat_lat and feat_lng:
            zoning_code, zoning_desc = await _spatial_query_zoning(
                MDC_MUNICIPAL_ZONING_URL, feat_lat, feat_lng,
            )
            # Municipal layer returns ZONE=NONE for unincorporated areas
            if not zoning_code or zoning_code.upper() == "NONE":
                zoning_code, zoning_desc = await _spatial_query_zoning(
                    MDC_UNINCORPORATED_ZONING_URL, feat_lat, feat_lng,
                )

        legal = attrs.get("LEGAL") or ""
        folio = str(attrs.get("FOLIO") or "")

        span.set_outputs({"folio": folio, "zoning_code": zoning_code})
        return PropertyRecord(
            folio=folio,
            address=str(attrs.get("TRUE_SITE_ADDR") or ""),
            municipality=str(attrs.get("TRUE_SITE_CITY") or ""),
            county="Miami-Dade",
            owner=str(attrs.get("TRUE_OWNER1") or ""),
            zoning_code=zoning_code,
            zoning_description=zoning_desc,
            land_use_code=str(attrs.get("DOR_CODE_CUR") or ""),
            land_use_description=str(attrs.get("DOR_DESC") or ""),
            lot_size_sqft=float(attrs.get("LOT_SIZE") or 0),
            lot_dimensions=_parse_lot_dimensions(legal),
            bedrooms=int(attrs.get("BEDROOM_COUNT") or 0),
            bathrooms=float(attrs.get("BATHROOM_COUNT") or 0),
            half_baths=int(attrs.get("HALF_BATHROOM_COUNT") or 0),
            floors=int(attrs.get("FLOOR_COUNT") or 0),
            living_units=int(attrs.get("UNIT_COUNT") or 0),
            building_area_sqft=float(attrs.get("BUILDING_ACTUAL_AREA") or 0),
            living_area_sqft=float(attrs.get("BUILDING_HEATED_AREA") or 0),
            year_built=int(attrs.get("YEAR_BUILT") or 0),
            assessed_value=float(attrs.get("ASSESSED_VAL_CUR") or 0),
            last_sale_price=float(attrs.get("PRICE_1") or 0),
            last_sale_date=str(attrs.get("DOS_1") or ""),
            lat=feat_lat,
            lng=feat_lng,
        )


# ---------------------------------------------------------------------------
# Broward County lookup
# ---------------------------------------------------------------------------

async def _lookup_broward(address: str, lat: float | None, lng: float | None) -> PropertyRecord | None:
    """Look up property in Broward County."""
    with start_span(name="lookup_broward", span_type="TOOL") as span:
        span.set_inputs({"address": address, "lat": lat, "lng": lng})
        street = _normalize_address(address)
        tokens = street.split()

        # Broward splits address into components
        if len(tokens) < 2:
            span.set_outputs({"error": "address_too_short"})
            return None

        street_num = tokens[0]
        # Join remaining as street name, removing directional prefixes and type suffixes
        # Broward stores direction in SITUS_STREET_DIRECTION, not in SITUS_STREET_NAME
        remaining = tokens[1:]
        # Strip leading directional (N, S, E, W, NE, NW, SE, SW)
        if remaining and remaining[0] in {"N", "S", "E", "W", "NE", "NW", "SE", "SW"}:
            remaining = remaining[1:]
        street_name = " ".join(remaining)
        # Remove type suffixes for LIKE match
        for suffix in ["BLVD", "AVE", "ST", "DR", "CT", "LN", "PL", "RD", "TER", "WAY", "CIR"]:
            street_name = re.sub(rf"\b{suffix}\b", "", street_name).strip()

        where = (
            f"SITUS_STREET_NUMBER='{street_num}' "
            f"AND SITUS_STREET_NAME LIKE '%{street_name}%'"
        )

        features = await _query_arcgis(
            BROWARD_PROPERTY_URL,
            where=where,
            out_fields=BROWARD_PROPERTY_FIELDS,
            limit=None,  # Broward MapServer errors on resultRecordCount without orderBy
        )
        if not features:
            span.set_outputs({"error": "no_features_found"})
            return None

        attrs = features[0].get("attributes", {})

        # Build address from components
        addr_parts = [
            str(attrs.get("SITUS_STREET_NUMBER") or ""),
            str(attrs.get("SITUS_STREET_DIRECTION") or ""),
            str(attrs.get("SITUS_STREET_NAME") or ""),
            str(attrs.get("SITUS_STREET_TYPE") or ""),
        ]
        full_addr = " ".join(p for p in addr_parts if p).strip()

        # Extract coordinates from feature geometry as fallback (Miami-Dade pattern)
        geom = features[0].get("geometry", {})
        feat_lat = lat or geom.get("y")
        feat_lng = lng or geom.get("x")

        # Spatial zoning query for Broward
        zoning_code, zoning_desc = "", ""
        if feat_lat and feat_lng:
            zoning_code, zoning_desc = await _spatial_query_zoning(
                BROWARD_ZONING_URL, feat_lat, feat_lng,
            )

        # Query Parcels layer for lot size (SHAPE.STArea() in sqft, EPSG 2236)
        folio = str(attrs.get("FOLIO_NUMBER") or "")
        lot_sqft = 0.0
        if folio:
            parcel_features = await _query_arcgis(
                BROWARD_PARCELS_URL,
                where=f"FOLIO='{folio}'",
                out_fields="*",
                limit=1,
            )
            if parcel_features:
                p_attrs = parcel_features[0].get("attributes", {})
                lot_sqft = _safe_float(
                    p_attrs.get("SHAPE.STArea()") or p_attrs.get("Shape.STArea()")
                    or p_attrs.get("Shape__Area") or p_attrs.get("SHAPE_Area")
                )

        span.set_outputs({"folio": folio, "zoning_code": zoning_code})
        return PropertyRecord(
            folio=folio,
            address=full_addr,
            municipality=str(attrs.get("SITUS_CITY") or ""),
            county="Broward",
            owner=str(attrs.get("NAME_LINE_1") or ""),
            zoning_code=zoning_code,
            zoning_description=zoning_desc,
            land_use_code=str(attrs.get("USE_CODE") or ""),
            lot_size_sqft=lot_sqft,
            building_area_sqft=_safe_float(attrs.get("BLDG_ADJ_SQ_FOOTAGE")),
            living_area_sqft=_safe_float(attrs.get("UNDER_AIR_SQFT")),
            year_built=int(attrs.get("BLDG_YEAR_BUILT") or 0),
            assessed_value=_safe_float(attrs.get("JUST_BUILDING_VALUE")),
            lat=feat_lat,
            lng=feat_lng,
        )


# ---------------------------------------------------------------------------
# Palm Beach County lookup
# ---------------------------------------------------------------------------

async def _lookup_palm_beach(address: str, lat: float | None, lng: float | None) -> PropertyRecord | None:
    """Look up property in Palm Beach County."""
    with start_span(name="lookup_palm_beach", span_type="TOOL") as span:
        span.set_inputs({"address": address, "lat": lat, "lng": lng})
        street = _normalize_address(address)

        features = await _query_arcgis(
            PBC_PROPERTY_URL,
            where=f"SITE_ADDR_STR LIKE '%{street}%'",
            out_fields=PBC_PROPERTY_FIELDS,
        )
        if not features:
            span.set_outputs({"error": "no_features_found"})
            return None

        attrs = features[0].get("attributes", {})

        acres = float(attrs.get("ACRES") or 0)
        lot_sqft = acres * 43560 if acres else 0.0

        year_str = attrs.get("YRBLT") or ""
        year_built = int(year_str) if year_str.isdigit() else 0

        sale_date = attrs.get("SALE_DATE") or ""
        if isinstance(sale_date, (int, float)) and sale_date > 0:
            from datetime import datetime, timezone
            try:
                sale_date = datetime.fromtimestamp(sale_date / 1000, tz=timezone.utc).strftime("%m/%d/%Y")
            except (ValueError, OSError):
                sale_date = str(sale_date)

        # Spatial zoning query for Palm Beach
        zoning_code, zoning_desc = "", ""
        if lat and lng:
            zoning_code, zoning_desc = await _spatial_query_zoning(
                PBC_ZONING_URL, lat, lng,
            )

        folio = str(attrs.get("PARCEL_NUMBER") or "")
        span.set_outputs({"folio": folio, "zoning_code": zoning_code})
        return PropertyRecord(
            folio=folio,
            address=str(attrs.get("SITE_ADDR_STR") or ""),
            municipality=str(attrs.get("MUNICIPALITY") or ""),
            county="Palm Beach",
            owner=str(attrs.get("OWNER_NAME1") or ""),
            zoning_code=zoning_code,
            zoning_description=zoning_desc,
            land_use_code=str(attrs.get("PROPERTY_USE") or ""),
            lot_size_sqft=lot_sqft,
            year_built=year_built,
            assessed_value=float(attrs.get("ASSESSED_VAL") or 0),
            market_value=float(attrs.get("TOTAL_MARKET") or 0),
            last_sale_price=float(attrs.get("PRICE") or 0),
            last_sale_date=str(sale_date),
            lat=lat,
            lng=lng,
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# County name → lookup function
_COUNTY_HANDLERS = {
    "miami-dade": _lookup_miami_dade,
    "miami dade": _lookup_miami_dade,
    "broward": _lookup_broward,
    "palm beach": _lookup_palm_beach,
}


@trace(name="lookup_property", span_type="TOOL")
async def lookup_property(
    address: str,
    county: str,
    lat: float | None = None,
    lng: float | None = None,
) -> PropertyRecord | None:
    """Look up property data from the county Property Appraiser.

    Args:
        address: Full property address.
        county: County name (e.g., 'Miami-Dade', 'Broward', 'Palm Beach').
        lat: Latitude from geocoding (used for zoning spatial queries).
        lng: Longitude from geocoding (used for zoning spatial queries).

    Returns:
        PropertyRecord with all available data, or None if not found.
    """
    county_key = county.lower().strip()
    handler = _COUNTY_HANDLERS.get(county_key)

    if not handler:
        logger.warning("No property lookup handler for county: %s", county)
        return None

    try:
        record = await handler(address, lat, lng)
        if record:
            logger.info(
                "Property found: folio=%s, zoning=%s, lot=%s sqft",
                record.folio, record.zoning_code or "N/A", record.lot_size_sqft,
            )
        return record
    except Exception as e:
        logger.error("Property lookup failed for %s (%s): %s", address, county, e)
        return None
