"""Tests for multi-county property lookup via ArcGIS REST APIs."""

import pytest
from unittest.mock import AsyncMock, patch

from plotlot.core.types import PropertyRecord
from plotlot.property.california import CaliforniaProvider
from plotlot.retrieval.property import (
    BROWARD_CITY_CODES,
    _address_components,
    _addresses_confidently_match,
    _addresses_spatially_recover,
    _build_broward_where_clause,
    _decode_broward_city,
    _extract_city_hint,
    _miami_dade_where_clauses,
    _normalize_address,
    _parse_lot_dimensions,
    _safe_float,
    _select_best_address_feature,
    lookup_property,
)


class TestNormalizeAddress:
    def test_basic(self):
        assert _normalize_address("171 NE 209th Ter") == "171 NE 209 TER"

    def test_strips_city_state(self):
        result = _normalize_address("171 NE 209th Ter, Miami, FL 33179")
        assert result == "171 NE 209 TER"

    def test_removes_ordinal_suffix(self):
        assert "1ST" not in _normalize_address("100 NW 1st Ave")
        assert "3RD" not in _normalize_address("200 SW 3rd St")

    def test_uppercases(self):
        assert _normalize_address("7940 plantation blvd") == "7940 PLANTATION BLVD"

    def test_removes_periods(self):
        assert _normalize_address("100 N.W. 1st Ave") == "100 NW 1 AVE"


class TestBrowardHelpers:
    def test_extract_city_hint(self):
        assert _extract_city_hint("1517 NE 5th Ct, Fort Lauderdale, FL 33301") == "fort lauderdale"

    def test_extract_city_hint_missing_city(self):
        assert _extract_city_hint("1517 NE 5th Ct") == ""

    def test_broward_city_code_map_contains_fort_lauderdale(self):
        assert BROWARD_CITY_CODES["fort lauderdale"] == "FL"

    def test_decode_broward_city_code(self):
        assert _decode_broward_city("FL") == "Fort Lauderdale"


class TestCountyWhereClauses:
    def test_miami_dade_tries_exact_before_like(self):
        clauses = _miami_dade_where_clauses("1600 NW 7 AVE")
        assert clauses[0] == "TRUE_SITE_ADDR='1600 NW 7 AVE'"
        assert "LIKE '1600 %'" in clauses[1]

    def test_broward_numeric_street_name_uses_exact_match(self):
        clause = _build_broward_where_clause(
            street_num="1234",
            street_direction="NW",
            street_name="15",
            street_type="ST",
            city_code="FL",
            exact_name=True,
        )
        assert "SITUS_STREET_NAME = '15'" in clause
        assert "SITUS_STREET_DIRECTION='NW'" in clause
        assert "SITUS_STREET_TYPE='ST'" in clause
        assert "SITUS_CITY='FL'" in clause


class TestAddressConfidence:
    def test_address_components_split_direction_name_and_type(self):
        assert _address_components("1234 NW 15th St, Fort Lauderdale, FL 33311") == (
            "1234",
            "NW",
            "15",
            "ST",
        )

    def test_addresses_confidently_match_exact_numeric_street(self):
        assert _addresses_confidently_match("1234 NW 15 ST", "1234 NW 15th St, Fort Lauderdale, FL")

    def test_addresses_confidently_match_rejects_house_number_substring(self):
        assert not _addresses_confidently_match("11600 NW 7 AVE", "1600 NW 7th Ave, Miami, FL")

    def test_addresses_confidently_match_rejects_numeric_street_mismatch(self):
        assert not _addresses_confidently_match("101 SE 16 AVE", "101 SE 1st Ave, Fort Lauderdale, FL")

    def test_addresses_spatially_recover_allows_same_corridor_small_house_number_delta(self):
        assert _addresses_spatially_recover("1603 NW 7 AVE", "1600 NW 7th Ave, Miami, FL")

    def test_addresses_spatially_recover_rejects_large_house_number_delta(self):
        assert not _addresses_spatially_recover("11600 NW 7 AVE", "1600 NW 7th Ave, Miami, FL")


class TestParseLotDimensions:
    def test_standard_format(self):
        assert _parse_lot_dimensions("LOT SIZE 75.000 X 100") == "75 x 100"

    def test_no_decimals(self):
        assert _parse_lot_dimensions("50 X 120") == "50 x 120"

    def test_with_decimals(self):
        assert _parse_lot_dimensions("75.500 X 100.250") == "75.5 x 100.25"

    def test_no_match(self):
        assert _parse_lot_dimensions("SOME LEGAL DESC") == ""

    def test_empty(self):
        assert _parse_lot_dimensions("") == ""


class TestSafeFloat:
    def test_normal_number(self):
        assert _safe_float(8000.0) == 8000.0

    def test_string_number(self):
        assert _safe_float("8000") == 8000.0

    def test_currency_string(self):
        assert _safe_float("$74,500") == 74500.0

    def test_dollar_sign_only(self):
        assert _safe_float("$74") == 74.0

    def test_none(self):
        assert _safe_float(None) == 0.0

    def test_empty_string(self):
        assert _safe_float("") == 0.0

    def test_garbage(self):
        assert _safe_float("N/A") == 0.0


class TestLookupProperty:
    @pytest.mark.asyncio
    async def test_miami_dade_success(self):
        mock_features = [
            {
                "attributes": {
                    "FOLIO": "34-1136-003-3330",
                    "TRUE_SITE_ADDR": "171 NE 209 TER",
                    "TRUE_SITE_CITY": "MIAMI GARDENS",
                    "TRUE_OWNER1": "ROBERT L HARRIS",
                    "DOR_CODE_CUR": "0100",
                    "DOR_DESC": "SINGLE FAMILY - GENERAL",
                    "BEDROOM_COUNT": 4,
                    "BATHROOM_COUNT": 3.0,
                    "HALF_BATHROOM_COUNT": 0,
                    "FLOOR_COUNT": 1,
                    "UNIT_COUNT": 1,
                    "BUILDING_ACTUAL_AREA": 2015.0,
                    "BUILDING_HEATED_AREA": 1935.0,
                    "LOT_SIZE": 7500.0,
                    "YEAR_BUILT": 1962,
                    "ASSESSED_VAL_CUR": 148298.0,
                    "PRICE_1": 69000.0,
                    "DOS_1": "12/01/1991",
                    "LEGAL": "LOT SIZE 75.000 X 100",
                },
                "geometry": {"x": -80.179, "y": 25.949},
            }
        ]

        with (
            patch("plotlot.retrieval.property._query_arcgis", return_value=mock_features),
            patch(
                "plotlot.retrieval.property._spatial_query_zoning",
                return_value=("R-1", "Single Family"),
            ),
        ):
            result = await lookup_property(
                "171 NE 209th Ter, Miami, FL 33179",
                county="Miami-Dade",
                lat=25.949,
                lng=-80.179,
            )

        assert isinstance(result, PropertyRecord)
        assert result.folio == "34-1136-003-3330"
        assert result.zoning_code == "R-1"
        assert result.lot_size_sqft == 7500.0
        assert result.lot_dimensions == "75 x 100"
        assert result.bedrooms == 4
        assert result.bathrooms == 3.0
        assert result.year_built == 1962
        assert result.owner == "ROBERT L HARRIS"

    def test_select_best_address_feature_prefers_exact_match(self):
        features = [
            {
                "attributes": {
                    "TRUE_SITE_ADDR": "171 NE 46 ST",
                    "TRUE_OWNER1": "WRONG OWNER",
                }
            },
            {
                "attributes": {
                    "TRUE_SITE_ADDR": "171 NE 209 TER",
                    "TRUE_OWNER1": "CORRECT OWNER",
                }
            },
        ]

        best = _select_best_address_feature(features, "171 NE 209 TER")
        assert best["attributes"]["TRUE_SITE_ADDR"] == "171 NE 209 TER"
        assert best["attributes"]["TRUE_OWNER1"] == "CORRECT OWNER"

    @pytest.mark.asyncio
    async def test_broward_success(self):
        property_features = [
            {
                "attributes": {
                    "FOLIO_NUMBER": "504210230010",
                    "SITUS_STREET_NUMBER": "7940",
                    "SITUS_STREET_DIRECTION": "",
                    "SITUS_STREET_NAME": "PLANTATION",
                    "SITUS_STREET_TYPE": "BLVD",
                    "SITUS_CITY": "MIRAMAR",
                    "NAME_LINE_1": "JOHN DOE",
                    "USE_CODE": "01",
                    "BLDG_USE_CODE": "01",
                    "BLDG_YEAR_BUILT": 2005,
                    "BLDG_ADJ_SQ_FOOTAGE": 2500.0,
                    "UNDER_AIR_SQFT": "2200",
                    "JUST_BUILDING_VALUE": 350000,
                },
            }
        ]
        parcel_features = [
            {
                "attributes": {
                    "FOLIO": "504210230010",
                    "SHAPE.STArea()": 8000.0,
                },
            }
        ]

        async def mock_arcgis(url, **kwargs):
            if "MapServer/16" in url:
                return parcel_features
            return property_features

        with (
            patch("plotlot.retrieval.property._query_arcgis", side_effect=mock_arcgis),
            patch(
                "plotlot.retrieval.property._spatial_query_zoning",
                return_value=("RS-4", "Residential"),
            ),
        ):
            result = await lookup_property(
                "7940 Plantation Blvd, Miramar, FL",
                county="Broward",
                lat=25.977,
                lng=-80.232,
            )

        assert isinstance(result, PropertyRecord)
        assert result.folio == "504210230010"
        assert result.zoning_code == "RS-4"
        assert result.lot_size_sqft == 8000.0
        assert result.living_area_sqft == 2200.0
        assert result.year_built == 2005

    @pytest.mark.asyncio
    async def test_palm_beach_success(self):
        mock_features = [
            {
                "attributes": {
                    "PARCEL_NUMBER": "74434316090000100",
                    "SITE_ADDR_STR": "100 CLEMATIS ST",
                    "MUNICIPALITY": "WEST PALM BEACH",
                    "OWNER_NAME1": "CITY OF WPB",
                    "PROPERTY_USE": "86",
                    "YRBLT": "1990",
                    "ACRES": 0.5,
                    "ASSESSED_VAL": 500000.0,
                    "TOTAL_MARKET": 600000.0,
                    "PRICE": 400000,
                    "SALE_DATE": None,
                    "LEGAL1": "LOT 1 BLK A",
                },
            }
        ]

        with patch("plotlot.retrieval.property._query_arcgis", return_value=mock_features):
            result = await lookup_property(
                "100 Clematis St, West Palm Beach, FL",
                county="Palm Beach",
                lat=26.715,
                lng=-80.053,
            )

        assert isinstance(result, PropertyRecord)
        assert result.folio == "74434316090000100"
        assert result.lot_size_sqft == pytest.approx(21780.0, rel=0.01)
        assert result.year_built == 1990

    @pytest.mark.asyncio
    async def test_broward_prefers_city_filtered_match_when_multiple_features(self):
        property_features = [
            {
                "attributes": {
                    "FOLIO_NUMBER": "504221120010",
                    "SITUS_STREET_NUMBER": "1517",
                    "SITUS_STREET_DIRECTION": "SW",
                    "SITUS_STREET_NAME": "25",
                    "SITUS_STREET_TYPE": "ST",
                    "SITUS_CITY": "FL",
                    "NAME_LINE_1": "WRONG MATCH LLC",
                    "USE_CODE": "08",
                    "BLDG_YEAR_BUILT": 1978,
                    "BLDG_ADJ_SQ_FOOTAGE": 1206.0,
                    "UNDER_AIR_SQFT": "0",
                    "JUST_BUILDING_VALUE": 379820,
                },
                "geometry": {"x": -80.1619, "y": 26.0920},
            },
            {
                "attributes": {
                    "FOLIO_NUMBER": "494234120010",
                    "SITUS_STREET_NUMBER": "1517",
                    "SITUS_STREET_DIRECTION": "NE",
                    "SITUS_STREET_NAME": "5",
                    "SITUS_STREET_TYPE": "CT",
                    "SITUS_CITY": "FL",
                    "NAME_LINE_1": "RIGHT MATCH LLC",
                    "USE_CODE": "01",
                    "BLDG_YEAR_BUILT": 1954,
                    "BLDG_ADJ_SQ_FOOTAGE": 1450.0,
                    "UNDER_AIR_SQFT": "1300",
                    "JUST_BUILDING_VALUE": 250000,
                },
                "geometry": {"x": -80.128145, "y": 26.129402},
            },
        ]
        parcel_features = [
            {
                "attributes": {
                    "FOLIO": "494234120010",
                    "SHAPE.STArea()": 8000.0,
                },
            }
        ]

        async def mock_arcgis(url, **kwargs):
            if "MapServer/16" in url:
                return parcel_features
            return property_features

        with (
            patch("plotlot.retrieval.property._query_arcgis", side_effect=mock_arcgis),
            patch(
                "plotlot.retrieval.property._spatial_query_zoning",
                return_value=("RS-8", "Residential Single Family"),
            ),
        ):
            result = await lookup_property(
                "1517 NE 5th Ct, Fort Lauderdale, FL 33301",
                county="Broward",
                lat=26.129402,
                lng=-80.128145,
            )

        assert isinstance(result, PropertyRecord)
        assert result.folio == "494234120010"
        assert result.address == "1517 NE 5 CT"
        assert result.owner == "RIGHT MATCH LLC"
        assert result.zoning_code == "RS-8"

    @pytest.mark.asyncio
    async def test_broward_lookup_includes_city_code_in_primary_query(self):
        captured_wheres: list[str] = []

        async def mock_arcgis(url, **kwargs):
            captured_wheres.append(kwargs["where"])
            return []

        with patch("plotlot.retrieval.property._query_arcgis", side_effect=mock_arcgis):
            result = await lookup_property(
                "1517 NE 5th Ct, Fort Lauderdale, FL 33301",
                county="Broward",
                lat=26.129402,
                lng=-80.128145,
            )

        assert result is None
        assert captured_wheres
        assert "SITUS_CITY='FL'" in captured_wheres[0]
        assert "SITUS_STREET_NAME = '5'" in captured_wheres[0]

    @pytest.mark.asyncio
    async def test_broward_lookup_decodes_city_code_to_municipality_name(self):
        property_features = [
            {
                "attributes": {
                    "FOLIO_NUMBER": "494234120010",
                    "SITUS_STREET_NUMBER": "1517",
                    "SITUS_STREET_DIRECTION": "NE",
                    "SITUS_STREET_NAME": "5",
                    "SITUS_STREET_TYPE": "CT",
                    "SITUS_CITY": "FL",
                    "NAME_LINE_1": "RIGHT MATCH LLC",
                    "USE_CODE": "01",
                    "BLDG_YEAR_BUILT": 1954,
                    "BLDG_ADJ_SQ_FOOTAGE": 1450.0,
                    "UNDER_AIR_SQFT": "1300",
                    "JUST_BUILDING_VALUE": 250000,
                },
                "geometry": {"x": -80.128145, "y": 26.129402},
            },
        ]
        parcel_features = [{"attributes": {"FOLIO": "494234120010", "SHAPE.STArea()": 8000.0}}]

        async def mock_arcgis(url, **kwargs):
            if "MapServer/16" in url:
                return parcel_features
            return property_features

        with (
            patch("plotlot.retrieval.property._query_arcgis", side_effect=mock_arcgis),
            patch(
                "plotlot.retrieval.property._spatial_query_zoning",
                return_value=("RS-8", "Residential Single Family"),
            ),
        ):
            result = await lookup_property(
                "1517 NE 5th Ct, Fort Lauderdale, FL 33301",
                county="Broward",
                lat=26.129402,
                lng=-80.128145,
            )

        assert result is not None
        assert result.municipality == "Fort Lauderdale"

    @pytest.mark.asyncio
    async def test_broward_falls_back_to_spatial_parcel_record_when_address_record_missing(self):
        property_features: list[dict] = []
        parcel_features = [
            {
                "attributes": {
                    "FOLIO": "494233281490",
                    "SHAPE.STArea()": 10687.23,
                },
                "geometry": {
                    "rings": [[[-80.16, 26.145], [-80.159, 26.145], [-80.159, 26.146], [-80.16, 26.145]]]
                },
            }
        ]

        async def mock_arcgis(url, **kwargs):
            if "MapServer/16" in url:
                return parcel_features
            return property_features

        with (
            patch("plotlot.retrieval.property._query_arcgis", side_effect=mock_arcgis),
            patch(
                "plotlot.retrieval.property._spatial_query_zoning",
                return_value=("RS-8", "Residential Single Family"),
            ),
        ):
            result = await lookup_property(
                "1234 NW 15th St, Fort Lauderdale, FL 33311",
                county="Broward",
                lat=26.145103,
                lng=-80.159491,
            )

        assert result is not None
        assert result.folio == "494233281490"
        assert result.address == "1234 NW 15TH ST"
        assert result.municipality == "Fort Lauderdale"
        assert result.zoning_code == "RS-8"
        assert result.lot_size_sqft == pytest.approx(10687.23)
        assert result.lot_size_source == "geometry"

    @pytest.mark.asyncio
    async def test_broward_falls_back_to_spatial_parcel_record_when_text_match_is_wrong(self):
        property_features = [
            {
                "attributes": {
                    "FOLIO_NUMBER": "504210060000",
                    "SITUS_STREET_NUMBER": "101",
                    "SITUS_STREET_DIRECTION": "SE",
                    "SITUS_STREET_NAME": "15",
                    "SITUS_STREET_TYPE": "AVE",
                    "SITUS_CITY": "FL",
                },
                "geometry": {"x": -80.14231, "y": 26.121551},
            }
        ]
        parcel_features = [
            {
                "attributes": {
                    "FOLIO": "504210060000",
                    "SHAPE.STArea()": 26244.77,
                },
                "geometry": {
                    "rings": [[[-80.143, 26.121], [-80.142, 26.121], [-80.142, 26.122], [-80.143, 26.121]]]
                },
            }
        ]

        async def mock_arcgis(url, **kwargs):
            if "MapServer/16" in url:
                return parcel_features
            return property_features

        with (
            patch("plotlot.retrieval.property._query_arcgis", side_effect=mock_arcgis),
            patch(
                "plotlot.retrieval.property._spatial_query_zoning",
                return_value=("RAC-CC", ""),
            ),
        ):
            result = await lookup_property(
                "101 SE 1st Ave, Fort Lauderdale, FL 33301",
                county="Broward",
                lat=26.121551,
                lng=-80.14231,
            )

        assert result is not None
        assert result.address == "101 SE 1ST AVE"
        assert result.municipality == "Fort Lauderdale"
        assert result.zoning_code == "RAC-CC"
        assert result.lot_size_source == "geometry"

    @pytest.mark.asyncio
    async def test_not_found(self):
        with patch("plotlot.retrieval.property._query_arcgis", return_value=[]):
            result = await lookup_property(
                "999 Nonexistent St",
                county="Miami-Dade",
                lat=25.7,
                lng=-80.2,
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_unsupported_county(self):
        result = await lookup_property("123 Main St", county="Monroe")
        assert result is None

    @pytest.mark.asyncio
    async def test_api_error_returns_none(self):
        with patch("plotlot.retrieval.property._query_arcgis", side_effect=Exception("API down")):
            result = await lookup_property(
                "171 NE 209th Ter",
                county="Miami-Dade",
                lat=25.9,
                lng=-80.1,
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_miami_dade_municipal_zoning_fallback(self):
        """Municipal zoning layer returns zone for incorporated cities."""
        mock_features = [
            {
                "attributes": {
                    "FOLIO": "12345",
                    "TRUE_SITE_ADDR": "100 NW 1 AVE",
                    "TRUE_SITE_CITY": "MIAMI GARDENS",
                    "TRUE_OWNER1": "OWNER",
                    "LOT_SIZE": 5000.0,
                    "YEAR_BUILT": 2000,
                    "LEGAL": "",
                },
                "geometry": {"x": -80.225, "y": 25.942},
            }
        ]

        # Municipal layer returns "GP", unincorporated would return empty
        async def mock_zoning(url, lat, lng):
            if "MapServer/2" in url:
                return ("GP", "")
            return ("", "")

        with (
            patch("plotlot.retrieval.property._query_arcgis", return_value=mock_features),
            patch("plotlot.retrieval.property._spatial_query_zoning", side_effect=mock_zoning),
        ):
            result = await lookup_property(
                "100 NW 1st Ave, Miami Gardens, FL",
                county="Miami-Dade",
                lat=25.942,
                lng=-80.225,
            )

        assert result is not None
        assert result.zoning_code == "GP"
        assert result.municipality == "MIAMI GARDENS"

    @pytest.mark.asyncio
    async def test_miami_dade_unincorporated_zoning_fallback(self):
        """Falls back to unincorporated layer when municipal returns NONE."""
        mock_features = [
            {
                "attributes": {
                    "FOLIO": "67890",
                    "TRUE_SITE_ADDR": "200 SW 2 ST",
                    "TRUE_SITE_CITY": "UNINCORPORATED",
                    "TRUE_OWNER1": "OWNER",
                    "LOT_SIZE": 7000.0,
                    "YEAR_BUILT": 1985,
                    "LEGAL": "",
                },
                "geometry": {"x": -80.3, "y": 25.8},
            }
        ]

        # Municipal layer returns NONE, unincorporated returns real zone
        async def mock_zoning(url, lat, lng):
            if "MapServer/2" in url:
                return ("NONE", "")
            return ("RU-1", "Single Family Residential")

        with (
            patch("plotlot.retrieval.property._query_arcgis", return_value=mock_features),
            patch("plotlot.retrieval.property._spatial_query_zoning", side_effect=mock_zoning),
        ):
            result = await lookup_property(
                "200 SW 2nd St, Miami, FL",
                county="Miami-Dade",
                lat=25.8,
                lng=-80.3,
            )

        assert result is not None
        assert result.zoning_code == "RU-1"
        assert result.zoning_description == "Single Family Residential"

    @pytest.mark.asyncio
    async def test_lookup_recovers_miami_dade_false_positive_with_spatial_boundary_fallback(self):
        point_features = [
            {
                "attributes": {
                    "FOLIO": "3021350080310",
                    "TRUE_SITE_ADDR": "11600 NW 7 AVE",
                    "TRUE_SITE_CITY": "UNINCORPORATED",
                    "TRUE_OWNER1": "OWNER",
                    "LOT_SIZE": 14175.0,
                    "YEAR_BUILT": 1957,
                    "LEGAL": "",
                },
                "geometry": {"x": -80.20681, "y": 25.790642},
            }
        ]
        polygon_features = [
            {
                "attributes": {
                    "FOLIO": "0131360600010",
                    "TRUE_SITE_ADDR": "1603 NW 7 AVE",
                    "TRUE_SITE_CITY": "Miami",
                    "TRUE_OWNER1": "OWNER",
                    "LEGAL": "",
                    "Shape.STArea()": 149287.34,
                },
                "geometry": {
                    "rings": [
                        [[-80.2061, 25.7914], [-80.2061, 25.7901], [-80.2060, 25.7901], [-80.2061, 25.7914]]
                    ]
                },
            }
        ]

        async def mock_query(url, where, out_fields="*", extra_params=None, limit=5):
            if "MD_ZoningLandManagementViewer/MapServer/2/query" in url:
                return polygon_features
            return point_features

        with (
            patch("plotlot.retrieval.property._query_arcgis", side_effect=mock_query),
            patch(
                "plotlot.retrieval.property._spatial_query_zoning",
                return_value=("CI-HD", ""),
            ),
        ):
            result = await lookup_property(
                "1600 NW 7th Ave, Miami, FL 33136",
                county="Miami-Dade",
                lat=25.790642,
                lng=-80.20681,
            )

        assert result is not None
        assert result.folio == "0131360600010"
        assert result.address == "1603 NW 7 AVE"
        assert result.lot_size_source == "geometry"


class TestCaliforniaCountyRouting:
    """Regression: CA counties without a dedicated registration must reach the
    CaliforniaProvider (statewide parcel layer), not the generic UniversalProvider.

    Marin (Sausalito / Tiburon) reported "not found" in production because
    get_provider("marin") routed it to UniversalProvider — which misses Bay Area
    parcels — even though 416 Richardson St (APN 065-234-10) exists in the CA
    statewide parcel layer. Ingesting Marin's ordinances does not create a parcel
    provider; routing does.
    """

    @pytest.mark.asyncio
    async def test_unregistered_ca_county_routes_to_california_provider(self):
        sentinel = PropertyRecord(
            folio="065-234-10",
            address="416 RICHARDSON ST",
            county="Marin",
            lot_size_sqft=765.0,
        )
        with (
            patch.object(
                CaliforniaProvider, "lookup", new_callable=AsyncMock, return_value=sentinel
            ) as mock_ca,
            patch("plotlot.property.registry.get_provider") as mock_get_provider,
        ):
            result = await lookup_property(
                "416 Richardson St, Sausalito, CA",
                county="Marin",
                lat=37.8500,
                lng=-122.4823,
                state="CA",
            )

        assert result is sentinel
        mock_ca.assert_awaited_once()
        # Must NOT fall through to the generic registry/UniversalProvider path.
        mock_get_provider.assert_not_called()

    @pytest.mark.asyncio
    async def test_registered_ca_county_still_uses_registry(self):
        """San Diego is registered, so it keeps using the registry path."""
        sentinel = PropertyRecord(folio="X", address="1233 Hueneme St", county="San Diego")
        mock_provider = AsyncMock()
        mock_provider.lookup = AsyncMock(return_value=sentinel)
        with patch(
            "plotlot.property.registry.get_provider", return_value=mock_provider
        ) as mock_get_provider:
            result = await lookup_property(
                "1233 Hueneme St, San Diego, CA",
                county="San Diego",
                lat=32.7574,
                lng=-117.2042,
                state="CA",
            )

        mock_get_provider.assert_called_once_with("San Diego")
        assert result is sentinel

    @pytest.mark.asyncio
    async def test_non_ca_county_does_not_route_to_california(self):
        """A non-CA unregistered county keeps the generic registry path."""
        mock_provider = AsyncMock()
        mock_provider.lookup = AsyncMock(return_value=None)
        with (
            patch(
                "plotlot.property.registry.get_provider", return_value=mock_provider
            ) as mock_get_provider,
            patch.object(CaliforniaProvider, "lookup", new_callable=AsyncMock) as mock_ca,
        ):
            result = await lookup_property(
                "100 Congress Ave, Austin, TX",
                county="Travis",
                lat=30.2672,
                lng=-97.7431,
                state="TX",
            )

        mock_get_provider.assert_called_once_with("Travis")
        mock_ca.assert_not_awaited()
        assert result is None

    @pytest.mark.asyncio
    async def test_ca_routing_requires_state(self):
        """Without state, county alone can't be known as CA — registry path is used.
        All real callers pass state from the geocoder, so this documents the contract."""
        mock_provider = AsyncMock()
        mock_provider.lookup = AsyncMock(return_value=None)
        with (
            patch(
                "plotlot.property.registry.get_provider", return_value=mock_provider
            ) as mock_get_provider,
            patch.object(CaliforniaProvider, "lookup", new_callable=AsyncMock) as mock_ca,
        ):
            await lookup_property("416 Richardson St", county="Marin", lat=37.85, lng=-122.48)

        mock_get_provider.assert_called_once_with("Marin")
        mock_ca.assert_not_awaited()
