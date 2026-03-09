"""Miami-Dade County PropertyProvider.

Wraps the existing ArcGIS REST API calls for the MDC Property Appraiser
and the two-layer municipal/unincorporated zoning spatial query.
"""

from __future__ import annotations

from plotlot.core.types import PropertyRecord
from plotlot.property.base import PropertyProvider
from plotlot.retrieval.property import _lookup_miami_dade


class MiamiDadeProvider(PropertyProvider):
    """Property lookup via Miami-Dade County ArcGIS FeatureServer."""

    async def lookup(
        self,
        address: str,
        county: str,
        *,
        lat: float | None = None,
        lng: float | None = None,
    ) -> PropertyRecord | None:
        return await _lookup_miami_dade(address, lat, lng)
