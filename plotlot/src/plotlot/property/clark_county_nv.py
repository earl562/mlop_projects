"""Clark County, Nevada property provider.

Uses maps.clarkcountynv.gov ArcGIS services — the county's own GIS server —
which is NOT indexed on ArcGIS Hub. The UniversalProvider (Hub-based discovery)
therefore cannot find it; this dedicated provider is necessary.

Endpoints
---------
Parcels (spatial — returns APN, lot area):
  maps.clarkcountynv.gov/arcgis/rest/services/Assessor/LandApp/MapServer/9

Las Vegas city zoning (Layer 7) — incorporated city within Clark County:
  maps.clarkcountynv.gov/arcgis/rest/services/OpenData/PlanningandZoning/MapServer/7

Clark County unincorporated zoning (Layer 11):
  maps.clarkcountynv.gov/arcgis/rest/services/OpenData/PlanningandZoning/MapServer/11
"""

from __future__ import annotations

import logging

import httpx

from plotlot.core.types import PropertyRecord
from plotlot.property.base import PropertyProvider

logger = logging.getLogger(__name__)

_BASE = "https://maps.clarkcountynv.gov/arcgis/rest/services"

# Parcel fabric — spatial lookup returns APN + acreage
_PARCELS_URL = f"{_BASE}/Assessor/LandApp/MapServer/9/query"

# City of Las Vegas zoning (incorporated — covers most of "Las Vegas" addresses)
_LV_ZONING_URL = f"{_BASE}/OpenData/PlanningandZoning/MapServer/7/query"

# Unincorporated Clark County zoning (covers Henderson, North Las Vegas, etc.)
_CC_ZONING_URL = f"{_BASE}/OpenData/PlanningandZoning/MapServer/11/query"


class ClarkCountyNVProvider(PropertyProvider):
    """PropertyProvider for Clark County, Nevada (Las Vegas metro)."""

    async def lookup(
        self,
        address: str,
        county: str,
        *,
        lat: float | None = None,
        lng: float | None = None,
        state: str = "",
    ) -> PropertyRecord | None:
        if lat is None or lng is None:
            logger.warning("ClarkCountyNVProvider requires lat/lng")
            return None

        # Step 1: Get parcel info via spatial query (APN + lot area)
        apn, lot_sqft = await _spatial_parcel(lat, lng)

        # Step 2: Resolve zoning AND jurisdiction by which layer the parcel point
        # actually intersects. The mailing city ("Las Vegas") is NOT the zoning
        # authority — most "Las Vegas, NV" addresses are unincorporated land zoned
        # by Clark County. Whichever layer returns a polygon IS the authority:
        #   • City of Las Vegas layer (7) hits → incorporated → "Las Vegas"
        #   • Clark County layer (11) hits      → unincorporated → "Clark County"
        # The label drives downstream ordinance ingest/search, so it must match the
        # body that actually adopted the code. "Clark County" is on Municode (Title
        # 30); the City of Las Vegas is not — so this routing is what makes
        # unincorporated parcels analyzable instead of dead-ending under "Las Vegas".
        lv_code, lv_desc = await _spatial_zoning(_LV_ZONING_URL, lat, lng)

        # The LV layer returns ZNCLASS=CITY (or no feature) for parcels outside the
        # incorporated city; a real code here means the parcel IS inside the city.
        if lv_code and lv_code.upper() not in ("", "CITY"):
            zoning_code, zoning_desc = lv_code, lv_desc
            municipality, zoning_layer_url = "Las Vegas", _LV_ZONING_URL
        else:
            cc_code, cc_desc = await _spatial_zoning(_CC_ZONING_URL, lat, lng)
            zoning_code, zoning_desc = cc_code, cc_desc
            municipality, zoning_layer_url = "Clark County", _CC_ZONING_URL

        if not apn and not zoning_code:
            logger.warning("No parcel or zoning data found at (%.4f, %.4f)", lat, lng)
            return None

        record = PropertyRecord(county="Clark")
        record.folio = apn
        record.municipality = municipality
        record.lat = lat
        record.lng = lng
        record.lot_size_sqft = lot_sqft
        record.zoning_code = zoning_code
        record.zoning_description = zoning_desc
        record.zoning_layer_url = zoning_layer_url.rsplit("/query", 1)[0]

        logger.info(
            "Clark County NV: jurisdiction=%s apn=%s zoning=%s lot=%.0f sqft",
            municipality,
            apn or "N/A",
            zoning_code or "N/A",
            lot_sqft,
        )
        return record


async def _spatial_parcel(lat: float, lng: float) -> tuple[str, float]:
    """Return (APN, lot_sqft) from LandApp Layer 9 spatial query."""
    params = {
        "geometry": f"{lng},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "APN,ASSR_ACRES,CALC_ACRES",
        "f": "json",
        "returnGeometry": "false",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(_PARCELS_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        features = data.get("features", [])
        if not features:
            return "", 0.0

        attrs = features[0].get("attributes", {})
        apn = str(attrs.get("APN") or "").strip()
        acres = float(attrs.get("ASSR_ACRES") or attrs.get("CALC_ACRES") or 0)
        return apn, round(acres * 43560, 1)
    except Exception:
        logger.warning("Clark County parcel spatial query failed", exc_info=True)
        return "", 0.0


async def _spatial_zoning(url: str, lat: float, lng: float) -> tuple[str, str]:
    """Return (zoning_code, description) from a spatial query on a zoning layer."""
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
            return "", ""

        attrs = features[0].get("attributes", {})

        # Las Vegas layer uses ZONE + DESCRIPTIO
        # Clark County layer uses ZNCLASS + Description
        code = str(attrs.get("ZONE") or attrs.get("ZNCLASS") or "").strip()
        desc = str(attrs.get("DESCRIPTIO") or attrs.get("Description") or "").strip()
        return code, desc
    except Exception:
        logger.warning("Clark County zoning spatial query failed: %s", url, exc_info=True)
        return "", ""
