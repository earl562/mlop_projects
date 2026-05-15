"""Unit tests for CaliforniaProvider.

All ArcGIS HTTP calls are mocked — no network required.
Tests cover:
  - Spatial parcel query (happy path for each county)
  - Address LIKE query fallback
  - Zoning code extraction from parcel attributes
  - Separate zoning layer query
  - UniversalProvider fallback when all CA endpoints fail
  - Lot area unit conversion (sq meters heuristic)
  - Unknown county falls through to UniversalProvider
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from plotlot.property.california import CaliforniaProvider, _COUNTY_CONFIG


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_feature(attrs: dict, rings: list | None = None) -> dict:
    """Build a minimal ArcGIS feature dict."""
    geom: dict = {}
    if rings is not None:
        geom = {"rings": [rings]}
    return {"attributes": attrs, "geometry": geom}


def _parcel_attrs(
    *,
    apn: str = "12345",
    site_addr: str = "500 CASTRO ST",
    zone: str = "R1",
    zone_desc: str = "Single Family Residential",
    shape_area: float = 6000.0,
    owner: str = "Test Owner",
    city: str = "Mountain View",
    year_built: int = 1985,
    assessed: float = 850000.0,
) -> dict:
    return {
        "APN": apn,
        "SITE_ADDR": site_addr,
        "ZONE": zone,
        "ZONE_DESC": zone_desc,
        "SHAPE_Area": shape_area,
        "OWNER": owner,
        "CITY": city,
        "YEAR_BUILT": year_built,
        "ASSESSED_VALUE": assessed,
    }


# ---------------------------------------------------------------------------
# _COUNTY_CONFIG completeness
# ---------------------------------------------------------------------------


class TestCountyConfig:
    def test_all_five_counties_present(self):
        expected = {"santa clara", "alameda", "contra costa", "san mateo", "sacramento"}
        assert expected == set(_COUNTY_CONFIG.keys())

    def test_each_county_has_required_keys(self):
        required = {
            "parcel_url",
            "zoning_url",
            "address_field",
            "zoning_fields",
            "desc_fields",
            "lot_fields",
            "lot_unit",
            "folio_fields",
        }
        for county, cfg in _COUNTY_CONFIG.items():
            assert required <= set(cfg.keys()), (
                f"Missing keys for {county}: {required - set(cfg.keys())}"
            )

    def test_parcel_urls_are_non_empty(self):
        for county, cfg in _COUNTY_CONFIG.items():
            assert cfg["parcel_url"], f"parcel_url is empty for {county}"

    def test_zoning_fields_are_lists(self):
        for county, cfg in _COUNTY_CONFIG.items():
            assert isinstance(cfg["zoning_fields"], list), (
                f"zoning_fields should be a list for {county}"
            )
            assert len(cfg["zoning_fields"]) >= 1


# ---------------------------------------------------------------------------
# Spatial parcel query — happy path
# ---------------------------------------------------------------------------


class TestSpatialQuery:
    @pytest.fixture
    def provider(self) -> CaliforniaProvider:
        return CaliforniaProvider()

    @patch("plotlot.property.california.spatial_query", new_callable=AsyncMock)
    async def test_santa_clara_spatial_returns_record(self, mock_spatial, provider):
        feature = _make_feature(_parcel_attrs())
        mock_spatial.return_value = [feature]

        record = await provider.lookup(
            "500 Castro St, Mountain View, CA 94041",
            "Santa Clara",
            lat=37.3894,
            lng=-122.0819,
        )

        assert record is not None
        assert record.county == "Santa Clara"
        assert record.zoning_code == "R1"
        assert record.zoning_description == "Single Family Residential"
        assert record.lot_size_sqft == pytest.approx(6000.0)
        assert record.folio == "12345"
        assert record.owner == "Test Owner"
        assert record.year_built == 1985

    @pytest.mark.parametrize("county", ["Alameda", "Contra Costa", "San Mateo", "Sacramento"])
    @patch("plotlot.property.california.spatial_query", new_callable=AsyncMock)
    async def test_other_counties_spatial(self, mock_spatial, provider, county):
        feature = _make_feature(_parcel_attrs(zone="R2", city="Test City"))
        mock_spatial.return_value = [feature]

        record = await provider.lookup(
            "123 Main St, Test City, CA",
            county,
            lat=37.0,
            lng=-122.0,
        )

        assert record is not None
        assert record.zoning_code == "R2"


# ---------------------------------------------------------------------------
# Address LIKE fallback
# ---------------------------------------------------------------------------


class TestAddressFallback:
    @pytest.fixture
    def provider(self) -> CaliforniaProvider:
        return CaliforniaProvider()

    @patch("plotlot.property.california.spatial_query", new_callable=AsyncMock)
    @patch("plotlot.property.california.httpx.AsyncClient")
    async def test_falls_back_to_address_when_no_lat_lng(
        self, mock_client_cls, mock_spatial, provider
    ):
        mock_spatial.return_value = []  # spatial not called without lat/lng anyway

        feature = _make_feature(_parcel_attrs(site_addr="500 CASTRO ST"))
        mock_response = MagicMock()
        mock_response.json.return_value = {"features": [feature]}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        record = await provider.lookup(
            "500 Castro St, Mountain View, CA 94041",
            "Santa Clara",
            lat=None,
            lng=None,
        )

        assert record is not None
        assert record.folio == "12345"

    @patch("plotlot.property.california.spatial_query", new_callable=AsyncMock)
    @patch("plotlot.property.california.httpx.AsyncClient")
    async def test_spatial_fails_address_succeeds(self, mock_client_cls, mock_spatial, provider):
        mock_spatial.return_value = []  # spatial returns nothing

        feature = _make_feature(_parcel_attrs())
        mock_response = MagicMock()
        mock_response.json.return_value = {"features": [feature]}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        record = await provider.lookup(
            "500 Castro St, Mountain View, CA 94041",
            "Santa Clara",
            lat=37.389,
            lng=-122.081,
        )

        assert record is not None


# ---------------------------------------------------------------------------
# Zoning code extraction edge cases
# ---------------------------------------------------------------------------


class TestZoningExtraction:
    def _provider(self) -> CaliforniaProvider:
        return CaliforniaProvider()

    def test_first_non_empty_zoning_field_wins(self):
        provider = self._provider()
        config = _COUNTY_CONFIG["santa clara"]

        attrs = {"ZONE": "", "ZONING": "R2", "ZONE_CODE": "R3"}
        code, _ = provider._extract_zoning(attrs, config)
        assert code == "R2"

    def test_returns_empty_when_all_null(self):
        provider = self._provider()
        config = _COUNTY_CONFIG["santa clara"]

        attrs = {"ZONE": None, "ZONING": "null", "ZONE_CODE": "N/A"}
        code, desc = provider._extract_zoning(attrs, config)
        assert code == ""
        assert desc == ""

    def test_description_extracted_separately(self):
        provider = self._provider()
        config = _COUNTY_CONFIG["santa clara"]

        attrs = {"ZONE": "R1", "ZONE_DESC": "Low Density Residential"}
        code, desc = provider._extract_zoning(attrs, config)
        assert code == "R1"
        assert desc == "Low Density Residential"


# ---------------------------------------------------------------------------
# Lot area unit conversion
# ---------------------------------------------------------------------------


class TestLotAreaConversion:
    @patch("plotlot.property.california.spatial_query", new_callable=AsyncMock)
    async def test_large_sqft_value_unchanged(self, mock_spatial):
        """Values > 10 000 are treated as sq ft (typical lot: 6 000–40 000 sqft)."""
        provider = CaliforniaProvider()
        feature = _make_feature(_parcel_attrs(shape_area=15_000.0))
        mock_spatial.return_value = [feature]

        record = await provider.lookup("addr", "Santa Clara", lat=37.0, lng=-122.0)
        assert record is not None
        assert record.lot_size_sqft == pytest.approx(15_000.0)

    @patch("plotlot.property.california.spatial_query", new_callable=AsyncMock)
    async def test_small_value_converted_from_sqm(self, mock_spatial):
        """Values < 500 are converted from sq meters (Web Mercator ArcGIS area)."""
        provider = CaliforniaProvider()
        # 465 sq meters ≈ 5 005 sqft (typical dense urban lot)
        feature = _make_feature(_parcel_attrs(shape_area=465.0))
        mock_spatial.return_value = [feature]

        record = await provider.lookup("addr", "Santa Clara", lat=37.0, lng=-122.0)
        assert record is not None
        # 465 * 10.7639 ≈ 5 005
        assert record.lot_size_sqft == pytest.approx(465.0 * 10.7639, rel=0.01)

    @patch("plotlot.property.california.spatial_query", new_callable=AsyncMock)
    async def test_zero_lot_area_stays_zero(self, mock_spatial):
        provider = CaliforniaProvider()
        feature = _make_feature(_parcel_attrs(shape_area=0.0))
        mock_spatial.return_value = [feature]

        record = await provider.lookup("addr", "Santa Clara", lat=37.0, lng=-122.0)
        assert record is not None
        assert record.lot_size_sqft == 0.0


# ---------------------------------------------------------------------------
# UniversalProvider fallback
# ---------------------------------------------------------------------------


class TestUniversalFallback:
    @patch("plotlot.property.california.spatial_query", new_callable=AsyncMock)
    @patch("plotlot.property.california.httpx.AsyncClient")
    @patch(
        "plotlot.property.california.CaliforniaProvider._universal_fallback", new_callable=AsyncMock
    )
    async def test_falls_back_when_all_county_endpoints_fail(
        self, mock_fallback, mock_client_cls, mock_spatial
    ):
        # Both spatial and address queries return nothing
        mock_spatial.return_value = []
        mock_response = MagicMock()
        mock_response.json.return_value = {"features": []}
        mock_response.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        mock_fallback.return_value = None

        provider = CaliforniaProvider()
        record = await provider.lookup(
            "500 Castro St",
            "Santa Clara",
            lat=37.389,
            lng=-122.081,
        )

        mock_fallback.assert_awaited_once()
        assert record is None

    @patch(
        "plotlot.property.california.CaliforniaProvider._universal_fallback", new_callable=AsyncMock
    )
    async def test_unknown_county_uses_universal_fallback(self, mock_fallback):
        mock_fallback.return_value = None

        provider = CaliforniaProvider()
        record = await provider.lookup(
            "100 Test Ave, Fresno, CA",
            "Fresno",
            lat=36.7,
            lng=-119.7,
        )

        mock_fallback.assert_awaited_once()
        assert record is None


# ---------------------------------------------------------------------------
# Registry integration — providers registered for all 5 counties
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_five_ca_counties_registered(self):
        from plotlot.property.registry import get_provider

        counties = ["santa clara", "alameda", "contra costa", "san mateo", "sacramento"]
        for county in counties:
            provider = get_provider(county)
            assert provider is not None, f"No provider registered for {county}"
            assert isinstance(provider, CaliforniaProvider), (
                f"Expected CaliforniaProvider for {county}, got {type(provider)}"
            )

    def test_existing_fl_nc_providers_unaffected(self):
        from plotlot.property.california import CaliforniaProvider
        from plotlot.property.registry import get_provider

        for county in ["broward", "miami-dade", "palm beach", "mecklenburg"]:
            provider = get_provider(county)
            assert provider is not None
            assert not isinstance(provider, CaliforniaProvider), (
                f"FL/NC county {county} incorrectly got CaliforniaProvider"
            )
