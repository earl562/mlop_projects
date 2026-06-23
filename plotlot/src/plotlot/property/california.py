"""California PropertyProvider — county-specific + statewide fallback.

Lookup hierarchy for any California address:
  1. County-specific ArcGIS endpoint (five counties with verified configs below)
  2. CA statewide parcel layer (all 58 counties; returns APN, address, lot area)
  3. UniversalProvider (ArcGIS Hub discovery + Firestore cache)

This means any CA county we ingest ordinances for — Marin, Sonoma, SF, Santa Cruz,
etc. — gets property lookup automatically via the statewide layer without a new config.

County-specific configs exist where the statewide layer doesn't return a zoning code
or has known coverage gaps (Sacramento):
- Sacramento, Contra Costa, Alameda, Santa Clara, San Mateo

Zoning is almost never available at the county assessor/parcel level. For municipalities
where we've ingested ordinances, the ordinance search pipeline resolves zoning from the
retrieved chunks — an empty zoning_code on the PropertyRecord is expected and handled.

UniversalProvider fallback is imported lazily to avoid a circular init
(universal.py depends on Firestore; we only pay that cost on fallback).
"""

from __future__ import annotations

import logging
import re

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


def _escape_where(value: str) -> str:
    """Escape single quotes for ArcGIS REST API WHERE clause safety."""
    return value.replace("'", "''")


# San Diego County Assessor parcel layer — authoritative legal lot area by APN.
# The CA statewide parcel layer's polygon area diverges from the assessor's
# recorded lot: APN 4364230200 (1233 Hueneme St) is 6,489 sqft as a statewide
# polygon but 7,710 sqft per the assessor — which flips RM-3-7 by-right density
# from 6 to 7 units. San Diego's density rule keys off legal "lot area", so the
# assessor figure is authoritative. Verified 2026-06 against the City of San
# Diego HUD application (7,700 SF), Zillow (0.177 ac), and Scoutred (7,710 SF).
# Defined before _COUNTY_CONFIG because the dict literal references it at module load.
_SD_ASSESSOR_PARCEL_URL = (
    "https://gis-public.sandiegocounty.gov/arcgis/rest/services/PDS/PDS_Layers/MapServer/0"
)


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
        # Santa Clara County Regional Open Data — county-wide parcel layer covering all
        # SCC municipalities (Mountain View, San Jose, Sunnyvale, Campbell, etc.).
        # Verified 2026-05: https://map.santaclaraca.gov/maps/rest/services/OPENDATA/RegionalBaseOpenData/MapServer/7
        # Fields confirmed: APN, ZONGDSGN (zoning designation), ACREAGE, PARCITY, YEARBUILT
        # Layer is in CA State Plane Zone III (feet); spatial_query sends inSR=4326 so the
        # server reprojects our WGS84 lat/lng before doing the polygon intersection.
        # No street address field in this layer — spatial query is the primary strategy.
        "parcel_url": (
            "https://map.santaclaraca.gov/maps/rest/services"
            "/OPENDATA/RegionalBaseOpenData/MapServer/7"
        ),
        "zoning_url": "",
        "address_field": "",  # no address field; spatial query used exclusively
        "zoning_fields": ["ZONGDSGN", "GPLANCRT", "ZONE", "ZONING"],
        "desc_fields": ["SPPLAN", "ZONE_DESC", "ZONING_DESC"],
        "lot_fields": ["ACREAGE", "Shape__Area", "SHAPE_Area"],
        "lot_unit": "acres",
        "folio_fields": ["APN", "APNMAPS"],
    },
    "alameda": {
        # Alameda County Assessor parcel boundaries — ArcGIS Online hosted.
        # Verified 2026-05: https://services5.arcgis.com/ROBnTHSNjoZ2Wm1P/arcgis/rest/services/Parcels/FeatureServer/0
        # Fields confirmed: APN, SitusAddress, SitusStreetNumber, SitusStreetName,
        #   SitusCity, SitusZip, UseCode, Land, Imps, TotalNetValue, Shape__Area
        "parcel_url": (
            "https://services5.arcgis.com/ROBnTHSNjoZ2Wm1P/arcgis/rest/services"
            "/Parcels/FeatureServer/0"
        ),
        "zoning_url": "",
        "address_field": "SitusAddress",
        "zoning_fields": ["UseCode", "ZONE", "ZONING", "ZONE_CODE"],
        "desc_fields": ["ZONE_DESC", "ZONING_DESC", "ZONE_NAME"],
        "lot_fields": ["Shape__Area", "Shape_Area", "SHAPE_Area"],
        "lot_unit": "sqft",
        "folio_fields": ["APN", "APN_SORT"],
    },
    "contra costa": {
        # Contra Costa County parcel service — ArcGIS Online hosted.
        # Verified 2026-05: https://services2.arcgis.com/1ufANJSTSqs8jV0y/arcgis/rest/services/Parcel/FeatureServer/0
        # Fields confirmed: PIDPLAIN, PID, Site_Addre, Address, City, State, ZIP,
        #   Owner, AC (acreage), Shape__Area
        "parcel_url": (
            "https://services2.arcgis.com/1ufANJSTSqs8jV0y/arcgis/rest/services"
            "/Parcel/FeatureServer/0"
        ),
        "zoning_url": "",
        "address_field": "Site_Addre",
        "zoning_fields": ["ZONE", "ZONING", "ZONE_CODE", "LAND_USE"],
        "desc_fields": ["ZONE_DESC", "ZONING_DESC", "ZONE_NAME"],
        "lot_fields": ["AC", "Shape__Area", "SHAPE_Area"],
        "lot_unit": "acres",  # AC field is acreage
        "folio_fields": ["PIDPLAIN", "PID"],
    },
    "san mateo": {
        # San Mateo County Planning — Active Parcels layer.
        # Verified 2026-05: https://gis.smcgov.org/maps/rest/services/PLANNING/COUNTY_PARCELS/MapServer/0
        # Fields confirmed: APN, SITUS_ADDR, SITUS_CITY, LANDAREA, Shape
        "parcel_url": (
            "https://gis.smcgov.org/maps/rest/services/PLANNING/COUNTY_PARCELS/MapServer/0"
        ),
        "zoning_url": "",
        "address_field": "SITUS_ADDR",
        "zoning_fields": ["ZONE", "ZONING", "ZONE_CODE", "USE_CODE"],
        "desc_fields": ["ZONE_DESC", "ZONING_DESC", "ZONE_NAME"],
        "lot_fields": ["LANDAREA", "Shape__Area", "SHAPE_Area"],
        "lot_unit": "sqft",
        "folio_fields": ["APN"],
    },
    "sacramento": {
        # Sacramento County GIS — ALL Parcels layer 22.
        # Verified 2026-05: https://mapservices.gis.saccounty.net/arcgis/rest/services/PARCELS/MapServer/22
        # Fields confirmed: PARCEL_NUMBER, ZONE_ (zoning!), LANDUSE, LOTSIZE,
        #   SITUS_ADD1, STREET_NBR, STREET_NAME, CITY, NAME (owner)
        "parcel_url": (
            "https://mapservices.gis.saccounty.net/arcgis/rest/services/PARCELS/MapServer/22"
        ),
        "zoning_url": "",
        "address_field": "SITUS_ADD1",
        "zoning_fields": ["ZONE_", "LANDUSE", "ZONE", "ZONING"],
        "desc_fields": ["LANDUSE", "ZONE_DESC", "ZONING_DESC"],
        "lot_fields": ["LOTSIZE", "Shape__Area", "SHAPE_Area"],
        "lot_unit": "sqft",
        "folio_fields": ["PARCEL_NUMBER", "APN10", "APN"],
    },
    "san diego": {
        # San Diego County — CA statewide parcel layer for lot size + APN.
        # Zoning via City of San Diego citywide zoning layer (point-in-polygon).
        # Verified 2026-05: ZONE_NAME field returns e.g. "RM-3-7" for Linda Vista.
        # Parcel layer has no address field — spatial query only.
        "parcel_url": (
            "https://services2.arcgis.com/zr3KAIbsRSUyARHG/arcgis/rest/services"
            "/CA_State_Parcels/FeatureServer/0"
        ),
        "zoning_url": (
            "https://services1.arcgis.com/eGSDp8lpKe5izqVc/arcgis/rest/services"
            "/San_Diego_Zoning/FeatureServer/0"
        ),
        "address_field": "",
        "zoning_fields": ["ZONE_NAME", "ZONE", "ZONING"],
        "desc_fields": ["ZONE_NAME"],
        "lot_fields": ["Shape__Area"],
        "lot_unit": "sqm",
        "folio_fields": ["PARCEL_APN"],
        # The statewide polygon area is unreliable for legal lot area — override
        # it with the County Assessor's recorded lot, keyed by APN, when available.
        "assessor_lot_url": _SD_ASSESSOR_PARCEL_URL,
    },
}

# sq meters → sq ft conversion (used when lot_unit = "sqm")
_SQM_TO_SQFT = 10.7639

# A lot value that comes from a polygon-area field is a GIS estimate of the lot,
# which can diverge from the recorded legal lot area; a named assessor field is
# authoritative. Used to stamp PropertyRecord.lot_size_source so a derived unit
# count built on a geometry estimate is not presented as firm.
_GEOMETRY_LOT_FIELDS = {"shape__area", "shape_area", "shape.starea()"}


def _is_geometry_lot_field(field: str) -> bool:
    """True when a lot field is a polygon-area field (a GIS estimate, not legal)."""
    return field.strip().lower() in _GEOMETRY_LOT_FIELDS


# ---------------------------------------------------------------------------
# CA statewide parcel layer (fallback for counties without a specific config)
#
# Maintained by the CA Strategic Growth Council / ICE; covers all 58 counties.
# Fields: PARCEL_APN, SITE_ADDR, SITE_CITY, Shape__Area (sq meters, EPSG:3310)
# Verified 2026-05: point-in-polygon works with inSR=4326 for Bay Area counties.
# Coverage gaps exist for some inland counties (Sacramento) — county configs
# handle those cases; this layer fills the gap for any county not yet configured.
# ---------------------------------------------------------------------------
_CA_STATEWIDE_PARCEL_URL = (
    "https://services2.arcgis.com/zr3KAIbsRSUyARHG/arcgis/rest/services"
    "/CA_State_Parcels/FeatureServer/0/query"
)


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
            logger.info(
                "CaliforniaProvider: no county config for %r — trying statewide layer", county
            )
            record = await self._statewide_parcel(address, county, lat=lat, lng=lng)
            if record is not None:
                await self._enrich_marin_zoning(record, county, lat, lng)
                await self._enrich_marin_lot(record, county)
                return record
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
                "trying statewide layer",
                address,
                county,
            )
            record = await self._statewide_parcel(address, county, lat=lat, lng=lng)

        if record is None:
            logger.info(
                "CaliforniaProvider: statewide layer returned nothing for %s (%s); "
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

        # --- 1b. Authoritative lot-size override ---
        # When the parcel layer's lot value is a GIS polygon estimate, replace it
        # with the county assessor's recorded legal lot area (keyed by APN). The
        # density rule keys off legal lot area, so trusting a polygon estimate can
        # produce a confidently-wrong unit count. If the assessor lookup misses,
        # the geometry value stays but its provenance flags it as unconfirmed.
        assessor_url = config.get("assessor_lot_url")
        if assessor_url and record.folio and record.lot_size_source != "assessor":
            assessor_lot, owner_name = await self._assessor_lot_sqft(assessor_url, record.folio)
            if assessor_lot and assessor_lot > 0:
                record.lot_size_sqft = assessor_lot
                record.lot_size_source = "assessor"
            if owner_name and not record.owner:
                record.owner = owner_name

        # --- 2. Zoning spatial query (if the parcel layer lacks zoning) ---
        if not record.zoning_code and config.get("zoning_url") and lat and lng:
            zoning_url = config["zoning_url"] + "/query"
            zoning_code, zoning_desc = await self._spatial_zoning(zoning_url, lat, lng, config)
            if zoning_code:
                record.zoning_code = zoning_code
                record.zoning_description = zoning_desc

        return record

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _enrich_marin_zoning(
        record: PropertyRecord,
        county: str,
        lat: float | None,
        lng: float | None,
    ) -> None:
        """Fill the parcel's zone from Marin's per-city zoning layers.

        The statewide parcel layer carries no zoning, so a Marin parcel returns
        empty ``zoning_code`` and the pipeline has to guess the zone. Marin
        County publishes a point-in-polygon zoning layer per city; resolve the
        real zone (e.g. Tiburon -> RO-2) so retrieval can target it.
        """
        if record.zoning_code or county.lower().strip() != "marin" or lat is None or lng is None:
            return
        try:
            from plotlot.property.marin_zoning import resolve_marin_zone

            code, desc = await resolve_marin_zone(record.municipality or "", lat, lng)
        except Exception as exc:
            logger.debug("Marin zoning enrichment failed: %s", exc)
            return
        if code:
            record.zoning_code = code
            if desc:
                record.zoning_description = desc

    @staticmethod
    async def _enrich_marin_lot(record: PropertyRecord, county: str) -> None:
        """Override the coarse statewide lot area with Marin's parcel fabric.

        The statewide layer under-estimates Marin lots (416 Richardson St:
        765 sqft statewide vs 1,162 sqft in the county fabric), which would build
        the by-right count on a wrong input. Marin County's own parcel layer is
        the authoritative cadastral boundary; stamp ``lot_size_source="assessor"``
        so the count is treated as firm, not a provisional GIS estimate (the SD
        path likewise labels the assessor parcel's own geometry area "assessor").
        """
        if (
            county.lower().strip() != "marin"
            or not record.folio
            or record.lot_size_source == "assessor"
        ):
            return
        try:
            from plotlot.property.marin_lot import resolve_marin_lot_sqft

            lot = await resolve_marin_lot_sqft(record.folio)
        except Exception as exc:
            logger.debug("Marin lot enrichment failed: %s", exc)
            return
        if lot and lot > 0:
            record.lot_size_sqft = lot
            record.lot_size_source = "assessor"

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
            out_fields = config.get("spatial_out_fields", "*")
            features = await spatial_query(url, lat, lng, out_fields=out_fields)
            if not features:
                return None
            return self._parse_feature(features[0], config, county)
        except Exception as exc:
            logger.debug("CaliforniaProvider spatial parcel failed (%s): %s", url, exc)
            return None

    async def _assessor_lot_sqft(self, assessor_url: str, apn: str) -> tuple[float | None, str]:
        """Authoritative legal lot area (sqft) + owner name for an APN from a county assessor layer.

        Returns ``(lot_sqft, owner_name)``. ``lot_sqft`` is ``None`` on any miss
        or failure — the caller keeps the geometry-derived estimate but flags it
        as unconfirmed, never silently substituting a guess (fail loud, per the
        anti-hallucination doctrine). ``owner_name`` is empty ``""`` on miss.
        """
        apn_digits = re.sub(r"\D", "", apn or "")
        if len(apn_digits) < 8:
            return None, ""
        params = {
            "where": f"APN='{apn_digits}'",
            "outFields": "ACREAGE,Shape.STArea(),OWN_NAME1",
            "returnGeometry": "false",
            "f": "json",
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(assessor_url + "/query", params=params)
                resp.raise_for_status()
                features = resp.json().get("features", [])
            if not features:
                return None, ""
            attrs = features[0].get("attributes", {})
            # Return owner name if present
            owner = str(attrs.get("OWN_NAME1") or "").strip()
            # Prefer the recorded ACREAGE (the legal figure); fall back to the
            # assessor parcel's own geometry area (State Plane US-ft → sqft).
            acreage = safe_float(attrs.get("ACREAGE"))
            if acreage > 0:
                return acreage * 43_560, owner
            st_area = safe_float(attrs.get("Shape.STArea()"))
            if st_area > 0:
                return st_area, owner
            return None, owner
        except Exception as exc:
            logger.debug("Assessor lot lookup failed for APN %s: %s", apn, exc)
            return None, ""

    async def _address_parcel(
        self,
        url: str,
        address: str,
        config: dict,
        county: str,
    ) -> PropertyRecord | None:
        """Address LIKE query against the parcel layer."""
        addr_field = config["address_field"]
        if not addr_field:
            # Layer has no address field (e.g. Santa Clara regional layer) — skip.
            return None
        normalized = normalize_address(address)
        # Try full normalized address first, then house-number + first street token
        where_clauses = [
            f"UPPER({addr_field}) LIKE '%{_escape_where(normalized)}%'",
        ]
        tokens = normalized.split()
        if len(tokens) >= 2:
            short = " ".join(tokens[:2])
            where_clauses.append(f"UPPER({addr_field}) LIKE '%{_escape_where(short)}%'")

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
        addr_field = config["address_field"]
        # Build composite address from SITUS_* fields when no single address field exists
        if not addr_field and attrs.get("SITUS_HOUSE_NUMBER"):
            parts = [
                str(attrs.get("SITUS_HOUSE_NUMBER") or "").strip(),
                str(attrs.get("SITUS_STREET_DIRECTION") or "").strip(),
                str(attrs.get("SITUS_STREET_NAME") or "").strip(),
                str(attrs.get("SITUS_STREET_TYPE") or "").strip(),
            ]
            address_val = " ".join(p for p in parts if p)
        else:
            address_val = str(attrs.get(addr_field) or "") if addr_field else ""
        zoning_code, zoning_desc = self._extract_zoning(attrs, config)

        lot_field, lot_value = self._first_value_field(attrs, config["lot_fields"])
        raw_lot = safe_float(lot_value)
        # Provenance: a polygon-area field (Shape__Area / Shape.STArea()) is a GIS
        # estimate of the lot that can diverge from the recorded legal lot area; a
        # named assessor field (ACREAGE, LOTSIZE, AC, LANDAREA) is authoritative.
        lot_source = "geometry" if _is_geometry_lot_field(lot_field) else "assessor"
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

        # Owner — field names vary by county (confirmed from schema probes)
        owner = str(
            attrs.get("OWNER")  # Sacramento, Contra Costa
            or attrs.get("Owner")  # Contra Costa alternate
            or attrs.get("NAME")  # Sacramento alternate
            or attrs.get("OWNER_NAME")
            or attrs.get("TAXPAYER")
            or ""
        )
        # Municipality — field names vary by county
        municipality = str(
            attrs.get("SITUS_CITY_NAME")  # Mountain View parcel service
            or attrs.get("PARCITY")  # Santa Clara regional layer
            or attrs.get("SitusCity")  # Alameda
            or attrs.get("SITUS_CITY")  # San Mateo
            or attrs.get("City")  # Contra Costa
            or attrs.get("CITY")  # Sacramento
            or attrs.get("MUNICIPALITY")
            or ""
        )
        year_built = int(
            safe_float(
                attrs.get("YEARBUILT")  # Santa Clara regional layer
                or attrs.get("YEAR_BUILT")
                or attrs.get("YR_BUILT")
                or 0
            )
        )
        assessed = safe_float(
            attrs.get("TotalNetValue")  # Alameda
            or attrs.get("Land")  # Alameda land value fallback
            or attrs.get("ASSESSED_VALUE")
            or attrs.get("ASSESSED_VAL")
            or attrs.get("TOTAL_VALUE")
            or 0
        )
        building_sqft = safe_float(
            attrs.get("BUILDING_SQFT") or attrs.get("BLDG_SQFT") or attrs.get("LIVING_SQFT") or 0
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
            lot_size_source=lot_source if lot_sqft > 0 else "",
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
        return CaliforniaProvider._first_value_field(attrs, fields)[1]

    @staticmethod
    def _first_value_field(attrs: dict, fields: list[str]) -> tuple[str, object]:
        """Return ``(field_name, value)`` of the first non-empty field in `fields`."""
        for f in fields:
            val = attrs.get(f)
            if val is not None and str(val).strip() not in ("", "None", "null"):
                return f, val
        return "", ""

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

    async def _statewide_parcel(
        self,
        address: str,
        county: str,
        *,
        lat: float | None,
        lng: float | None,
    ) -> PropertyRecord | None:
        """Query the CA statewide parcel layer (all 58 counties).

        Fields returned: PARCEL_APN, SITE_ADDR, SITE_CITY, Shape__Area (sq meters).
        Spatial query requires lat/lng; address fallback uses SITE_ADDR LIKE.
        """
        out_fields = "PARCEL_APN,SITE_ADDR,SITE_CITY,Shape__Area"

        # --- spatial first ---
        if lat is not None and lng is not None:
            try:
                features = await spatial_query(
                    _CA_STATEWIDE_PARCEL_URL, lat, lng, out_fields=out_fields
                )
                if features:
                    return self._parse_statewide_feature(features[0], county)
            except Exception as exc:
                logger.debug("CaliforniaProvider statewide spatial failed: %s", exc)

        # --- address LIKE fallback ---
        normalized = normalize_address(address)
        tokens = normalized.split()
        where_clauses = [f"UPPER(SITE_ADDR) LIKE '%{_escape_where(normalized)}%'"]
        if len(tokens) >= 2:
            short = " ".join(tokens[:2])
            where_clauses.append(f"UPPER(SITE_ADDR) LIKE '%{_escape_where(short)}%'")

        params_base = {
            "outFields": out_fields,
            "returnGeometry": "false",
            "f": "json",
            "resultRecordCount": "5",
        }
        for where in where_clauses:
            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    resp = await client.get(
                        _CA_STATEWIDE_PARCEL_URL, params={**params_base, "where": where}
                    )
                    resp.raise_for_status()
                    features = resp.json().get("features", [])
                if features:
                    return self._parse_statewide_feature(features[0], county)
            except Exception as exc:
                logger.debug(
                    "CaliforniaProvider statewide address query failed (%s): %s",
                    where[:80],
                    exc,
                )

        logger.info(
            "CaliforniaProvider: statewide layer returned nothing for %s (%s)", address, county
        )
        return None

    @staticmethod
    def _parse_statewide_feature(feature: dict, county: str) -> PropertyRecord:
        """Convert a CA statewide parcel feature to PropertyRecord.

        Shape__Area is in sq meters (EPSG:3310 Albers Equal Area).
        Zoning is not available from this layer — left empty for ordinance search.
        """
        attrs = feature.get("attributes", {})
        folio = str(attrs.get("PARCEL_APN") or "")
        address_val = str(attrs.get("SITE_ADDR") or "")
        municipality = str(attrs.get("SITE_CITY") or "")
        raw_area = safe_float(attrs.get("Shape__Area"))
        lot_sqft = raw_area * _SQM_TO_SQFT if raw_area > 0 else 0.0

        geom = feature.get("geometry") or {}
        feat_lat: float | None = geom.get("y")
        feat_lng: float | None = geom.get("x")

        return PropertyRecord(
            folio=folio,
            address=address_val,
            municipality=municipality,
            county=county.title(),
            zoning_code="",  # not available; ordinance search resolves zoning
            zoning_description="",
            lot_size_sqft=lot_sqft,
            lot_size_source="geometry" if lot_sqft > 0 else "",
            lat=feat_lat,
            lng=feat_lng,
        )

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
