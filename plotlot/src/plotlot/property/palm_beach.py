"""Palm Beach County PropertyProvider.

Wraps the existing ArcGIS REST API calls for the Palm Beach County
Property Appraiser FeatureServer and spatial zoning query.
"""

from __future__ import annotations

from plotlot.core.types import PropertyRecord
from plotlot.property.base import PropertyProvider
from plotlot.retrieval.property import _lookup_palm_beach


class PalmBeachProvider(PropertyProvider):
    """Property lookup via Palm Beach County ArcGIS FeatureServer."""

    async def lookup(
        self,
        address: str,
        county: str,
        *,
        lat: float | None = None,
        lng: float | None = None,
    ) -> PropertyRecord | None:
        return await _lookup_palm_beach(address, lat, lng)
