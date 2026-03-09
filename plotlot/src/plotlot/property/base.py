"""Abstract PropertyProvider interface.

Each county implements this interface with its own ArcGIS API calls.
The registry maps county names to concrete providers so adding a new
county (e.g., Charlotte/Mecklenburg) is a single class + registration.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from plotlot.core.types import PropertyRecord


class PropertyProvider(ABC):
    """Contract that every county property-lookup provider must satisfy."""

    @abstractmethod
    async def lookup(
        self,
        address: str,
        county: str,
        *,
        lat: float | None = None,
        lng: float | None = None,
    ) -> PropertyRecord | None:
        """Look up a property record from the county Property Appraiser.

        Args:
            address: Full street address (may include city/state/zip).
            county: County name (e.g., "Miami-Dade").
            lat: Latitude from geocoding (used for spatial zoning queries).
            lng: Longitude from geocoding (used for spatial zoning queries).

        Returns:
            PropertyRecord with all available data, or None if not found.
        """
        ...
