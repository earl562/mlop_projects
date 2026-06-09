"""County GIS integration — real per-parcel zoning data from NC county ArcGIS portals.

Replaces lot-size-based zoning estimation with actual GIS queries by APN/address.
Fallback to estimate_zoning_district() when GIS data is unavailable.

Counties: Catawba, Lincoln, Gaston (NC)
Protocol: ArcGIS REST Feature Service (most NC counties use ESRI)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParcelGISData:
    apn: str
    county: str
    zoning: str = ""
    zoning_description: str = ""
    acreage: float = 0.0
    land_use_code: str = ""
    owner_name: str = ""
    flood_zone: str = ""
    sewer_available: bool = False
    water_available: bool = False
    source: str = "estimated"  # "gis" or "estimated"
    raw_data: dict[str, Any] = field(default_factory=dict)


# ==========================================================================
# County GIS endpoints (ArcGIS REST Feature Services)
# ==========================================================================

COUNTY_GIS_CONFIG: dict[str, dict[str, str]] = {
    "Catawba": {
        "name": "Catawba County GIS",
        "parcel_service": "https://gis.catawbacountync.gov/arcgis/rest/services/Parcels/FeatureServer/0",
        "zoning_service": "https://gis.catawbacountync.gov/arcgis/rest/services/Zoning/FeatureServer/0",
        "apn_field": "PIN",
        "zoning_field": "ZONING",
        "gis_portal": "https://gis.catawbacountync.gov/",
    },
    "Lincoln": {
        "name": "Lincoln County GIS",
        "parcel_service": "https://gis.lincolncounty.org/arcgis/rest/services/Parcels/FeatureServer/0",
        "zoning_service": "https://gis.lincolncounty.org/arcgis/rest/services/Zoning/FeatureServer/0",
        "apn_field": "PARCEL_ID",
        "zoning_field": "ZONING",
        "gis_portal": "https://gis.lincolncounty.org/",
    },
    "Gaston": {
        "name": "Gaston County GIS",
        "parcel_service": "https://gis.gastongov.com/arcgis/rest/services/Parcels/FeatureServer/0",
        "zoning_service": "https://gis.gastongov.com/arcgis/rest/services/Zoning/FeatureServer/0",
        "apn_field": "PARCELID",
        "zoning_field": "ZONING",
        "gis_portal": "https://gis.gastongov.com/",
    },
}


class CountyGISClient:
    """Query county GIS systems for per-parcel zoning and property data."""

    def __init__(self, county: str):
        self._county = county
        self._config = COUNTY_GIS_CONFIG.get(county, COUNTY_GIS_CONFIG["Lincoln"])
        self._cache: dict[str, ParcelGISData] = {}

    async def query_parcel(self, apn: str) -> ParcelGISData:
        """Query parcel zoning by APN. Falls back to estimation if API fails."""
        if apn in self._cache:
            return self._cache[apn]
        data = await self._query_arcgis(apn)
        self._cache[apn] = data
        return data

    async def _query_arcgis(self, apn: str) -> ParcelGISData:
        """Query ArcGIS REST Feature Service for parcel data."""
        try:
            import httpx
            service_url = self._config["parcel_service"]
            apn_field = self._config["apn_field"]
            query_url = f"{service_url}/query"
            params = {
                "where": f"{apn_field}='{apn}'",
                "outFields": "*",
                "returnGeometry": "false",
                "f": "json",
            }
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(query_url, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    features = data.get("features", [])
                    if features:
                        attrs = features[0].get("attributes", {})
                        zoning_field = self._config["zoning_field"]
                        result = ParcelGISData(
                            apn=apn,
                            county=self._county,
                            zoning=attrs.get(zoning_field, ""),
                            zoning_description="",
                            acreage=float(attrs.get("ACREAGE", attrs.get("ACRES", 0)) or 0),
                            land_use_code=str(attrs.get("LANDUSE", attrs.get("LU_CODE", ""))),
                            owner_name=str(attrs.get("OWNER", attrs.get("OWNER_NAME", ""))),
                            source="gis",
                            raw_data=attrs,
                        )
                        self._try_zoning_service(result)
                        return result
        except Exception:
            pass
        return self._estimated_fallback(apn)

    def _try_zoning_service(self, result: ParcelGISData) -> None:
        """Enrich with zoning description from zoning layer."""
        pass  # Async enrichment deferred — use synchronous validate_zoning_for_lead() for now

    def _estimated_fallback(self, apn: str) -> ParcelGISData:
        from plotlot.harness.county_zoning import estimate_zoning_district
        return ParcelGISData(
            apn=apn,
            county=self._county,
            zoning=estimate_zoning_district(10000, self._county),
            source="estimated",
        )

    def get_portal_url(self) -> str:
        return self._config["gis_portal"]


# Convenience: get zoning for any county by APN
async def lookup_parcel_zoning(apn: str, county: str) -> ParcelGISData:
    client = CountyGISClient(county)
    return await client.query_parcel(apn)


def validate_zoning_for_lead(apn: str, county: str, lot_size_sqft: float) -> dict[str, Any]:
    """Synchronous fallback — validates zoning using county defaults + lot size.

    Returns zoning parameters that can be used immediately without awaiting GIS.
    Includes a flag indicating whether this is estimated or confirmed.
    """
    from plotlot.harness.county_zoning import estimate_unit_potential
    zoning = estimate_unit_potential(lot_size_sqft, county)
    zoning["source"] = "estimated"
    zoning["needs_gis_verification"] = True
    zoning["gis_portal"] = COUNTY_GIS_CONFIG.get(county, {}).get("gis_portal", "")
    return zoning
