"""Broward County PropertyProvider.

Wraps the existing ArcGIS REST API calls for the Broward County Property
Appraiser (BCPA MapServer), parcels layer for lot size, and spatial
zoning query.
"""

from __future__ import annotations

from plotlot.core.types import PropertyRecord
from plotlot.property.base import PropertyProvider
from plotlot.retrieval.property import _lookup_broward


class BrowardProvider(PropertyProvider):
    """Property lookup via Broward County ArcGIS MapServer (BCPA)."""

    async def lookup(
        self,
        address: str,
        county: str,
        *,
        lat: float | None = None,
        lng: float | None = None,
    ) -> PropertyRecord | None:
        return await _lookup_broward(address, lat, lng)
