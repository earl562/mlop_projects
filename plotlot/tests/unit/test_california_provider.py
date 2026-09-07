"""Unit tests for CaliforniaProvider.

All ArcGIS HTTP calls are mocked — no network required.
Tests cover:
  - Spatial parcel query (happy path for each county)
  - Address LIKE query fallback (counties that have an address field)
  - Santa Clara spatial-only path (no address field in that layer)
  - Zoning code extraction from parcel attributes
  - Lot area unit conversion (acres → sqft for SCC/CCC, sqm heuristic for others)
  - UniversalProvider fallback when all CA endpoints fail
  - Unknown county falls through to UniversalProvider
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from plotlot.property.california import CaliforniaProvider, _COUNTY_CONFIG


# ---------------------------------------------------------------------------
# Per-county attribute fixtures matching VERIFIED field names
# ---------------------------------------------------------------------------


def _make_feature(attrs: dict, rings: list | None = None) -> dict:
    geom: dict = {}
    if rings is not None:
        geom = {"rings": [rings]}
    return {"attributes": attrs, "geometry": geom}


def _santa_clara_attrs(
    *,
    apn: str = "700-12-345",
    zoning: str = "R1",
    acreage: float = 0.15,
    city: str = "Mountain View",
    year_built: int = 1985,
) -> dict:
    """Santa Clara County Regional Open Data layer fields (verified schema 2026-05).

    County-wide coverage; ZONGDSGN carries the zoning designation.
    """
    return {
        "APN": apn,
        "ZONGDSGN": zoning,
        "ACREAGE": acreage,
        "PARCITY": city,
        "YEARBUILT": year_built,
    }


def _alameda_attrs(
    *,
    apn: str = "048-1234-567",
    address: str = "100 Grand Ave, Oakland CA 94612",
    zone: str = "RM-3",
    shape_area: float = 7500.0,
    city: str = "Oakland",
    assessed: float = 600000.0,
) -> dict:
    """Alameda County Assessor AGOL layer fields (verified schema)."""
    return {
        "APN": apn,
        "SitusAddress": address,
        "UseCode": zone,
        "Shape__Area": shape_area,
        "SitusCity": city,
        "TotalNetValue": assessed,
    }


def _contra_costa_attrs(
    *,
    pid: str = "125-180-001",
    address: str = "1000 SAN PABLO AVE",
    city: str = "Richmond",
    acreage: float = 0.20,
) -> dict:
    """Contra Costa County AGOL layer fields (verified schema)."""
    return {
        "PIDPLAIN": pid,
        "Site_Addre": address,
        "City": city,
        "AC": acreage,
    }


def _san_mateo_attrs(
    *,
    apn: str = "063-291-080",
    address: str = "2000 UNIVERSITY AVE",
    city: str = "East Palo Alto",
    land_area: float = 6000.0,
) -> dict:
    """San Mateo County MapServer fields (verified schema)."""
    return {
        "APN": apn,
        "SITUS_ADDR": address,
        "SITUS_CITY": city,
        "LANDAREA": land_area,
    }


def _sacramento_attrs(
    *,
    parcel_number: str = "225-0341-001",
    address: str = "6000 J ST",
    zone: str = "RD-5",
    land_use: str = "Residential",
    lot_size: float = 8700.0,
    city: str = "Sacramento",
    owner: str = "Smith, John",
) -> dict:
    """Sacramento County MapServer layer 22 fields (verified schema)."""
    return {
        "PARCEL_NUMBER": parcel_number,
        "SITUS_ADD1": address,
        "ZONE_": zone,
        "LANDUSE": land_use,
        "LOTSIZE": lot_size,
        "CITY": city,
        "NAME": owner,
    }


# ---------------------------------------------------------------------------
# _COUNTY_CONFIG completeness
# ---------------------------------------------------------------------------


class TestCountyConfig:
    def test_all_five_counties_present(self):
        expected = {
            "santa clara",
            "alameda",
            "contra costa",
            "san mateo",
            "sacramento",
            "san diego",
        }
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
            assert len(cfg["zoning_fields"]) >= 1, (
                f"zoning_fields should have at least one candidate for {county}"
            )

    def test_santa_clara_has_no_address_field(self):
        """Santa Clara regional layer has no address field — spatial only."""
        assert _COUNTY_CONFIG["santa clara"]["address_field"] == ""

    def test_santa_clara_uses_acres(self):
        """SCC regional layer ACREAGE field is in acres."""
        assert _COUNTY_CONFIG["santa clara"]["lot_unit"] == "acres"

    def test_contra_costa_uses_acres(self):
        assert _COUNTY_CONFIG["contra costa"]["lot_unit"] == "acres"

    def test_verified_urls_match_expected_hosts(self):
        assert "map.santaclaraca.gov" in _COUNTY_CONFIG["santa clara"]["parcel_url"]
        assert "services5.arcgis.com" in _COUNTY_CONFIG["alameda"]["parcel_url"]
        assert "services2.arcgis.com" in _COUNTY_CONFIG["contra costa"]["parcel_url"]
        assert "gis.smcgov.org" in _COUNTY_CONFIG["san mateo"]["parcel_url"]
        assert "mapservices.gis.saccounty.net" in _COUNTY_CONFIG["sacramento"]["parcel_url"]


# ---------------------------------------------------------------------------
# Spatial parcel query — happy path per county
# ---------------------------------------------------------------------------


class TestSpatialQuery:
    @pytest.fixture
    def provider(self) -> CaliforniaProvider:
        return CaliforniaProvider()

    @patch("plotlot.property.california.spatial_query", new_callable=AsyncMock)
    async def test_santa_clara_spatial_returns_record(self, mock_spatial, provider):
        """Santa Clara county-wide layer: ZONGDSGN zoning, ACREAGE lot (acres → sqft), PARCITY city."""
        feature = _make_feature(_santa_clara_attrs(acreage=0.15))
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
        assert record.folio == "700-12-345"
        assert record.municipality == "Mountain View"
        assert record.year_built == 1985
        # 0.15 acres × 43 560 = 6 534 sqft
        assert record.lot_size_sqft == pytest.approx(0.15 * 43_560, rel=0.01)

    @patch("plotlot.property.california.spatial_query", new_callable=AsyncMock)
    async def test_alameda_spatial_returns_record(self, mock_spatial, provider):
        """Alameda: SitusAddress, UseCode, Shape__Area (sqft)."""
        feature = _make_feature(_alameda_attrs())
        mock_spatial.return_value = [feature]

        record = await provider.lookup(
            "100 Grand Ave, Oakland, CA 94612",
            "Alameda",
            lat=37.8044,
            lng=-122.2712,
        )

        assert record is not None
        assert record.zoning_code == "RM-3"
        assert record.folio == "048-1234-567"
        assert record.lot_size_sqft == pytest.approx(7500.0)
        assert record.assessed_value == pytest.approx(600000.0)

    @patch("plotlot.property.california.spatial_query", new_callable=AsyncMock)
    async def test_contra_costa_spatial_returns_record(self, mock_spatial, provider):
        """Contra Costa: PIDPLAIN, AC (acres → sqft)."""
        feature = _make_feature(_contra_costa_attrs(acreage=0.20))
        mock_spatial.return_value = [feature]

        record = await provider.lookup(
            "1000 San Pablo Ave, Richmond, CA",
            "Contra Costa",
            lat=37.9358,
            lng=-122.3477,
        )

        assert record is not None
        assert record.folio == "125-180-001"
        assert record.municipality == "Richmond"
        # 0.20 acres × 43 560 = 8 712 sqft
        assert record.lot_size_sqft == pytest.approx(0.20 * 43_560, rel=0.01)

    @patch("plotlot.property.california.spatial_query", new_callable=AsyncMock)
    async def test_san_mateo_spatial_returns_record(self, mock_spatial, provider):
        """San Mateo: SITUS_ADDR, LANDAREA (sqft)."""
        feature = _make_feature(_san_mateo_attrs(land_area=6000.0))
        mock_spatial.return_value = [feature]

        record = await provider.lookup(
            "2000 University Ave, East Palo Alto, CA",
            "San Mateo",
            lat=37.4683,
            lng=-122.1412,
        )

        assert record is not None
        assert record.folio == "063-291-080"
        assert record.lot_size_sqft == pytest.approx(6000.0)

    @patch("plotlot.property.california.spatial_query", new_callable=AsyncMock)
    async def test_sacramento_spatial_returns_record(self, mock_spatial, provider):
        """Sacramento: PARCEL_NUMBER, ZONE_, LOTSIZE."""
        feature = _make_feature(_sacramento_attrs(zone="RD-5", lot_size=8700.0))
        mock_spatial.return_value = [feature]

        record = await provider.lookup(
            "6000 J St, Sacramento, CA",
            "Sacramento",
            lat=38.5816,
            lng=-121.4944,
        )

        assert record is not None
        assert record.zoning_code == "RD-5"
        assert record.folio == "225-0341-001"
        assert record.owner == "Smith, John"
        assert record.lot_size_sqft == pytest.approx(8700.0)


# ---------------------------------------------------------------------------
# Address LIKE fallback (counties that have an address field)
# ---------------------------------------------------------------------------


class TestAddressFallback:
    @pytest.fixture
    def provider(self) -> CaliforniaProvider:
        return CaliforniaProvider()

    @patch("plotlot.property.california.spatial_query", new_callable=AsyncMock)
    @patch("plotlot.property.california.httpx.AsyncClient")
    async def test_sacramento_address_fallback_when_no_lat_lng(
        self, mock_client_cls, mock_spatial, provider
    ):
        """Without lat/lng, Sacramento uses address LIKE query."""
        feature = _make_feature(_sacramento_attrs())
        mock_response = MagicMock()
        mock_response.json.return_value = {"features": [feature]}
        mock_response.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        record = await provider.lookup(
            "6000 J St, Sacramento, CA 95819",
            "Sacramento",
            lat=None,
            lng=None,
        )

        assert record is not None
        assert record.folio == "225-0341-001"

    @patch("plotlot.property.california.spatial_query", new_callable=AsyncMock)
    async def test_santa_clara_skips_address_fallback(self, mock_spatial, provider):
        """Santa Clara has no address field — county address fallback is skipped.
        With lat=None/lng=None and no county results, the statewide layer is tried
        next, then UniversalProvider if statewide also misses."""
        mock_spatial.return_value = []

        with (
            patch.object(
                CaliforniaProvider, "_statewide_parcel", new_callable=AsyncMock
            ) as mock_statewide,
            patch.object(
                CaliforniaProvider, "_universal_fallback", new_callable=AsyncMock
            ) as mock_ufb,
        ):
            mock_statewide.return_value = None
            mock_ufb.return_value = None
            record = await provider.lookup(
                "500 Castro St, Mountain View, CA",
                "Santa Clara",
                lat=None,
                lng=None,
            )
            # Statewide layer tried before universal
            mock_statewide.assert_awaited_once()
            mock_ufb.assert_awaited_once()
            assert record is None

    @patch("plotlot.property.california.spatial_query", new_callable=AsyncMock)
    @patch("plotlot.property.california.httpx.AsyncClient")
    async def test_spatial_fails_address_succeeds_alameda(
        self, mock_client_cls, mock_spatial, provider
    ):
        """When spatial returns nothing, Alameda tries address LIKE query."""
        mock_spatial.return_value = []

        feature = _make_feature(_alameda_attrs())
        mock_response = MagicMock()
        mock_response.json.return_value = {"features": [feature]}
        mock_response.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        record = await provider.lookup(
            "100 Grand Ave, Oakland, CA",
            "Alameda",
            lat=37.8,
            lng=-122.27,
        )

        assert record is not None
        assert record.folio == "048-1234-567"


# ---------------------------------------------------------------------------
# Zoning code extraction edge cases
# ---------------------------------------------------------------------------


class TestZoningExtraction:
    def _provider(self) -> CaliforniaProvider:
        return CaliforniaProvider()

    def test_first_non_empty_zoning_field_wins(self):
        provider = self._provider()
        config = _COUNTY_CONFIG["sacramento"]
        attrs = {"ZONE_": "", "LANDUSE": "Residential", "ZONE": "R2"}
        code, _ = provider._extract_zoning(attrs, config)
        # ZONE_ is empty → falls through to LANDUSE
        assert code == "Residential"

    def test_returns_empty_when_all_null(self):
        provider = self._provider()
        config = _COUNTY_CONFIG["santa clara"]
        attrs = {"ZONGDSGN": None, "ZONE": "null", "ZONING": "N/A"}
        code, desc = provider._extract_zoning(attrs, config)
        assert code == ""
        assert desc == ""

    def test_santa_clara_zongdsgn_field(self):
        """ZONGDSGN is the primary zoning field for the SCC county-wide layer."""
        provider = self._provider()
        config = _COUNTY_CONFIG["santa clara"]
        attrs = {"ZONGDSGN": "R1E2", "GPLANCRT": "ignored"}
        code, _ = provider._extract_zoning(attrs, config)
        assert code == "R1E2"


# ---------------------------------------------------------------------------
# Lot area unit conversion
# ---------------------------------------------------------------------------


class TestLotAreaConversion:
    @patch("plotlot.property.california.spatial_query", new_callable=AsyncMock)
    async def test_santa_clara_acres_converted(self, mock_spatial):
        """Santa Clara lot_unit=acres: ACREAGE 0.25 → 10 890 sqft."""
        provider = CaliforniaProvider()
        feature = _make_feature(_santa_clara_attrs(acreage=0.25))
        mock_spatial.return_value = [feature]

        record = await provider.lookup("addr", "Santa Clara", lat=37.0, lng=-122.0)
        assert record is not None
        assert record.lot_size_sqft == pytest.approx(0.25 * 43_560, rel=0.01)

    @patch("plotlot.property.california.spatial_query", new_callable=AsyncMock)
    async def test_contra_costa_acres_converted(self, mock_spatial):
        """Contra Costa lot_unit=acres: AC 0.30 → 13 068 sqft."""
        provider = CaliforniaProvider()
        feature = _make_feature(_contra_costa_attrs(acreage=0.30))
        mock_spatial.return_value = [feature]

        record = await provider.lookup("addr", "Contra Costa", lat=37.9, lng=-122.3)
        assert record is not None
        assert record.lot_size_sqft == pytest.approx(0.30 * 43_560, rel=0.01)

    @patch("plotlot.property.california.spatial_query", new_callable=AsyncMock)
    async def test_alameda_sqft_large_value_unchanged(self, mock_spatial):
        """Alameda lot_unit=sqft: Shape__Area 7500 stays as-is (≥ 500 threshold)."""
        provider = CaliforniaProvider()
        feature = _make_feature(_alameda_attrs(shape_area=7500.0))
        mock_spatial.return_value = [feature]

        record = await provider.lookup("addr", "Alameda", lat=37.8, lng=-122.27)
        assert record is not None
        assert record.lot_size_sqft == pytest.approx(7500.0)

    @patch("plotlot.property.california.spatial_query", new_callable=AsyncMock)
    async def test_sqm_heuristic_converts_small_values(self, mock_spatial):
        """Values < 500 in sqft mode treated as sq meters and converted."""
        provider = CaliforniaProvider()
        # San Mateo uses sqft; inject a value < 500 to trigger sq-meter heuristic
        feature = _make_feature(_san_mateo_attrs(land_area=465.0))
        mock_spatial.return_value = [feature]

        record = await provider.lookup("addr", "San Mateo", lat=37.4, lng=-122.1)
        assert record is not None
        assert record.lot_size_sqft == pytest.approx(465.0 * 10.7639, rel=0.01)

    @patch("plotlot.property.california.spatial_query", new_callable=AsyncMock)
    async def test_zero_lot_area_stays_zero(self, mock_spatial):
        provider = CaliforniaProvider()
        feature = _make_feature(_sacramento_attrs(lot_size=0.0))
        mock_spatial.return_value = [feature]

        record = await provider.lookup("addr", "Sacramento", lat=38.5, lng=-121.4)
        assert record is not None
        assert record.lot_size_sqft == 0.0


# ---------------------------------------------------------------------------
# CA statewide parcel layer (counties without a specific config)
# ---------------------------------------------------------------------------


class TestStatewideParcel:
    """CaliforniaProvider falls back to CA_State_Parcels FeatureServer for unknown counties."""

    @patch("plotlot.property.california.spatial_query", new_callable=AsyncMock)
    async def test_statewide_spatial_returns_record(self, mock_spatial):
        """Unknown county → statewide layer spatial query → PropertyRecord."""
        feature = {
            "attributes": {
                "PARCEL_APN": "15810032",
                "SITE_ADDR": "500 CASTRO ST",
                "SITE_CITY": "MOUNTAIN VIEW",
                "Shape__Area": 30953.64,  # sq meters
            },
            "geometry": {},
        }
        mock_spatial.return_value = [feature]

        provider = CaliforniaProvider()
        record = await provider.lookup(
            "500 Castro St, Mountain View, CA",
            "Marin",  # no county config → statewide
            lat=37.3894,
            lng=-122.0819,
        )

        assert record is not None
        assert record.folio == "15810032"
        assert record.address == "500 CASTRO ST"
        assert record.municipality == "MOUNTAIN VIEW"
        assert record.county == "Marin"
        assert record.zoning_code == ""  # expected — ordinance search resolves zoning
        # 30953.64 sqm × 10.7639 ≈ 333 226 sqft — just verify conversion happened
        assert record.lot_size_sqft == pytest.approx(30953.64 * 10.7639, rel=0.01)

    @patch("plotlot.property.california.spatial_query", new_callable=AsyncMock)
    @patch("plotlot.property.california.httpx.AsyncClient")
    async def test_statewide_address_fallback_when_no_lat_lng(self, mock_client_cls, mock_spatial):
        """Without lat/lng, statewide layer tries SITE_ADDR LIKE query."""
        feature = {
            "attributes": {
                "PARCEL_APN": "999-001-001",
                "SITE_ADDR": "100 MAIN ST",
                "SITE_CITY": "NOVATO",
                "Shape__Area": 500.0,
            },
            "geometry": {},
        }
        mock_response = MagicMock()
        mock_response.json.return_value = {"features": [feature]}
        mock_response.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        provider = CaliforniaProvider()
        record = await provider.lookup("100 Main St, Novato, CA", "Marin", lat=None, lng=None)

        assert record is not None
        assert record.folio == "999-001-001"
        assert record.municipality == "NOVATO"

    @patch("plotlot.property.california.spatial_query", new_callable=AsyncMock)
    @patch("plotlot.property.california.httpx.AsyncClient")
    @patch(
        "plotlot.property.california.CaliforniaProvider._universal_fallback",
        new_callable=AsyncMock,
    )
    async def test_statewide_miss_falls_to_universal(self, mock_ufb, mock_client_cls, mock_spatial):
        """Statewide returns nothing → UniversalProvider is called."""
        mock_spatial.return_value = []
        mock_response = MagicMock()
        mock_response.json.return_value = {"features": []}
        mock_response.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client
        mock_ufb.return_value = None

        provider = CaliforniaProvider()
        record = await provider.lookup("100 Main St, Novato, CA", "Marin", lat=37.1, lng=-122.5)

        mock_ufb.assert_awaited_once()
        assert record is None

    def test_parse_statewide_sqm_conversion(self):
        """Shape__Area in sq meters is correctly converted to sq ft."""
        provider = CaliforniaProvider()
        feature = {
            "attributes": {
                "PARCEL_APN": "001",
                "SITE_ADDR": "1 TEST ST",
                "SITE_CITY": "TESTVILLE",
                "Shape__Area": 1000.0,  # 1000 sqm
            },
            "geometry": {},
        }
        record = provider._parse_statewide_feature(feature, "Marin")
        assert record.lot_size_sqft == pytest.approx(1000.0 * 10.7639, rel=0.01)


# ---------------------------------------------------------------------------
# UniversalProvider fallback
# ---------------------------------------------------------------------------


class TestUniversalFallback:
    @patch("plotlot.property.california.spatial_query", new_callable=AsyncMock)
    @patch("plotlot.property.california.httpx.AsyncClient")
    @patch(
        "plotlot.property.california.CaliforniaProvider._universal_fallback",
        new_callable=AsyncMock,
    )
    async def test_falls_back_when_all_county_endpoints_fail(
        self, mock_fallback, mock_client_cls, mock_spatial
    ):
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
            "6000 J St",
            "Sacramento",
            lat=38.58,
            lng=-121.49,
        )

        mock_fallback.assert_awaited_once()
        assert record is None

    @patch(
        "plotlot.property.california.CaliforniaProvider._universal_fallback",
        new_callable=AsyncMock,
    )
    @patch(
        "plotlot.property.california.CaliforniaProvider._statewide_parcel",
        new_callable=AsyncMock,
    )
    async def test_unknown_county_uses_universal_fallback(self, mock_statewide, mock_fallback):
        mock_statewide.return_value = None
        mock_fallback.return_value = None
        provider = CaliforniaProvider()
        record = await provider.lookup("100 Test Ave, Fresno, CA", "Fresno", lat=36.7, lng=-119.7)
        mock_statewide.assert_awaited_once()
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
        from plotlot.property.registry import get_provider

        for county in ["broward", "miami-dade", "palm beach", "mecklenburg"]:
            provider = get_provider(county)
            assert provider is not None
            assert not isinstance(provider, CaliforniaProvider), (
                f"FL/NC county {county} incorrectly got CaliforniaProvider"
            )


# ---------------------------------------------------------------------------
# San Diego authoritative assessor lot-size override + provenance
# ---------------------------------------------------------------------------


def _sd_statewide_feature(*, apn: str = "4364230200", area_sqm: float = 602.8) -> dict:
    """The CA statewide layer feature San Diego resolves through (geometry lot)."""
    return _make_feature(
        {
            "PARCEL_APN": apn,
            "SITE_ADDR": "1233 HUENEME ST",
            "SITE_CITY": "SAN DIEGO",
            "Shape__Area": area_sqm,  # sq meters → ~6,489 sqft (a GIS estimate)
        }
    )


def _mock_assessor_client(mock_client_cls, *, features: list[dict]) -> None:
    """Wire httpx.AsyncClient so the assessor /query returns `features`."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"features": features}
    mock_response.raise_for_status = MagicMock()
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client_cls.return_value = mock_client


class TestSanDiegoAssessorLot:
    """SD overrides the unreliable statewide polygon area with the legal lot."""

    @pytest.fixture
    def provider(self) -> CaliforniaProvider:
        return CaliforniaProvider()

    @patch("plotlot.property.california.httpx.AsyncClient")
    @patch("plotlot.property.california.spatial_query", new_callable=AsyncMock)
    async def test_assessor_lot_overrides_geometry(self, mock_spatial, mock_client_cls, provider):
        """The assessor's recorded lot (7,710) replaces the polygon estimate (~6,489)."""
        mock_spatial.return_value = [_sd_statewide_feature()]
        _mock_assessor_client(
            mock_client_cls,
            features=[{"attributes": {"ACREAGE": None, "Shape.STArea()": 7710.49}}],
        )

        record = await provider.lookup(
            "1233 Hueneme St, San Diego, CA 92110", "San Diego", lat=32.756, lng=-117.197
        )

        assert record is not None
        assert record.folio == "4364230200"
        # Authoritative legal lot, not the ~6,489 sqft statewide polygon.
        assert record.lot_size_sqft == pytest.approx(7710.49)
        assert record.lot_size_source == "assessor"

    @patch("plotlot.property.california.httpx.AsyncClient")
    @patch("plotlot.property.california.spatial_query", new_callable=AsyncMock)
    async def test_assessor_prefers_recorded_acreage(self, mock_spatial, mock_client_cls, provider):
        """When ACREAGE is populated it wins (legal figure) over geometry STArea."""
        mock_spatial.return_value = [_sd_statewide_feature()]
        _mock_assessor_client(
            mock_client_cls,
            features=[{"attributes": {"ACREAGE": 0.177, "Shape.STArea()": 7710.49}}],
        )

        record = await provider.lookup(
            "1233 Hueneme St, San Diego, CA 92110", "San Diego", lat=32.756, lng=-117.197
        )

        assert record is not None
        assert record.lot_size_sqft == pytest.approx(0.177 * 43_560, rel=0.001)
        assert record.lot_size_source == "assessor"

    @patch("plotlot.property.california.httpx.AsyncClient")
    @patch("plotlot.property.california.spatial_query", new_callable=AsyncMock)
    async def test_assessor_miss_keeps_geometry_and_flags_it(
        self, mock_spatial, mock_client_cls, provider
    ):
        """Fail loud, not silently wrong: a miss keeps the estimate, flagged 'geometry'."""
        mock_spatial.return_value = [_sd_statewide_feature()]
        _mock_assessor_client(mock_client_cls, features=[])  # APN not found

        record = await provider.lookup(
            "1233 Hueneme St, San Diego, CA 92110", "San Diego", lat=32.756, lng=-117.197
        )

        assert record is not None
        # Geometry estimate retained, but provenance marks it unconfirmed.
        assert record.lot_size_sqft == pytest.approx(602.8 * 10.7639, rel=0.01)
        assert record.lot_size_source == "geometry"


class TestGeometryLotFieldDetection:
    def test_polygon_area_fields_are_geometry(self):
        from plotlot.property.california import _is_geometry_lot_field

        for f in ("Shape__Area", "SHAPE_Area", "Shape.STArea()", "shape_area"):
            assert _is_geometry_lot_field(f) is True

    def test_named_assessor_fields_are_not_geometry(self):
        from plotlot.property.california import _is_geometry_lot_field

        for f in ("ACREAGE", "LOTSIZE", "AC", "LANDAREA"):
            assert _is_geometry_lot_field(f) is False
