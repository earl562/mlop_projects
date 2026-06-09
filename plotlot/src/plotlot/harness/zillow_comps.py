"""Zillow comps integration via Zillapi REST API.

Per Zillapi (zillapi.com): 11 REST endpoints, Python-ready with httpx.
Free tier: 100 credits at signup. $5/month for 1K credits.

Endpoints used:
- /v1/properties/by-address → property lookup
- /v1/properties/{zpid}/zestimate → Zestimate + rent Zestimate + tax assessed
- /v1/properties/{zpid}/nearby → comparable nearby listings
- /v1/search → search by bbox for recently sold homes (new build comps)

Fills the critical gap: new build comps currently = 0 because our dataset
is vacant land only. This module provides real MLS comp data.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


ZILLAPI_BASE = "https://api.zillapi.com/v1"


@dataclass
class ZillowProperty:
    zpid: int = 0
    address: str = ""
    price: float = 0.0
    zestimate: float = 0.0
    rent_zestimate: float = 0.0
    tax_assessed: float = 0.0
    bedrooms: int = 0
    bathrooms: float = 0.0
    living_area_sqft: float = 0.0
    lot_size_sqft: float = 0.0
    year_built: int = 0
    last_sold_price: float = 0.0
    last_sold_date: str = ""
    home_type: str = ""
    status: str = ""  # FOR_SALE, RECENTLY_SOLD
    days_on_zillow: int = 0
    price_per_sqft: float = 0.0

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "ZillowProperty":
        addr = data.get("address", {})
        full_addr = f"{addr.get('streetAddress','')}, {addr.get('city','')}, {addr.get('state','')} {addr.get('zipcode','')}"
        return cls(
            zpid=data.get("zpid", 0),
            address=full_addr,
            price=float(data.get("price", 0) or 0),
            zestimate=float(data.get("zestimate", 0) or 0),
            rent_zestimate=float(data.get("rentZestimate", 0) or 0),
            tax_assessed=float(data.get("taxAssessedValue", 0) or 0),
            bedrooms=int(data.get("bedrooms", 0) or 0),
            bathrooms=float(data.get("bathrooms", 0) or 0),
            living_area_sqft=float(data.get("livingArea", 0) or 0),
            lot_size_sqft=float(data.get("lotSize", 0) or 0),
            year_built=int(data.get("yearBuilt", 0) or 0),
            last_sold_price=float(data.get("lastSoldPrice", 0) or 0),
            last_sold_date=str(data.get("lastSoldDate", "")),
            home_type=str(data.get("homeType", "")),
            status=str(data.get("homeStatus", "")),
            days_on_zillow=int(data.get("daysOnZillow", 0) or 0),
            price_per_sqft=float(data.get("pricePerSqft", 0) or 0),
        )


class ZillowCompsClient:
    """Query Zillapi for property data and comparable sales."""

    def __init__(self, api_key: str | None = None):
        self._key = api_key or os.environ.get("ZILLAPI_KEY", "")
        self._headers = {"Authorization": f"Bearer {self._key}"} if self._key else {}

    @property
    def configured(self) -> bool:
        return bool(self._key)

    async def lookup_property(self, address: str) -> ZillowProperty | None:
        """Look up a property by address. Returns full record with Zestimate."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(f"{ZILLAPI_BASE}/properties/by-address", params={"address": address}, headers=self._headers)
                if resp.status_code == 200:
                    data = resp.json().get("data", {})
                    return ZillowProperty.from_api(data)
        except Exception:
            pass
        return None

    async def get_zestimate(self, zpid: int) -> dict[str, Any]:
        """Get Zestimate, rent Zestimate, tax assessed, last sold."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{ZILLAPI_BASE}/properties/{zpid}/zestimate", headers=self._headers)
                if resp.status_code == 200:
                    return resp.json().get("data", {})
        except Exception:
            pass
        return {}

    async def get_nearby_comps(self, zpid: int, limit: int = 10) -> list[dict[str, Any]]:
        """Get nearby comparable properties (active + recently sold)."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(f"{ZILLAPI_BASE}/properties/{zpid}/nearby", headers=self._headers)
                if resp.status_code == 200:
                    return resp.json().get("data", [])[:limit]
        except Exception:
            pass
        return []

    async def search_recently_sold(self, bbox: dict[str, float], months: int = 6, limit: int = 20) -> list[dict[str, Any]]:
        """Search for recently sold homes in a geographic bounding box."""
        try:
            import httpx
            body = {
                "filters": {
                    "status": "recently_sold",
                    "bbox": bbox,
                    "daysOnZillow": str(months * 30),
                },
                "extractionMethod": "PAGINATION",
                "maxItems": limit,
                "async": False,
            }
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(f"{ZILLAPI_BASE}/search", json=body, headers=self._headers)
                if resp.status_code == 200:
                    return resp.json().get("data", [])[:limit]
        except Exception:
            pass
        return []

    def bbox_from_coords(self, lat: float, lng: float, radius_miles: float = 3.0) -> dict[str, float]:
        """Create a bounding box around a coordinate."""
        delta = radius_miles / 69.0
        return {"west": round(lng - delta, 4), "south": round(lat - delta, 4), "east": round(lng + delta, 4), "north": round(lat + delta, 4)}

    async def get_comps_for_parcel(self, address: str, lat: float = 0, lng: float = 0, radius_miles: float = 3.0) -> dict[str, Any]:
        """Full comp analysis: lookup property + nearby comps + recently sold."""
        result: dict[str, Any] = {"property": None, "nearby_count": 0, "nearby_comps": [], "recently_sold_count": 0, "recently_sold": []}
        prop = await self.lookup_property(address)
        if prop:
            result["property"] = {
                "zpid": prop.zpid, "address": prop.address, "zestimate": prop.zestimate,
                "last_sold": prop.last_sold_price, "year_built": prop.year_built,
                "lot_sqft": prop.lot_size_sqft, "living_sqft": prop.living_area_sqft,
                "beds": prop.bedrooms, "baths": prop.bathrooms,
            }
            nearby = await self.get_nearby_comps(prop.zpid)
            result["nearby_count"] = len(nearby)
            result["nearby_comps"] = [{"address": n.get("address", {}).get("streetAddress", ""), "price": n.get("price"), "zestimate": n.get("zestimate"), "sqft": n.get("livingArea"), "beds": n.get("bedrooms"), "status": n.get("homeStatus")} for n in nearby[:5]]
        if lat and lng:
            bbox = self.bbox_from_coords(lat, lng, radius_miles)
            sold = await self.search_recently_sold(bbox)
            result["recently_sold_count"] = len(sold)
            result["recently_sold"] = [{"address": s.get("address", {}).get("streetAddress", ""), "price": s.get("price"), "sqft": s.get("livingArea"), "sold_date": s.get("dateSold"), "zestimate": s.get("zestimate")} for s in sold[:5]]
        return result
