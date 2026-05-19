"""Tests for ArcGIS Hub dataset discovery."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from plotlot.property.hub_discovery import (
    _score_dataset,
    discover_datasets,
)


def _make_response(data: dict) -> MagicMock:
    """Create a mock httpx Response (sync .json(), sync .raise_for_status())."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = data
    return resp


class TestScoreDataset:
    """Test dataset scoring heuristic."""

    def test_parcel_fields_score_high(self):
        fields = ["FOLIO", "PARCEL_ID", "LOT_SIZE", "OWNER_NAME", "SITE_ADDR"]
        score = _score_dataset(fields, "County Parcels", "parcels")
        assert score > 5.0

    def test_zoning_fields_score_high(self):
        fields = ["ZONE_CODE", "ZONING", "DISTRICT", "ZONE_DESC"]
        score = _score_dataset(fields, "Zoning Districts", "zoning")
        assert score > 5.0

    def test_name_keywords_add_bonus(self):
        fields = ["FID", "SHAPE"]
        score_with_name = _score_dataset(fields, "Tax Parcel Data", "parcels")
        score_without = _score_dataset(fields, "Random Data", "parcels")
        assert score_with_name > score_without

    def test_empty_fields_score_zero(self):
        score = _score_dataset([], "Something", "parcels")
        assert score == 0.0

    def test_irrelevant_fields_score_low(self):
        fields = ["OBJECTID", "FID", "SHAPE_AREA", "SHAPE_LENGTH"]
        score = _score_dataset(fields, "Random Layer", "parcels")
        assert score < 2.0


class TestDiscoverDatasets:
    """Test Hub discovery integration (mocked HTTP)."""

    @pytest.fixture
    def hub_response(self):
        return {
            "data": [
                {
                    "id": "abc123",
                    "attributes": {
                        "name": "County Parcels",
                        "url": "https://example.com/arcgis/rest/services/Parcels/FeatureServer",
                    },
                }
            ]
        }

    @pytest.fixture
    def fields_response(self):
        return {
            "fields": [
                {"name": "FOLIO"},
                {"name": "SITE_ADDR"},
                {"name": "OWNER_NAME"},
                {"name": "LOT_SIZE"},
                {"name": "YEAR_BUILT"},
            ]
        }

    async def test_discover_returns_datasets(self, hub_response, fields_response):
        """Hub search + layer inspection → DatasetInfo."""
        layers_response = {
            "layers": [{"id": 0, "type": "Feature Layer", "name": "Parcels"}],
        }

        call_count = 0
        responses = [
            hub_response,  # 1. Hub search for parcels
            layers_response,  # 2. _find_best_layer (service root ?f=json)
            fields_response,  # 3. Layer fields fetch (/0?f=json)
            {"data": []},  # 4. Hub search for zoning (no results)
        ]

        async def mock_get(*args, **kwargs):
            nonlocal call_count
            idx = min(call_count, len(responses) - 1)
            call_count += 1
            return _make_response(responses[idx])

        # Each `async with httpx.AsyncClient(...)` creates a new context.
        mock_client = MagicMock()
        mock_client.get = mock_get

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_client)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("plotlot.property.hub_discovery.httpx.AsyncClient", return_value=ctx):
            parcels, zoning = await discover_datasets(25.93, -80.24, "Miami-Dade", "FL")

            assert parcels is not None
            assert parcels.dataset_type == "parcels"
            assert parcels.county == "Miami-Dade"

    async def test_discover_returns_none_on_no_results(self):
        """Hub returns empty → (None, None)."""

        async def mock_get(*args, **kwargs):
            return _make_response({"data": []})

        mock_client = AsyncMock()
        mock_client.get = mock_get

        with patch("plotlot.property.hub_discovery.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            parcels, zoning = await discover_datasets(40.0, -74.0, "Unknown", "XX")
            assert parcels is None
            assert zoning is None
