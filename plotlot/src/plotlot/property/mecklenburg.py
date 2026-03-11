"""Mecklenburg County (Charlotte NC metro) property provider.

Uses the Mecklenburg County GIS REST API for property lookups.
Covers: Charlotte, Huntersville, Cornelius, Davidson, Matthews, Mint Hill,
Pineville, and other Charlotte metro municipalities within Mecklenburg County.
"""

from __future__ import annotations

import logging

import httpx

from plotlot.core.types import PropertyRecord
from plotlot.property.base import PropertyProvider

logger = logging.getLogger(__name__)

MECKLENBURG_PARCEL_URL = (
    "https://gis.charlottenc.gov/arcgis/rest/services/Common/DynamicMecklenburg/MapServer/61/query"
)


class MecklenburgProvider(PropertyProvider):
    """Property lookup for Mecklenburg County, NC."""

    county = "mecklenburg"

    async def lookup(
        self,
        address: str,
        county: str,
        *,
        lat: float | None = None,
        lng: float | None = None,
    ) -> PropertyRecord | None:
        """Look up property record from Mecklenburg County GIS.

        Tries spatial query first (lat/lng), falls back to address search.
        """
        try:
            # Try spatial query first if coordinates are available
            if lat is not None and lng is not None:
                record = await self._spatial_query(lat, lng)
                if record:
                    return record

            # Fall back to address search
            return await self._address_query(address)
        except Exception as e:
            logger.warning("Mecklenburg property lookup failed: %s", e)
            return None

    async def _spatial_query(self, lat: float, lng: float) -> PropertyRecord | None:
        """Query parcels by lat/lng point."""
        params = {
            "geometry": f"{lng},{lat}",
            "geometryType": "esriGeometryPoint",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "*",
            "returnGeometry": "false",
            "f": "json",
            "inSR": "4326",
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(MECKLENBURG_PARCEL_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        features = data.get("features", [])
        if not features:
            return None

        return self._parse_feature(features[0].get("attributes", {}))

    async def _address_query(self, address: str) -> PropertyRecord | None:
        """Query parcels by address string."""
        # Clean address for query — take street address before first comma
        clean_addr = address.split(",")[0].strip().upper()

        params = {
            "where": f"UPPER(SITE_ADDR) LIKE '%{clean_addr}%'",
            "outFields": "*",
            "returnGeometry": "false",
            "f": "json",
            "resultRecordCount": 1,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(MECKLENBURG_PARCEL_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        features = data.get("features", [])
        if not features:
            return None

        return self._parse_feature(features[0].get("attributes", {}))

    def _parse_feature(self, attrs: dict) -> PropertyRecord:
        """Parse ArcGIS feature attributes into PropertyRecord.

        Mecklenburg field names vary across layers — handle common patterns.
        """
        lot_size = float(attrs.get("SHAPE_Area", 0) or attrs.get("LAND_AREA", 0) or 0)
        # Convert from sq meters to sq feet if needed (ArcGIS often returns sq meters)
        if lot_size > 0 and lot_size < 50000:  # likely sq meters
            lot_size *= 10.764

        return PropertyRecord(
            folio=str(attrs.get("PID", "") or attrs.get("PARCEL_ID", "")),
            address=str(attrs.get("SITE_ADDR", "") or attrs.get("ADDRESS", "")),
            municipality=str(attrs.get("CITY", "") or attrs.get("JURIS", "")),
            county="Mecklenburg",
            owner=str(attrs.get("OWNER_NAME", "") or attrs.get("OWNER", "")),
            zoning_code=str(attrs.get("ZONE_CLASS", "") or attrs.get("ZONING", "")),
            zoning_description=str(attrs.get("ZONE_DESC", "") or ""),
            land_use_code=str(attrs.get("LAND_USE_CD", "") or attrs.get("LU_CODE", "")),
            land_use_description=str(attrs.get("LAND_USE", "") or attrs.get("LU_DESC", "")),
            lot_size_sqft=lot_size,
            assessed_value=float(
                attrs.get("TOTAL_VALUE", 0) or attrs.get("ASSESSED_VALUE", 0) or 0
            ),
            market_value=float(attrs.get("MARKET_VALUE", 0) or attrs.get("TOTAL_VALUE", 0) or 0),
            year_built=int(attrs.get("YEAR_BUILT", 0) or 0),
            building_area_sqft=float(attrs.get("BLDG_SQFT", 0) or attrs.get("HEATED_AREA", 0) or 0),
        )
