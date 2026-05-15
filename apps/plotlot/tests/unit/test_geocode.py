"""Tests for geocoding with Geocodio primary and Census Geocoder fallback."""

import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock

from plotlot.retrieval.geocode import (
    _census_geocode,
    geocode_address,
    address_to_municipality_key,
    county_to_key,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_geocodio_response(
    formatted_address: str,
    city: str,
    county: str,
    lat: float,
    lng: float,
    accuracy: float = 1.0,
) -> MagicMock:
    """Build a mock httpx response mimicking Geocodio's JSON structure."""
    resp = MagicMock()
    resp.json.return_value = {
        "results": [
            {
                "formatted_address": formatted_address,
                "address_components": {"city": city, "county": county},
                "location": {"lat": lat, "lng": lng},
                "accuracy": accuracy,
            }
        ]
    }
    resp.raise_for_status = MagicMock()
    return resp


def _mock_census_response(
    matched_address: str,
    city: str,
    lat: float,
    lng: float,
) -> MagicMock:
    """Build a mock httpx response mimicking Census Geocoder JSON."""
    resp = MagicMock()
    resp.json.return_value = {
        "result": {
            "addressMatches": [
                {
                    "matchedAddress": matched_address,
                    "coordinates": {"x": lng, "y": lat},
                    "addressComponents": {"city": city},
                }
            ]
        }
    }
    resp.raise_for_status = MagicMock()
    return resp


def _mock_census_empty_response() -> MagicMock:
    """Census response with no address matches."""
    resp = MagicMock()
    resp.json.return_value = {"result": {"addressMatches": []}}
    resp.raise_for_status = MagicMock()
    return resp


def _make_async_client(mock_response: MagicMock) -> AsyncMock:
    """Wrap a mock response in an async-context-manager-compatible client."""
    client = AsyncMock()
    client.get.return_value = mock_response
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


@pytest.fixture(autouse=True)
def _clear_geocode_cache():
    """Clear the module-level geocode cache between tests."""
    from plotlot.retrieval.geocode import _geocode_cache

    _geocode_cache.clear()
    yield
    _geocode_cache.clear()


# ---------------------------------------------------------------------------
# Key-conversion helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Geocodio-primary tests (existing behaviour)
# ---------------------------------------------------------------------------


class TestGeocodeAddress:
    @pytest.mark.asyncio
    async def test_successful_geocode(self):
        mock_response = _mock_geocodio_response(
            "7940 Plantation Blvd, Miramar, FL 33023",
            city="Miramar",
            county="Broward County",
            lat=25.977,
            lng=-80.232,
        )
        mock_client = _make_async_client(mock_response)

        with (
            patch("plotlot.retrieval.geocode.httpx.AsyncClient", return_value=mock_client),
            patch("plotlot.retrieval.geocode.settings") as mock_settings,
        ):
            mock_settings.geocodio_api_key = "test_key"
            result = await geocode_address("7940 Plantation Blvd, Miramar, FL")

        assert result is not None
        assert result["municipality"] == "Miramar"
        assert result["county"] == "Broward"
        assert result["lat"] == 25.977
        assert result["geocode_provider"] == "geocodio"

    @pytest.mark.asyncio
    async def test_county_suffix_stripped(self):
        mock_response = _mock_geocodio_response(
            "171 NE 209th Ter, Miami, FL 33179",
            city="Miami Gardens",
            county="Miami-Dade County",
            lat=25.949,
            lng=-80.179,
        )
        mock_client = _make_async_client(mock_response)

        with (
            patch("plotlot.retrieval.geocode.httpx.AsyncClient", return_value=mock_client),
            patch("plotlot.retrieval.geocode.settings") as mock_settings,
        ):
            mock_settings.geocodio_api_key = "test_key"
            result = await geocode_address("171 NE 209th Ter, Miami, FL 33179")

        assert result["county"] == "Miami-Dade"
        assert result["municipality"] == "Miami Gardens"


# ---------------------------------------------------------------------------
# Census Geocoder tests
# ---------------------------------------------------------------------------


class TestCensusGeocode:
    """Direct tests for the _census_geocode helper."""

    @pytest.mark.asyncio
    async def test_census_returns_result(self):
        """Census geocoder parses a successful response correctly."""
        mock_response = _mock_census_response(
            matched_address="171 NE 209TH TER, MIAMI GARDENS, FL, 33179",
            city="Miami Gardens",
            lat=25.949,
            lng=-80.179,
        )
        mock_client = _make_async_client(mock_response)

        with patch("plotlot.retrieval.geocode.httpx.AsyncClient", return_value=mock_client):
            result = await _census_geocode("171 NE 209th Ter, Miami, FL 33179")

        assert result is not None
        assert result["municipality"] == "Miami Gardens"
        assert result["lat"] == 25.949
        assert result["lng"] == -80.179
        assert result["geocode_provider"] == "census"
        assert result["accuracy_type"] == "census_geocoder"

    @pytest.mark.asyncio
    async def test_census_empty_results(self):
        """Census geocoder returns None when there are no address matches."""
        mock_response = _mock_census_empty_response()
        mock_client = _make_async_client(mock_response)

        with patch("plotlot.retrieval.geocode.httpx.AsyncClient", return_value=mock_client):
            result = await _census_geocode("some invalid address xyz")

        assert result is None

    @pytest.mark.asyncio
    async def test_census_handles_network_error(self):
        """Census geocoder returns None on network failure."""
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("plotlot.retrieval.geocode.httpx.AsyncClient", return_value=mock_client):
            result = await _census_geocode("171 NE 209th Ter, Miami, FL 33179")

        assert result is None


# ---------------------------------------------------------------------------
# Fallback chain tests
# ---------------------------------------------------------------------------


class TestGeocodeFallbackChain:
    """Tests that geocode_address falls back to Census when Geocodio fails."""

    @pytest.mark.asyncio
    async def test_fallback_when_geocodio_has_no_api_key(self):
        """When GEOCODIO_API_KEY is empty, Census geocoder is used."""
        census_resp = _mock_census_response(
            matched_address="171 NE 209TH TER, MIAMI GARDENS, FL, 33179",
            city="Miami Gardens",
            lat=25.949,
            lng=-80.179,
        )
        census_client = _make_async_client(census_resp)

        with (
            patch("plotlot.retrieval.geocode.httpx.AsyncClient", return_value=census_client),
            patch("plotlot.retrieval.geocode.settings") as mock_settings,
        ):
            mock_settings.geocodio_api_key = ""
            result = await geocode_address("171 NE 209th Ter, Miami, FL 33179")

        assert result is not None
        assert result["geocode_provider"] == "census"
        assert result["municipality"] == "Miami Gardens"
        assert result["lat"] == 25.949

    @pytest.mark.asyncio
    async def test_fallback_when_geocodio_returns_empty(self):
        """When Geocodio returns no results, Census is tried."""
        # Geocodio returns empty results
        geocodio_resp = MagicMock()
        geocodio_resp.json.return_value = {"results": []}
        geocodio_resp.raise_for_status = MagicMock()

        # Census returns a match
        census_resp = _mock_census_response(
            matched_address="100 MAIN ST, MIAMI, FL, 33101",
            city="Miami",
            lat=25.775,
            lng=-80.194,
        )

        call_count = 0

        def _side_effect_client(*args, **kwargs):
            """Return Geocodio client on first call, Census on second."""
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_async_client(geocodio_resp)
            return _make_async_client(census_resp)

        with (
            patch("plotlot.retrieval.geocode.httpx.AsyncClient", side_effect=_side_effect_client),
            patch("plotlot.retrieval.geocode.settings") as mock_settings,
        ):
            mock_settings.geocodio_api_key = "test_key"
            result = await geocode_address("100 Main St, Miami, FL 33101")

        assert result is not None
        assert result["geocode_provider"] == "census"
        assert result["municipality"] == "Miami"

    @pytest.mark.asyncio
    async def test_fallback_when_geocodio_raises_exception(self):
        """When Geocodio throws a network error, Census is tried."""
        # Geocodio client raises
        geocodio_client = AsyncMock()
        geocodio_client.get.side_effect = httpx.ConnectError("Connection refused")
        geocodio_client.__aenter__ = AsyncMock(return_value=geocodio_client)
        geocodio_client.__aexit__ = AsyncMock(return_value=False)

        # Census returns a match
        census_resp = _mock_census_response(
            matched_address="100 MAIN ST, MIAMI, FL, 33101",
            city="Miami",
            lat=25.775,
            lng=-80.194,
        )
        census_client = _make_async_client(census_resp)

        call_count = 0

        def _side_effect_client(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return geocodio_client
            return census_client

        with (
            patch("plotlot.retrieval.geocode.httpx.AsyncClient", side_effect=_side_effect_client),
            patch("plotlot.retrieval.geocode.settings") as mock_settings,
        ):
            mock_settings.geocodio_api_key = "test_key"
            result = await geocode_address("100 Main St, Miami, FL 33101")

        assert result is not None
        assert result["geocode_provider"] == "census"

    @pytest.mark.asyncio
    async def test_all_providers_fail_returns_none(self):
        """When both Geocodio and Census fail, returns None."""
        # Geocodio returns empty
        geocodio_resp = MagicMock()
        geocodio_resp.json.return_value = {"results": []}
        geocodio_resp.raise_for_status = MagicMock()

        # Census returns empty
        census_resp = _mock_census_empty_response()

        call_count = 0

        def _side_effect_client(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_async_client(geocodio_resp)
            return _make_async_client(census_resp)

        with (
            patch("plotlot.retrieval.geocode.httpx.AsyncClient", side_effect=_side_effect_client),
            patch("plotlot.retrieval.geocode.settings") as mock_settings,
        ):
            mock_settings.geocodio_api_key = "test_key"
            result = await geocode_address("some nonsense address")

        assert result is None
