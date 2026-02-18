"""Unit tests for bulk property search module.

Tests the WHERE clause builder, safe filter parser, record normalization,
and paginated search (all with mocked ArcGIS calls).
"""

from unittest.mock import AsyncMock, patch

import pytest

from plotlot.retrieval.bulk_search import (
    MDC_FIELDS,
    PBC_FIELDS,
    BROWARD_FIELDS,
    DatasetInfo,
    PropertySearchParams,
    build_where_clause,
    bulk_property_search,
    compute_dataset_stats,
    describe_search,
    _normalize_record,
    _safe_filter,
)


# ---------------------------------------------------------------------------
# WHERE clause builder
# ---------------------------------------------------------------------------


class TestBuildWhereClause:
    def test_vacant_residential_mdc(self):
        """Vacant residential in Miami-Dade uses DOR_CODE_CUR='0000'."""
        params = PropertySearchParams(county="Miami-Dade", land_use_type="vacant_residential")
        where, fm = build_where_clause(params)
        assert "DOR_CODE_CUR" in where
        assert "'0000'" in where
        assert fm.county_name == "Miami-Dade"

    def test_vacant_commercial_mdc(self):
        """Vacant commercial in Miami-Dade uses DOR_CODE_CUR='0100'."""
        params = PropertySearchParams(county="Miami-Dade", land_use_type="vacant_commercial")
        where, _ = build_where_clause(params)
        assert "'0100'" in where

    def test_ownership_duration_mdc(self):
        """Ownership filter converts ISO date to MDC's YYYYMMDD string format."""
        params = PropertySearchParams(county="Miami-Dade", max_sale_date="2006-01-01")
        where, _ = build_where_clause(params)
        assert "DOS_1" in where
        assert "'20060101'" in where

    def test_combined_filters(self):
        """Multiple filters joined with AND."""
        params = PropertySearchParams(
            county="Miami-Dade",
            land_use_type="vacant_residential",
            city="MIAMI GARDENS",
            max_sale_date="2006-01-01",
        )
        where, _ = build_where_clause(params)
        assert " AND " in where
        assert "DOR_CODE_CUR" in where
        assert "TRUE_SITE_CITY" in where
        assert "DOS_1" in where

    def test_lot_size_pbc_converts_to_acres(self):
        """Palm Beach lot size filter converts sqft to acres."""
        params = PropertySearchParams(county="Palm Beach", min_lot_size_sqft=43560)
        where, _ = build_where_clause(params)
        assert "ACRES" in where
        assert "1.0000" in where  # 43560 sqft = 1.0 acre

    def test_sale_date_pbc_epoch_ms(self):
        """Palm Beach sale date filter uses epoch milliseconds."""
        params = PropertySearchParams(county="Palm Beach", max_sale_date="2006-01-01")
        where, _ = build_where_clause(params)
        assert "SALE_DATE" in where
        # Should be a large number (epoch ms)
        assert "<" in where

    def test_empty_params_returns_1_eq_1(self):
        """No filters → WHERE 1=1."""
        params = PropertySearchParams(county="Miami-Dade")
        where, _ = build_where_clause(params)
        assert where == "1=1"

    def test_unsupported_county_raises(self):
        """Unsupported county raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported county"):
            build_where_clause(PropertySearchParams(county="Monroe"))

    def test_owner_name_filter(self):
        """Owner name filter uses LIKE with uppercase."""
        params = PropertySearchParams(county="Miami-Dade", owner_name_contains="john doe")
        where, _ = build_where_clause(params)
        assert "TRUE_OWNER1 LIKE '%JOHN DOE%'" in where

    def test_year_built_before(self):
        """Year built before filter."""
        params = PropertySearchParams(county="Miami-Dade", year_built_before=1)
        where, _ = build_where_clause(params)
        assert "YEAR_BUILT<1" in where

    def test_assessed_value_range(self):
        """Assessed value range filter."""
        params = PropertySearchParams(
            county="Miami-Dade",
            min_assessed_value=50000,
            max_assessed_value=200000,
        )
        where, _ = build_where_clause(params)
        assert "ASSESSED_VAL_CUR>=50000" in where
        assert "ASSESSED_VAL_CUR<=200000" in where

    def test_broward_needs_order_by(self):
        """Broward field map has needs_order_by flag."""
        params = PropertySearchParams(county="Broward", land_use_type="vacant_residential")
        _, fm = build_where_clause(params)
        assert fm.needs_order_by is True
        assert fm.order_by_field == "FOLIO_NUMBER"

    def test_broward_city_code_translation(self):
        """Broward city names translate to 2-letter codes."""
        params = PropertySearchParams(county="Broward", city="Miramar")
        where, _ = build_where_clause(params)
        assert "SITUS_CITY='MM'" in where

    def test_broward_city_code_direct(self):
        """Broward 2-letter city codes pass through directly."""
        params = PropertySearchParams(county="Broward", city="FL")
        where, _ = build_where_clause(params)
        assert "SITUS_CITY='FL'" in where

    def test_multifamily_mdc_in_clause(self):
        """Multiple land use codes produce IN clause."""
        params = PropertySearchParams(county="Miami-Dade", land_use_type="multifamily")
        where, _ = build_where_clause(params)
        assert "DOR_CODE_CUR IN (" in where
        assert "'0104'" in where


# ---------------------------------------------------------------------------
# Safe filter parser
# ---------------------------------------------------------------------------


class TestSafeFilter:
    def test_numeric_greater_than(self):
        records = [{"lot_size_sqft": 5000}, {"lot_size_sqft": 15000}]
        result = _safe_filter(records, "lot_size_sqft > 10000")
        assert len(result) == 1
        assert result[0]["lot_size_sqft"] == 15000

    def test_string_equality(self):
        records = [{"city": "MIAMI"}, {"city": "MIRAMAR"}]
        result = _safe_filter(records, "city == 'MIAMI'")
        assert len(result) == 1
        assert result[0]["city"] == "MIAMI"

    def test_case_insensitive_string(self):
        records = [{"city": "MIAMI GARDENS"}, {"city": "MIRAMAR"}]
        result = _safe_filter(records, "city == 'miami gardens'")
        assert len(result) == 1

    def test_combined_and(self):
        records = [
            {"lot_size_sqft": 15000, "city": "MIAMI"},
            {"lot_size_sqft": 15000, "city": "MIRAMAR"},
            {"lot_size_sqft": 5000, "city": "MIAMI"},
        ]
        result = _safe_filter(records, "lot_size_sqft > 10000 and city == 'MIAMI'")
        assert len(result) == 1

    def test_invalid_expression_returns_all(self):
        records = [{"a": 1}]
        result = _safe_filter(records, "invalid garbage!!!")
        assert result == records

    def test_contains_operator(self):
        records = [{"owner": "JOHN DOE"}, {"owner": "JANE SMITH"}]
        result = _safe_filter(records, "owner contains 'john'")
        assert len(result) == 1
        assert result[0]["owner"] == "JOHN DOE"

    def test_less_than_or_equal(self):
        records = [{"assessed_value": 50000}, {"assessed_value": 100000}, {"assessed_value": 200000}]
        result = _safe_filter(records, "assessed_value <= 100000")
        assert len(result) == 2

    def test_not_equal(self):
        records = [{"city": "MIAMI"}, {"city": "MIRAMAR"}, {"city": "MIAMI"}]
        result = _safe_filter(records, "city != 'MIAMI'")
        assert len(result) == 1

    def test_empty_expression_returns_all(self):
        records = [{"a": 1}, {"a": 2}]
        result = _safe_filter(records, "")
        assert len(result) == 2

    def test_missing_field_excludes_record(self):
        records = [{"lot_size_sqft": 5000}, {"city": "MIAMI"}]
        result = _safe_filter(records, "lot_size_sqft > 3000")
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Record normalization
# ---------------------------------------------------------------------------


class TestNormalizeRecord:
    def test_mdc_normalization(self):
        """MDC raw attributes normalize to standard schema."""
        attrs = {
            "FOLIO": "3422120000010",
            "TRUE_SITE_ADDR": "171 NE 209 TER",
            "TRUE_SITE_CITY": "MIAMI GARDENS",
            "TRUE_OWNER1": "JOHN DOE",
            "DOR_CODE_CUR": "0000",
            "LOT_SIZE": 7500.0,
            "YEAR_BUILT": 0,
            "ASSESSED_VAL_CUR": 50000.0,
            "PRICE_1": 25000.0,
            "DOS_1": "01/15/2000",
        }
        result = _normalize_record(attrs, {"x": -80.199, "y": 25.957}, MDC_FIELDS)
        assert result["folio"] == "3422120000010"
        assert result["address"] == "171 NE 209 TER"
        assert result["city"] == "MIAMI GARDENS"
        assert result["county"] == "Miami-Dade"
        assert result["owner"] == "JOHN DOE"
        assert result["lot_size_sqft"] == 7500.0
        assert result["year_built"] == 0
        assert result["assessed_value"] == 50000.0
        assert result["last_sale_price"] == 25000.0
        assert result["last_sale_date"] == "01/15/2000"
        assert result["lat"] == 25.957
        assert result["lng"] == -80.199

    def test_pbc_acres_to_sqft(self):
        """PBC ACRES field converts to sqft."""
        attrs = {
            "PARCEL_NUMBER": "123",
            "SITE_ADDR_STR": "100 MAIN ST",
            "MUNICIPALITY": "WEST PALM BEACH",
            "OWNER_NAME1": "JANE",
            "PROPERTY_USE": "00",
            "YRBLT": "0",
            "ACRES": 0.5,
            "ASSESSED_VAL": 100000,
            "PRICE": 80000,
            "SALE_DATE": 1136073600000,  # 2006-01-01 UTC
        }
        result = _normalize_record(attrs, None, PBC_FIELDS)
        assert result["lot_size_sqft"] == pytest.approx(21780.0, rel=0.01)
        assert "2006" in result["last_sale_date"]
        assert result["lat"] is None

    def test_broward_composite_address(self):
        """Broward address assembled from components."""
        attrs = {
            "FOLIO_NUMBER": "504210230010",
            "SITUS_STREET_NUMBER": "7940",
            "SITUS_STREET_DIRECTION": "W",
            "SITUS_STREET_NAME": "PLANTATION",
            "SITUS_STREET_TYPE": "BLVD",
            "SITUS_CITY": "PLANTATION",
            "NAME_LINE_1": "OWNER LLC",
            "USE_CODE": "01",
            "BLDG_YEAR_BUILT": 1985,
            "JUST_BUILDING_VALUE": 250000,
        }
        result = _normalize_record(attrs, {"x": -80.3, "y": 26.1}, BROWARD_FIELDS)
        assert "7940" in result["address"]
        assert "PLANTATION" in result["address"]
        assert result["county"] == "Broward"
        assert result["lat"] == 26.1

    def test_missing_geometry(self):
        """Missing geometry produces None lat/lng."""
        attrs = {"FOLIO": "123", "TRUE_SITE_ADDR": "A", "TRUE_SITE_CITY": "B",
                 "TRUE_OWNER1": "C", "DOR_CODE_CUR": "0000", "LOT_SIZE": 0,
                 "YEAR_BUILT": 0, "ASSESSED_VAL_CUR": 0, "PRICE_1": 0, "DOS_1": ""}
        result = _normalize_record(attrs, None, MDC_FIELDS)
        assert result["lat"] is None
        assert result["lng"] is None


# ---------------------------------------------------------------------------
# Paginated bulk search (mocked)
# ---------------------------------------------------------------------------


class TestBulkPropertySearch:
    @pytest.mark.asyncio
    async def test_single_page_results(self):
        """Single page of results returned and normalized."""
        mock_features = [
            {
                "attributes": {
                    "FOLIO": f"F{i}",
                    "TRUE_SITE_ADDR": f"{i} MAIN ST",
                    "TRUE_SITE_CITY": "MIAMI",
                    "TRUE_OWNER1": "OWNER",
                    "DOR_CODE_CUR": "0000",
                    "LOT_SIZE": 7500,
                    "YEAR_BUILT": 0,
                    "ASSESSED_VAL_CUR": 50000,
                    "PRICE_1": 25000,
                    "DOS_1": "01/01/2000",
                },
                "geometry": {"x": -80.2, "y": 25.9},
            }
            for i in range(50)
        ]
        with patch("plotlot.retrieval.bulk_search._query_arcgis", new_callable=AsyncMock, return_value=mock_features):
            results = await bulk_property_search(
                PropertySearchParams(county="Miami-Dade", land_use_type="vacant_residential")
            )
        assert len(results) == 50
        assert results[0]["folio"] == "F0"
        assert results[0]["county"] == "Miami-Dade"

    @pytest.mark.asyncio
    async def test_max_results_cap(self):
        """Respects max_results even if more data available."""
        mock_features = [
            {
                "attributes": {
                    "FOLIO": f"F{i}", "TRUE_SITE_ADDR": f"{i} ST",
                    "TRUE_SITE_CITY": "MIAMI", "TRUE_OWNER1": "O",
                    "DOR_CODE_CUR": "0000", "LOT_SIZE": 0, "YEAR_BUILT": 0,
                    "ASSESSED_VAL_CUR": 0, "PRICE_1": 0, "DOS_1": "",
                },
                "geometry": None,
            }
            for i in range(200)
        ]
        with patch("plotlot.retrieval.bulk_search._query_arcgis", new_callable=AsyncMock, return_value=mock_features):
            results = await bulk_property_search(
                PropertySearchParams(county="Miami-Dade", max_results=100)
            )
        assert len(results) <= 100

    @pytest.mark.asyncio
    async def test_empty_results(self):
        """No results returns empty list."""
        with patch("plotlot.retrieval.bulk_search._query_arcgis", new_callable=AsyncMock, return_value=[]):
            results = await bulk_property_search(
                PropertySearchParams(county="Miami-Dade", land_use_type="vacant_residential")
            )
        assert results == []

    @pytest.mark.asyncio
    async def test_api_error_returns_partial(self):
        """API error mid-pagination returns what we have so far."""
        page1 = [
            {
                "attributes": {
                    "FOLIO": f"F{i}", "TRUE_SITE_ADDR": f"{i} ST",
                    "TRUE_SITE_CITY": "MIAMI", "TRUE_OWNER1": "O",
                    "DOR_CODE_CUR": "0000", "LOT_SIZE": 0, "YEAR_BUILT": 0,
                    "ASSESSED_VAL_CUR": 0, "PRICE_1": 0, "DOS_1": "",
                },
                "geometry": None,
            }
            for i in range(10)
        ]

        call_count = 0
        async def mock_arcgis(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return page1
            raise RuntimeError("API down")

        with patch("plotlot.retrieval.bulk_search._query_arcgis", side_effect=mock_arcgis):
            results = await bulk_property_search(
                PropertySearchParams(county="Miami-Dade", max_results=2000)
            )
        assert len(results) == 10


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


class TestUtilities:
    def test_compute_stats(self):
        records = [
            {"lot_size_sqft": 5000, "assessed_value": 50000, "city": "MIAMI", "last_sale_price": 0, "year_built": 0},
            {"lot_size_sqft": 15000, "assessed_value": 150000, "city": "MIRAMAR", "last_sale_price": 0, "year_built": 0},
        ]
        stats = compute_dataset_stats(records)
        assert stats["count"] == 2
        assert stats["lot_size_sqft"]["min"] == 5000
        assert stats["lot_size_sqft"]["max"] == 15000
        assert "MIAMI" in stats["unique_cities"]

    def test_compute_stats_empty(self):
        assert compute_dataset_stats([])["count"] == 0

    def test_describe_search(self):
        desc = describe_search({
            "county": "Miami-Dade",
            "land_use_type": "vacant_residential",
            "ownership_min_years": 20,
        })
        assert "Miami-Dade" in desc
        assert "Vacant Residential" in desc
        assert "20" in desc
