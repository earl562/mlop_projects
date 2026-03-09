"""Tests for the Mecklenburg County PropertyProvider.

All external API calls are mocked — no real HTTP requests are made.
"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from plotlot.core.types import PropertyRecord
from plotlot.property.mecklenburg import MecklenburgProvider, MECKLENBURG_PARCEL_URL
from plotlot.property.registry import get_provider, registered_counties


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_FEATURE = {
    "attributes": {
        "PID": "12345678",
        "SITE_ADDR": "600 E 4TH ST",
        "CITY": "Charlotte",
        "OWNER_NAME": "SMITH JOHN",
        "ZONE_CLASS": "R-3",
        "ZONE_DESC": "Single Family Residential",
        "LAND_USE_CD": "100",
        "LAND_USE": "Single Family",
        "SHAPE_Area": 85000.0,  # sq ft (>= 50000 → no conversion)
        "TOTAL_VALUE": 350000.0,
        "MARKET_VALUE": 375000.0,
        "YEAR_BUILT": 1998,
        "BLDG_SQFT": 2200.0,
    }
}


SAMPLE_FEATURE_ALT_FIELDS = {
    "attributes": {
        "PARCEL_ID": "ALT-9999",
        "ADDRESS": "100 MAIN ST",
        "JURIS": "Huntersville",
        "OWNER": "DOE JANE",
        "ZONING": "MX-2",
        "ZONE_DESC": "",
        "LU_CODE": "200",
        "LU_DESC": "Mixed Use",
        "LAND_AREA": 4000.0,  # sq meters (< 50000 threshold → converted)
        "ASSESSED_VALUE": 200000.0,
        "TOTAL_VALUE": 0,
        "MARKET_VALUE": 0,
        "YEAR_BUILT": 2005,
        "HEATED_AREA": 1800.0,
    }
}


def _make_response(features: list[dict], status: int = 200) -> httpx.Response:
    """Build a mock httpx.Response with feature data."""
    request = httpx.Request("GET", MECKLENBURG_PARCEL_URL)
    return httpx.Response(status, json={"features": features}, request=request)


# ---------------------------------------------------------------------------
# Provider registration
# ---------------------------------------------------------------------------


class TestMecklenburgRegistration:
    def test_registered_in_registry(self):
        """Mecklenburg provider should be registered after package import."""
        assert "mecklenburg" in registered_counties()

    def test_get_provider_returns_mecklenburg(self):
        provider = get_provider("mecklenburg")
        assert provider is not None
        assert isinstance(provider, MecklenburgProvider)

    def test_get_provider_case_insensitive(self):
        assert get_provider("Mecklenburg") is not None
        assert get_provider("MECKLENBURG") is not None


# ---------------------------------------------------------------------------
# Spatial query
# ---------------------------------------------------------------------------


class TestSpatialQuery:
    @pytest.mark.asyncio
    async def test_spatial_query_returns_property_record(self):
        provider = MecklenburgProvider()

        async def mock_get(url, params=None):
            return _make_response([SAMPLE_FEATURE])

        with patch("plotlot.property.mecklenburg.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await provider.lookup(
                "600 E 4th St, Charlotte, NC",
                "Mecklenburg",
                lat=35.227,
                lng=-80.843,
            )

        assert result is not None
        assert isinstance(result, PropertyRecord)
        assert result.folio == "12345678"
        assert result.address == "600 E 4TH ST"
        assert result.municipality == "Charlotte"
        assert result.county == "Mecklenburg"
        assert result.owner == "SMITH JOHN"
        assert result.zoning_code == "R-3"
        assert result.zoning_description == "Single Family Residential"
        assert result.year_built == 1998
        assert result.building_area_sqft == 2200.0

    @pytest.mark.asyncio
    async def test_spatial_query_empty_returns_none_then_address_fallback(self):
        """When spatial query returns no features, falls back to address query."""
        provider = MecklenburgProvider()
        call_urls: list[str] = []

        async def mock_get(url, params=None):
            call_urls.append(url)
            # First call (spatial) returns empty, second (address) returns data
            if len(call_urls) == 1:
                return _make_response([])
            return _make_response([SAMPLE_FEATURE])

        with patch("plotlot.property.mecklenburg.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await provider.lookup(
                "600 E 4th St, Charlotte, NC",
                "Mecklenburg",
                lat=35.227,
                lng=-80.843,
            )

        assert result is not None
        assert result.folio == "12345678"
        # Should have made 2 API calls (spatial + address)
        assert len(call_urls) == 2


# ---------------------------------------------------------------------------
# Address query
# ---------------------------------------------------------------------------


class TestAddressQuery:
    @pytest.mark.asyncio
    async def test_address_query_returns_property_record(self):
        """When no lat/lng provided, goes straight to address query."""
        provider = MecklenburgProvider()

        async def mock_get(url, params=None):
            return _make_response([SAMPLE_FEATURE])

        with patch("plotlot.property.mecklenburg.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await provider.lookup(
                "600 E 4th St, Charlotte, NC",
                "Mecklenburg",
            )

        assert result is not None
        assert result.folio == "12345678"

    @pytest.mark.asyncio
    async def test_address_query_empty_returns_none(self):
        provider = MecklenburgProvider()

        async def mock_get(url, params=None):
            return _make_response([])

        with patch("plotlot.property.mecklenburg.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await provider.lookup(
                "999 Nonexistent St, Charlotte, NC",
                "Mecklenburg",
            )

        assert result is None


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_api_error_returns_none(self):
        """HTTP errors are caught and None is returned."""
        provider = MecklenburgProvider()

        async def mock_get(url, params=None):
            request = httpx.Request("GET", url)
            raise httpx.HTTPStatusError(
                "Server Error",
                request=request,
                response=httpx.Response(500, request=request),
            )

        with patch("plotlot.property.mecklenburg.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await provider.lookup(
                "600 E 4th St, Charlotte, NC",
                "Mecklenburg",
                lat=35.227,
                lng=-80.843,
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_timeout_returns_none(self):
        """Timeout errors are caught gracefully."""
        provider = MecklenburgProvider()

        async def mock_get(url, params=None):
            raise httpx.TimeoutException("Connection timed out")

        with patch("plotlot.property.mecklenburg.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await provider.lookup(
                "600 E 4th St, Charlotte, NC",
                "Mecklenburg",
                lat=35.227,
                lng=-80.843,
            )

        assert result is None


# ---------------------------------------------------------------------------
# _parse_feature field extraction
# ---------------------------------------------------------------------------


class TestParseFeature:
    def test_parses_primary_field_names(self):
        provider = MecklenburgProvider()
        record = provider._parse_feature(SAMPLE_FEATURE["attributes"])

        assert record.folio == "12345678"
        assert record.address == "600 E 4TH ST"
        assert record.municipality == "Charlotte"
        assert record.county == "Mecklenburg"
        assert record.owner == "SMITH JOHN"
        assert record.zoning_code == "R-3"
        assert record.zoning_description == "Single Family Residential"
        assert record.land_use_code == "100"
        assert record.land_use_description == "Single Family"
        assert record.lot_size_sqft == 85000.0
        assert record.assessed_value == 350000.0
        assert record.market_value == 375000.0
        assert record.year_built == 1998
        assert record.building_area_sqft == 2200.0

    def test_parses_alternate_field_names(self):
        provider = MecklenburgProvider()
        record = provider._parse_feature(SAMPLE_FEATURE_ALT_FIELDS["attributes"])

        assert record.folio == "ALT-9999"
        assert record.address == "100 MAIN ST"
        assert record.municipality == "Huntersville"
        assert record.owner == "DOE JANE"
        assert record.zoning_code == "MX-2"
        assert record.land_use_code == "200"
        assert record.land_use_description == "Mixed Use"
        assert record.year_built == 2005
        assert record.building_area_sqft == 1800.0
        # LAND_AREA=4000 (< 50000) → converted from sq meters
        assert record.lot_size_sqft == pytest.approx(4000.0 * 10.764, rel=1e-3)

    def test_handles_empty_attributes(self):
        provider = MecklenburgProvider()
        record = provider._parse_feature({})

        assert record.folio == ""
        assert record.address == ""
        assert record.county == "Mecklenburg"
        assert record.lot_size_sqft == 0.0
        assert record.assessed_value == 0.0
        assert record.year_built == 0

    def test_lot_size_no_conversion_when_large(self):
        """Lot sizes >= 50000 are assumed to already be in sq feet."""
        provider = MecklenburgProvider()
        attrs = {"SHAPE_Area": 75000.0}
        record = provider._parse_feature(attrs)
        assert record.lot_size_sqft == 75000.0  # no conversion

    def test_lot_size_conversion_when_small(self):
        """Lot sizes < 50000 are assumed to be sq meters and converted."""
        provider = MecklenburgProvider()
        attrs = {"SHAPE_Area": 500.0}
        record = provider._parse_feature(attrs)
        assert record.lot_size_sqft == pytest.approx(500.0 * 10.764, rel=1e-3)
