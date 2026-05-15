"""California county PropertyProvider.

Supports ArcGIS-based property lookups for five California counties:
- Sacramento (Citrus Heights, Lincoln, Rocklin)
- Contra Costa (El Cerrito, Lafayette, Moraga, Orinda, Richmond)
- Alameda (Alameda city, Hayward, Newark, Oakland)
- Santa Clara (Campbell, Los Altos, Los Gatos, Milpitas, Monte Sereno,
               Morgan Hill, Mountain View, San Jose, Saratoga)
- San Mateo (Daly City, East Palo Alto, Hillsborough, Portola Valley, Woodside)

Strategy per county:
1. Spatial parcel query (lat/lng point-in-polygon → parcel attributes)
2. Address-based parcel query (fallback when spatial returns nothing)
3. Separate zoning spatial query if the parcel layer lacks a zoning field
4. UniversalProvider fallback if all county-specific attempts fail

UniversalProvider fallback is imported lazily to avoid a circular init
(universal.py depends on Firestore; we only pay that cost on fallback).
"""

from __future__ import annotations

import logging

import httpx

from plotlot.core.types import PropertyRecord
from plotlot.property.arcgis_utils import (
    extract_parcel_rings,
    normalize_address,
    safe_float,
    spatial_query,
)
from plotlot.property.base import PropertyProvider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# County configurations
#
# Each entry keyed by lowercase county name (matching Geocodio output).
# Fields:
#   parcel_url      — ArcGIS REST layer endpoint (query appended at call time)
#   zoning_url      — dedicated zoning layer; empty → read zoning from parcel attrs
#   address_field   — field name for address LIKE queries
#   zoning_fields   — ordered list of candidate field names for the zoning code
#   desc_fields     — ordered list of candidate field names for the zoning description
#   lot_fields      — ordered list of candidate field names for lot area (sq ft)
#   lot_unit        — "sqft" | "acres" | "sqm" (unit of the raw lot value)
#   folio_fields    — ordered list of candidate field names for the parcel number (APN)
# ---------------------------------------------------------------------------

_COUNTY_CONFIG: dict[str, dict] = {
    "santa clara": {
        # Santa Clara County Assessor GIS parcel layer
        "parcel_url": (
            "https://gis.sccgov.org/arcgis/rest/services"
            "/OpenData/Parcels/MapServer/0"
        ),
        # City zoning is managed by individual municipalities in SCC;
        # use the county planning zoning overlay for a consolidated view.
        "zoning_url": (
            "https://gis.sccgov.org/arcgis/rest/services"
            "/OpenData/Zoning/MapServer/0"
        ),
        "address_field": "SITE_ADDR",
        "zoning_fields": ["ZONE", "ZONING", "ZONE_CODE", "ZONING_CODE", "USE_CODE", "LU_CODE"],
        "desc_fields": ["ZONE_DESC", "ZONING_DESC", "ZONE_NAME", "USE_DESCR", "LU_DESC"],
        "lot_fields": ["SHAPE_Area", "LOT_AREA_SQFT", "SHAPE__Area", "PARCEL_AREA"],
        "lot_unit": "sqft",
        "folio_fields": ["APN", "PARCEL_NO", "PARCEL_NUM", "PARCEL_ID", "ASSESSOR_PARCEL"],
    },
    "alameda": {
        # Alameda County GIS parcel service
        "parcel_url": (
            "https://gis.acgov.org/arcgis/rest/services"
            "/PropertyInformation/MapServer/0"
        ),
        "zoning_url": "",
        "address_field": "SITE_ADDR",
        "zoning_fields": ["ZONE", "ZONING", "ZONE_CODE", "USE_CODE", "LU_CODE"],
        "desc_fields": ["ZONE_DESC", "ZONING_DESC", "ZONE_NAME", "LU_DESC"],
        "lot_fields": ["SHAPE_Area", "LOT_AREA", "PARCEL_AREA", "SHAPE__Area"],
        "lot_unit": "sqft",
        "folio_fields": ["APN", "PARCEL_NO", "OBJECTID"],
    },
    "contra costa": {
        # Contra Costa County open data parcel service
        "parcel_url": (
            "https://opendata.contracostaenviz.org/server/rest/services"
            "/OpenData/CCC_Parcels/MapServer/0"
        ),
        "zoning_url": "",
        "address_field": "SITE_ADDR",
        "zoning_fields": ["ZONE", "ZONING", "ZONE_CODE", "LAND_USE"],
        "desc_fields": ["ZONE_DESC", "ZONING_DESC", "ZONE_NAME"],
        "lot_fields": ["SHAPE_Area", "LOT_AREA", "PARCEL_AREA", "SHAPE__Area"],
        "lot_unit": "sqft",
        "folio_fields": ["APN", "PARCEL_NUM", "PARCEL_NO"],
    },
    "san mateo": {
        # San Mateo County GIS parcel service
        "parcel_url": (
            "https://gis.smcgov.org/arcgis/rest/services"
            "/OpenData/Parcels/MapServer/0"
        ),
        "zoning_url": "",
        "address_field": "SITE_ADDR",
        "zoning_fields": ["ZONE", "ZONING", "ZONE_CODE", "USE_CODE"],
        "desc_fields": ["ZONE_DESC", "ZONING_DESC", "ZONE_NAME"],
        "lot_fields": ["SHAPE_Area", "LOT_AREA", "PARCEL_AREA", "SHAPE__Area"],
        "lot_unit": "sqft",
        "folio_fields": ["APN", "PARCEL_NUM", "PARCEL_NO"],
    },
    "sacramento": {
        # Sacramento County Assessor parcel data via ArcGIS Online
        "parcel_url": (
            "https://services1.arcgis.com/Hp6G80Pky0om7QvQ/arcgis/rest/services"
            "/Sacramento_County_Parcels/FeatureServer/0"
        ),
        "zoning_url": "",
        "address_field": "SITUS_ADDRESS",
        "zoning_fields": ["ZONE", "ZONING", "ZONE_CODE", "LAND_USE_CODE"],
        "desc_fields": ["ZONE_DESC", "ZONING_DESC", "ZONE_NAME", "LAND_USE_DESC"],
        "lot_fields": ["SHAPE_Area", "PARCEL_SQFT", "LOT_AREA", "SHAPE__Area"],
        "lot_unit": "sqft",
        "folio_fields": ["APN", "PARCEL_NUM", "PARCEL_NUMBER", "ASSESSOR_PARCEL_NUMBER"],
    },
}

# sq meters → sq ft conversion (used when lot_unit = "sqm")
_SQM_TO_SQFT = 10.7639


class CaliforniaProvider(PropertyProvider):
    """PropertyProvider for the five CA counties with ingested ordinance data.

    Uses county-specific ArcGIS REST endpoints with a spatial-first query
    strategy (lat/lng point-in-polygon), falling back to address LIKE search,
    then to UniversalProvider discovery if both fail.
    """

    async def lookup(
        self,
        address: str,
        county: str,
        *,
        lat: float | None = None,
        lng: float | None = None,
        state: str = "",
    ) -> PropertyRecord | None:
        county_key = county.lower().strip()
        config = _COUNTY_CONFIG.get(county_key)

        if config is None:
            logger.warning("CaliforniaProvider: no config for county %r", county)
            return await self._universal_fallback(address, county, lat=lat, lng=lng, state=state)

        # --- 1. Try county-specific ArcGIS endpoints ---
        parcel_url = config["parcel_url"] + "/query"
        record = None

        if lat is not None and lng is not None:
            record = await self._spatial_parcel(parcel_url, lat, lng, config, county)

        if record is None:
            record = await self._address_parcel(parcel_url, address, config, county)

        if record is None:
            logger.info(
                "CaliforniaProvider: county endpoint returned nothing for %s (%s); "
                "trying UniversalProvider",
                address,
                county,
            )
            return await self._universal_fallback(address, county, lat=lat, lng=lng, state=state)

        # Preserve lat/lng from geocodio when the parcel query didn't return geometry
        if record.lat is None:
            record.lat = lat
        if record.lng is None:
            record.lng = lng

        # --- 2. Zoning spatial query (if the parcel layer lacks zoning) ---
        if not record.zoning_code and config.get("zoning_url") and lat and lng:
            zoning_url = config["zoning_url"] + "/query"
            zoning_code, zoning_desc = await self._spatial_zoning(
                zoning_url, lat, lng, config
            )
            if zoning_code:
                record.zoning_code = zoning_code
                record.zoning_description = zoning_desc

        return record

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _spatial_parcel(
        self,
        url: str,
        lat: float,
        lng: float,
        config: dict,
        county: str,
    ) -> PropertyRecord | None:
        """Point-in-polygon spatial query to retrieve the parcel under lat/lng."""
        try:
            features = await spatial_query(url, lat, lng)
            if not features:
                return None
            return self._parse_feature(features[0], config, county)
        except Exception as exc:
            logger.debug("CaliforniaProvider spatial parcel failed (%s): %s", url, exc)
            return None

    async def _address_parcel(
        self,
        url: str,
        address: str,
        config: dict,
        county: str,
    ) -> PropertyRecord | None:
        """Address LIKE query against the parcel layer."""
        addr_field = config["address_field"]
        normalized = normalize_address(address)
        # Try full normalized address first, then house-number + first street token
        where_clauses = [
            f"UPPER({addr_field}) LIKE '%{normalized}%'",
        ]
        tokens = normalized.split()
        if len(tokens) >= 2:
            short = " ".join(tokens[:2])
            where_clauses.append(f"UPPER({addr_field}) LIKE '%{short}%'")

        params_base = {
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "json",
            "resultRecordCount": "5",
        }

        for where in where_clauses:
            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    resp = await client.get(url, params={**params_base, "where": where})
                    resp.raise_for_status()
                    data = resp.json()
                features = data.get("features", [])
                if features:
                    return self._parse_feature(features[0], config, county)
            except Exception as exc:
                logger.debug(
                    "CaliforniaProvider address query failed (%s | %s): %s",
                    url,
                    where[:80],
                    exc,
                )
        return None

    async def _spatial_zoning(
        self,
        url: str,
        lat: float,
        lng: float,
        config: dict,
    ) -> tuple[str, str]:
        """Spatial query against a dedicated zoning layer."""
        try:
            features = await spatial_query(url, lat, lng)
            if not features:
                return "", ""
            attrs = features[0].get("attributes", {})
            return self._extract_zoning(attrs, config)
        except Exception as exc:
            logger.debug("CaliforniaProvider zoning spatial failed: %s", exc)
            return "", ""

    def _parse_feature(
        self,
        feature: dict,
        config: dict,
        county: str,
    ) -> PropertyRecord:
        """Convert an ArcGIS feature dict to PropertyRecord."""
        attrs = feature.get("attributes", {})

        folio = self._first_value(attrs, config["folio_fields"])
        address_val = str(attrs.get(config["address_field"]) or "")
        zoning_code, zoning_desc = self._extract_zoning(attrs, config)

        raw_lot = safe_float(self._first_value(attrs, config["lot_fields"]))
        unit = config.get("lot_unit", "sqft")
        if unit == "acres":
            lot_sqft = raw_lot * 43_560
        elif unit == "sqm":
            lot_sqft = raw_lot * _SQM_TO_SQFT
        else:
            # sqft — but ArcGIS SHAPE_Area in Web Mercator projection returns sq meters.
            # Typical residential lot: 3 000–50 000 sqft (280–4 600 sqm).
            # Heuristic: if value < 500, it is almost certainly sq meters (500 sqm ≈ 5 382 sqft).
            # Values ≥ 500 are taken as-is (sqft) since 500 sqft is below any real lot size
            # but 500 sqm is a plausible small urban parcel (~5 000 sqft).
            if 0 < raw_lot < 500:
                lot_sqft = raw_lot * _SQM_TO_SQFT
            else:
                lot_sqft = raw_lot

        owner = str(
            attrs.get("OWNER") or attrs.get("OWNER_NAME") or attrs.get("TAXPAYER") or ""
        )
        municipality = str(
            attrs.get("CITY")
            or attrs.get("MUNICIPALITY")
            or attrs.get("JURIS")
            or attrs.get("SITE_CITY")
            or ""
        )
        year_built = int(
            safe_float(
                attrs.get("YEAR_BUILT")
                or attrs.get("YR_BUILT")
                or attrs.get("YEAR_BLT")
                or 0
            )
        )
        assessed = safe_float(
            attrs.get("ASSESSED_VALUE")
            or attrs.get("ASSESSED_VAL")
            or attrs.get("TOTAL_VALUE")
            or 0
        )
        building_sqft = safe_float(
            attrs.get("BUILDING_SQFT")
            or attrs.get("BLDG_SQFT")
            or attrs.get("LIVING_SQFT")
            or 0
        )

        # Extract parcel geometry rings if present
        parcel_geom = extract_parcel_rings(feature)

        # Lat/lng from geometry (point) — some parcel layers return centroid
        geom = feature.get("geometry") or {}
        feat_lat: float | None = geom.get("y")
        feat_lng: float | None = geom.get("x")

        return PropertyRecord(
            folio=str(folio),
            address=address_val,
            owner=owner,
            municipality=municipality,
            county=county.title(),
            zoning_code=zoning_code,
            zoning_description=zoning_desc,
            lot_size_sqft=lot_sqft,
            year_built=year_built,
            assessed_value=assessed,
            building_area_sqft=building_sqft,
            lat=feat_lat,
            lng=feat_lng,
            parcel_geometry=parcel_geom,
        )

    @staticmethod
    def _first_value(attrs: dict, fields: list[str]) -> object:
        """Return the value of the first field in `fields` that is non-empty."""
        for f in fields:
            val = attrs.get(f)
            if val is not None and str(val).strip() not in ("", "None", "null"):
                return val
        return ""

    @staticmethod
    def _extract_zoning(attrs: dict, config: dict) -> tuple[str, str]:
        """Extract zoning code + description from attribute dict using config candidates."""
        code = ""
        for f in config["zoning_fields"]:
            val = str(attrs.get(f) or "").strip()
            if val and val.lower() not in ("none", "null", "n/a", ""):
                code = val
                break

        desc = ""
        for f in config["desc_fields"]:
            val = str(attrs.get(f) or "").strip()
            if val and val.lower() not in ("none", "null", "n/a", ""):
                desc = val
                break

        return code, desc

    @staticmethod
    async def _universal_fallback(
        address: str,
        county: str,
        *,
        lat: float | None,
        lng: float | None,
        state: str,
    ) -> PropertyRecord | None:
        """Lazy import + call UniversalProvider as last-resort fallback."""
        try:
            from plotlot.property.universal import UniversalProvider

            provider = UniversalProvider()
            return await provider.lookup(address, county, lat=lat, lng=lng, state=state)
        except Exception as exc:
            logger.warning(
                "CaliforniaProvider: UniversalProvider fallback failed for %s (%s): %s",
                address,
                county,
                exc,
            )
            return None
