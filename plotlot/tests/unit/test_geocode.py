"""Tests for Geocodio address resolution."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from plotlot.retrieval.geocode import (
    geocode_address,
    address_to_municipality_key,
    county_to_key,
)


class TestAddressToMunicipalityKey:
    def test_simple_name(self):
        assert address_to_municipality_key("Miramar") == "miramar"

    def test_two_word_name(self):
        assert address_to_municipality_key("Fort Lauderdale") == "fort_lauderdale"

    def test_hyphenated_name(self):
        assert address_to_municipality_key("Miami-Dade") == "miami_dade"

    def test_extra_spaces(self):
        assert address_to_municipality_key("  Miami  Gardens  ") == "miami_gardens"


class TestCountyToKey:
    def test_simple_county(self):
        assert county_to_key("Broward") == "broward"

    def test_two_word_county(self):
        assert county_to_key("Palm Beach") == "palm_beach"

    def test_hyphenated_county(self):
        assert county_to_key("Miami-Dade") == "miami_dade"


class TestGeocodeAddress:
    @pytest.mark.asyncio
    async def test_successful_geocode(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {
                    "formatted_address": "7940 Plantation Blvd, Miramar, FL 33023",
                    "address_components": {
                        "city": "Miramar",
                        "county": "Broward County",
                    },
                    "location": {"lat": 25.977, "lng": -80.232},
                    "accuracy": 1.0,
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("plotlot.retrieval.geocode.httpx.AsyncClient", return_value=mock_client), \
             patch("plotlot.retrieval.geocode.settings") as mock_settings:
            mock_settings.geocodio_api_key = "test_key"
            result = await geocode_address("7940 Plantation Blvd, Miramar, FL")

        assert result is not None
        assert result["municipality"] == "Miramar"
        assert result["county"] == "Broward"
        assert result["lat"] == 25.977

    @pytest.mark.asyncio
    async def test_no_results(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("plotlot.retrieval.geocode.httpx.AsyncClient", return_value=mock_client), \
             patch("plotlot.retrieval.geocode.settings") as mock_settings:
            mock_settings.geocodio_api_key = "test_key"
            result = await geocode_address("some invalid address xyz")

        assert result is None

    @pytest.mark.asyncio
    async def test_no_api_key(self):
        with patch("plotlot.retrieval.geocode.settings") as mock_settings:
            mock_settings.geocodio_api_key = ""
            result = await geocode_address("any address")

        assert result is None

    @pytest.mark.asyncio
    async def test_county_suffix_stripped(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {
                    "formatted_address": "171 NE 209th Ter, Miami, FL 33179",
                    "address_components": {
                        "city": "Miami Gardens",
                        "county": "Miami-Dade County",
                    },
                    "location": {"lat": 25.949, "lng": -80.179},
                    "accuracy": 1.0,
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("plotlot.retrieval.geocode.httpx.AsyncClient", return_value=mock_client), \
             patch("plotlot.retrieval.geocode.settings") as mock_settings:
            mock_settings.geocodio_api_key = "test_key"
            result = await geocode_address("171 NE 209th Ter, Miami, FL 33179")

        assert result["county"] == "Miami-Dade"
        assert result["municipality"] == "Miami Gardens"
