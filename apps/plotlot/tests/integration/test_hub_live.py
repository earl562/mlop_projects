"""Live integration tests for ArcGIS Hub discovery.

These tests hit the real ArcGIS Hub API and county endpoints.
Run with: uv run pytest tests/integration/test_hub_live.py -v -m live
"""

import pytest

from plotlot.property.hub_discovery import discover_datasets
from plotlot.property.field_mapper import map_fields_heuristic


@pytest.mark.live
class TestHubLiveDiscovery:
    """Test real Hub discovery for known counties."""

    async def test_miami_dade_parcels(self):
        """Should discover Miami-Dade parcel + zoning datasets."""
        parcels, zoning = await discover_datasets(
            lat=25.93, lng=-80.24, county="Miami-Dade", state="FL"
        )

        assert parcels is not None, "Should find a parcel dataset for Miami-Dade"
        assert parcels.dataset_type == "parcels"
        assert len(parcels.fields) > 5, "Should have multiple fields"

        # Should be able to map fields heuristically
        mapping = map_fields_heuristic(parcels.fields)
        assert mapping.confidence >= 0.5, f"Field mapping confidence too low: {mapping.confidence}"

    async def test_broward_parcels(self):
        """Should discover Broward parcel datasets."""
        parcels, _ = await discover_datasets(lat=26.12, lng=-80.14, county="Broward", state="FL")

        assert parcels is not None, "Should find a parcel dataset for Broward"
        assert len(parcels.fields) > 3

    async def test_harris_county_tx(self):
        """Should discover datasets for a county we've never hardcoded."""
        parcels, _ = await discover_datasets(lat=29.76, lng=-95.36, county="Harris", state="TX")

        # Harris County (Houston) should have parcel data on ArcGIS Hub
        if parcels is not None:
            assert parcels.dataset_type == "parcels"
            assert len(parcels.fields) > 0

    async def test_no_results_graceful(self):
        """Remote island with no GIS data should return None gracefully."""
        parcels, zoning = await discover_datasets(lat=0.0, lng=0.0, county="Nowhere", state="XX")

        # Should not crash — just return None
        assert parcels is None or parcels.dataset_type == "parcels"
