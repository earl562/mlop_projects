"""Tests for comparable sales pipeline step."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import httpx
import pytest

from plotlot.core.types import CompAnalysis, ComparableSale, PropertyRecord
from plotlot.pipeline.comps import (
    _address_sort_penalty,
    _apply_identifier_address_penalty,
    _clean_comp_address,
    _classify_improved,
    _filter_vacant_single_family_land_comps,
    _filter_vacant_single_family_unit_comps,
    _feature_latlng,
    _haversine_miles,
    _is_arms_length,
    _municipality_is_comparable,
    _municipality_comparability_status,
    _parse_sale_date,
    _percentile,
    _polygon_area_sqft,
    _price_range,
    _query_nearby_sales,
    _resolved_comp_address,
    _sales_query_limit,
    _score_confidence,
    _vacant_land_sales_where_clause,
    _within_months,
    _zoning_is_comparable,
    _zoning_comparability_status,
    find_comparables,
)


class TestHaversine:
    def test_same_point_zero_distance(self):
        assert _haversine_miles(25.0, -80.0, 25.0, -80.0) == 0.0

    def test_known_distance(self):
        # Miami to Fort Lauderdale ~28 miles
        dist = _haversine_miles(25.7617, -80.1918, 26.1224, -80.1373)
        assert 24 < dist < 32


class TestArmsLength:
    def test_zero_not_arms_length(self):
        assert not _is_arms_length(0)

    def test_hundred_not_arms_length(self):
        assert not _is_arms_length(100)

    def test_normal_price_is_arms_length(self):
        assert _is_arms_length(150_000)


class TestParseSaleDate:
    def test_epoch_ms(self):
        # 2024-01-15 in epoch ms
        result = _parse_sale_date(1705276800000)
        assert result.startswith("2024-01-1")

    def test_string_date(self):
        assert _parse_sale_date("2024-03-15") == "2024-03-15"

    def test_none(self):
        assert _parse_sale_date(None) == ""


class TestPercentile:
    def test_empty(self):
        assert _percentile([], 50) == 0.0

    def test_single(self):
        assert _percentile([42.0], 25) == 42.0

    def test_median_even(self):
        assert _percentile([10.0, 20.0, 30.0, 40.0], 50) == 25.0

    def test_quartiles(self):
        vals = [100.0, 200.0, 300.0, 400.0, 500.0]
        assert _percentile(vals, 25) == 200.0
        assert _percentile(vals, 50) == 300.0
        assert _percentile(vals, 75) == 400.0


class TestPriceRange:
    def test_returns_p25_median_p75(self):
        low, median, high = _price_range([500.0, 100.0, 300.0, 400.0, 200.0])
        assert low == 200.0
        assert median == 300.0
        assert high == 400.0

    def test_ignores_nonpositive(self):
        low, median, high = _price_range([0.0, -5.0, 100.0])
        assert median == 100.0
        assert low == high == 100.0

    def test_empty(self):
        assert _price_range([]) == (0.0, 0.0, 0.0)


class TestWithinMonths:
    def test_recent_sale_passes(self):
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        assert _within_months("2026-03-01", 12, now)

    def test_old_sale_excluded(self):
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        assert not _within_months("2020-01-01", 12, now)

    def test_missing_date_not_excluded(self):
        assert _within_months("", 12)

    def test_unparseable_date_not_excluded(self):
        assert _within_months("not-a-date", 12)


class TestClassifyImproved:
    def test_vacant_land_no_signals(self):
        improved, units = _classify_improved({}, "UNITS", "BLDG", "YR", "IMP")
        assert improved is False
        assert units == 0

    def test_building_area_marks_improved_single_unit(self):
        attrs = {"BLDG": "1800"}
        improved, units = _classify_improved(attrs, None, "BLDG", None, None)
        assert improved is True
        assert units == 1

    def test_explicit_unit_count(self):
        attrs = {"UNITS": "6", "BLDG": "8000"}
        improved, units = _classify_improved(attrs, "UNITS", "BLDG", None, None)
        assert improved is True
        assert units == 6


class TestMunicipalityComparable:
    def test_matches_same_city(self):
        assert _municipality_is_comparable("Miami Gardens", "Miami Gardens")

    def test_rejects_different_city(self):
        assert not _municipality_is_comparable("Miami Gardens", "Aventura")

    def test_marks_blank_city_as_unknown_not_match(self):
        assert _municipality_comparability_status("Miami Gardens", "") == "unknown"
        assert not _municipality_is_comparable("Miami Gardens", "")


class TestCompAddressQuality:
    def test_identifier_addresses_sort_after_street_addresses(self):
        assert _address_sort_penalty("17605 NW 19 AVE") == 0
        assert _address_sort_penalty("3421100011870") == 1

    def test_identifier_addresses_receive_small_quality_penalty(self):
        assert _apply_identifier_address_penalty(0.65, "3421100011870") == pytest.approx(0.62)
        assert _apply_identifier_address_penalty(0.65, "17605 NW 19 AVE") == pytest.approx(0.65)


class TestVacantSingleFamilyLandCompFilter:
    def test_filters_land_sales_above_finished_home_pricing_band(self):
        subject = PropertyRecord(
            county="Miami-Dade",
            zoning_code="R-1",
            land_use_description="VACANT RESIDENTIAL",
            lot_size_sqft=10105,
        )
        land_comps = [
            ComparableSale(address="High Lot", sale_price=900000.0, lot_size_sqft=11250.0, price_per_acre=3484800.0),
            ComparableSale(address="Reasonable Lot", sale_price=145000.0, lot_size_sqft=9500.0, price_per_acre=665789.47),
        ]
        unit_comps = [
            ComparableSale(address="Exit 1", sale_price=505000.0, price_per_unit=505000.0),
            ComparableSale(address="Exit 2", sale_price=489000.0, price_per_unit=489000.0),
            ComparableSale(address="Exit 3", sale_price=475000.0, price_per_unit=475000.0),
        ]

        filtered, rejected = _filter_vacant_single_family_land_comps(subject, land_comps, unit_comps)

        assert [comp.address for comp in filtered] == ["Reasonable Lot"]
        assert [comp.address for comp in rejected] == ["High Lot"]

    def test_returns_empty_when_all_land_sales_exceed_finished_home_pricing_band(self):
        subject = PropertyRecord(
            county="Miami-Dade",
            zoning_code="R-1",
            land_use_description="VACANT RESIDENTIAL",
            lot_size_sqft=10105,
        )
        land_comps = [
            ComparableSale(address="High Lot 1", sale_price=900000.0, lot_size_sqft=11250.0, price_per_acre=3484800.0),
            ComparableSale(address="High Lot 2", sale_price=725000.0, lot_size_sqft=11025.0, price_per_acre=2864489.8),
        ]
        unit_comps = [
            ComparableSale(address="Exit 1", sale_price=505000.0, price_per_unit=505000.0),
            ComparableSale(address="Exit 2", sale_price=489000.0, price_per_unit=489000.0),
            ComparableSale(address="Exit 3", sale_price=475000.0, price_per_unit=475000.0),
        ]

        filtered, rejected = _filter_vacant_single_family_land_comps(subject, land_comps, unit_comps)

        assert filtered == []
        assert [comp.address for comp in rejected] == ["High Lot 1", "High Lot 2"]

    def test_prefers_nearby_local_land_comp_cluster(self):
        subject = PropertyRecord(
            county="Miami-Dade",
            municipality="Miami Gardens",
            zoning_code="R-1",
            land_use_description="VACANT RESIDENTIAL",
            lot_size_sqft=10105,
        )
        land_comps = [
            ComparableSale(
                address="Nearby Lot 1",
                sale_price=145000.0,
                lot_size_sqft=9500.0,
                distance_miles=0.32,
                price_per_acre=665789.47,
            ),
            ComparableSale(
                address="Nearby Lot 2",
                sale_price=138000.0,
                lot_size_sqft=9100.0,
                distance_miles=0.41,
                price_per_acre=660494.51,
            ),
            ComparableSale(
                address="Farther Lot",
                sale_price=152000.0,
                lot_size_sqft=9700.0,
                distance_miles=4.25,
                price_per_acre=682846.39,
            ),
        ]
        unit_comps = [
            ComparableSale(address="Exit 1", sale_price=505000.0, price_per_unit=505000.0),
            ComparableSale(address="Exit 2", sale_price=489000.0, price_per_unit=489000.0),
        ]

        filtered, rejected = _filter_vacant_single_family_land_comps(subject, land_comps, unit_comps)

        assert [comp.address for comp in filtered] == ["Nearby Lot 1", "Nearby Lot 2"]
        assert rejected == []

    def test_year_built_marks_improved(self):
        attrs = {"YR": "1998"}
        improved, units = _classify_improved(attrs, None, None, "YR", None)
        assert improved is True


class TestVacantSingleFamilyUnitCompFilter:
    def test_prefers_recent_new_build_exit_comps_when_two_or_more_exist(self):
        subject = PropertyRecord(
            county="Miami-Dade",
            municipality="Miami Gardens",
            zoning_code="R-1",
            land_use_description="VACANT RESIDENTIAL",
            lot_size_sqft=10105,
        )
        unit_comps = [
            ComparableSale(
                address="Recent Build 1",
                sale_price=699000.0,
                lot_size_sqft=7500.0,
                price_per_unit=699000.0,
                adjustments={"year_built": 2025.0},
            ),
            ComparableSale(
                address="Recent Build 2",
                sale_price=705000.0,
                lot_size_sqft=7600.0,
                price_per_unit=705000.0,
                adjustments={"year_built": 2026.0},
            ),
            ComparableSale(
                address="Older Renovation 1",
                sale_price=505000.0,
                lot_size_sqft=3007.0,
                price_per_unit=505000.0,
                adjustments={"year_built": 1980.0},
            ),
            ComparableSale(
                address="Older Renovation 2",
                sale_price=465000.0,
                lot_size_sqft=3023.0,
                price_per_unit=465000.0,
                adjustments={"year_built": 1985.0},
            ),
        ]

        filtered = _filter_vacant_single_family_unit_comps(subject, unit_comps)

        assert [comp.address for comp in filtered] == ["Recent Build 1", "Recent Build 2"]

    def test_keeps_older_exit_comps_when_recent_new_build_set_is_too_thin(self):
        subject = PropertyRecord(
            county="Miami-Dade",
            municipality="Miami Gardens",
            zoning_code="R-1",
            land_use_description="VACANT RESIDENTIAL",
            lot_size_sqft=10105,
        )
        unit_comps = [
            ComparableSale(
                address="Recent Build 1",
                sale_price=699000.0,
                lot_size_sqft=7500.0,
                price_per_unit=699000.0,
                adjustments={"year_built": 2025.0},
            ),
            ComparableSale(
                address="Older Renovation 1",
                sale_price=505000.0,
                lot_size_sqft=3007.0,
                price_per_unit=505000.0,
                adjustments={"year_built": 1980.0},
            ),
            ComparableSale(
                address="Older Renovation 2",
                sale_price=465000.0,
                lot_size_sqft=3023.0,
                price_per_unit=465000.0,
                adjustments={"year_built": 1985.0},
            ),
        ]

        filtered = _filter_vacant_single_family_unit_comps(subject, unit_comps)

        assert [comp.address for comp in filtered] == [
            "Recent Build 1",
            "Older Renovation 1",
            "Older Renovation 2",
        ]

    def test_rejects_recent_new_builds_with_noncomparable_lot_sizes(self):
        subject = PropertyRecord(
            county="Miami-Dade",
            municipality="Miami Gardens",
            zoning_code="R-1",
            land_use_description="VACANT RESIDENTIAL",
            lot_size_sqft=10105,
        )
        unit_comps = [
            ComparableSale(
                address="Oversized Build 1",
                sale_price=890000.0,
                lot_size_sqft=22000.0,
                price_per_unit=890000.0,
                adjustments={"year_built": 2025.0},
            ),
            ComparableSale(
                address="Oversized Build 2",
                sale_price=905000.0,
                lot_size_sqft=24500.0,
                price_per_unit=905000.0,
                adjustments={"year_built": 2026.0},
            ),
            ComparableSale(
                address="Renovation 1",
                sale_price=505000.0,
                lot_size_sqft=3007.0,
                price_per_unit=505000.0,
                adjustments={"year_built": 1980.0},
            ),
            ComparableSale(
                address="Renovation 2",
                sale_price=465000.0,
                lot_size_sqft=3023.0,
                price_per_unit=465000.0,
                adjustments={"year_built": 1985.0},
            ),
        ]

        filtered = _filter_vacant_single_family_unit_comps(subject, unit_comps)

        assert [comp.address for comp in filtered] == ["Renovation 1", "Renovation 2"]

    def test_prefers_nearby_local_cluster_over_farther_same_market_unit_comps(self):
        subject = PropertyRecord(
            county="Miami-Dade",
            municipality="Miami Gardens",
            zoning_code="R-1",
            land_use_description="VACANT RESIDENTIAL",
            lot_size_sqft=10105,
        )
        unit_comps = [
            ComparableSale(
                address="Nearby Comp 1",
                sale_price=505000.0,
                lot_size_sqft=3007.0,
                distance_miles=0.31,
                price_per_unit=505000.0,
                adjustments={"year_built": 1980.0},
            ),
            ComparableSale(
                address="Nearby Comp 2",
                sale_price=465000.0,
                lot_size_sqft=3023.0,
                distance_miles=0.38,
                price_per_unit=465000.0,
                adjustments={"year_built": 1985.0},
            ),
            ComparableSale(
                address="Farther Same-City Comp",
                sale_price=590000.0,
                lot_size_sqft=3200.0,
                distance_miles=1.82,
                price_per_unit=590000.0,
                adjustments={"year_built": 1988.0},
            ),
        ]

        filtered = _filter_vacant_single_family_unit_comps(subject, unit_comps)

        assert [comp.address for comp in filtered] == ["Nearby Comp 1", "Nearby Comp 2"]

    def test_prefers_nearby_local_cluster_over_farther_premium_new_build_cluster(self):
        subject = PropertyRecord(
            county="Miami-Dade",
            municipality="Miami Gardens",
            zoning_code="R-1",
            land_use_description="VACANT RESIDENTIAL",
            lot_size_sqft=10105,
        )
        unit_comps = [
            ComparableSale(
                address="Premium New Build 1",
                sale_price=710000.0,
                lot_size_sqft=7600.0,
                distance_miles=1.42,
                price_per_unit=710000.0,
                adjustments={"year_built": 2025.0},
            ),
            ComparableSale(
                address="Premium New Build 2",
                sale_price=699000.0,
                lot_size_sqft=7500.0,
                distance_miles=1.37,
                price_per_unit=699000.0,
                adjustments={"year_built": 2026.0},
            ),
            ComparableSale(
                address="Nearby Renovation 1",
                sale_price=505000.0,
                lot_size_sqft=3007.0,
                distance_miles=0.31,
                price_per_unit=505000.0,
                adjustments={"year_built": 1980.0},
            ),
            ComparableSale(
                address="Nearby Renovation 2",
                sale_price=465000.0,
                lot_size_sqft=3023.0,
                distance_miles=0.38,
                price_per_unit=465000.0,
                adjustments={"year_built": 1985.0},
            ),
        ]

        filtered = _filter_vacant_single_family_unit_comps(subject, unit_comps)

        assert [comp.address for comp in filtered] == [
            "Nearby Renovation 1",
            "Nearby Renovation 2",
        ]


class TestLandCompQualificationScore:
    def test_prefers_nearby_recent_exact_land_matches(self):
        from plotlot.pipeline.comps import _land_comp_qualification_score

        high_score = _land_comp_qualification_score(
            subject_lot_sqft=10000.0,
            comp_lot_sqft=9800.0,
            zoning_status="match",
            municipality_status="match",
            distance_miles=0.4,
            sale_date="2026-04-01",
            now=datetime(2026, 6, 29, tzinfo=timezone.utc),
        )
        low_score = _land_comp_qualification_score(
            subject_lot_sqft=10000.0,
            comp_lot_sqft=18000.0,
            zoning_status="mismatch",
            municipality_status="mismatch",
            distance_miles=4.5,
            sale_date="2024-07-01",
            now=datetime(2026, 6, 29, tzinfo=timezone.utc),
        )

        assert high_score > low_score
        assert high_score >= 0.85
        assert low_score <= 0.55

    def test_caps_unknown_land_metadata_below_strong_support(self):
        from plotlot.pipeline.comps import _land_comp_qualification_score

        score = _land_comp_qualification_score(
            subject_lot_sqft=10000.0,
            comp_lot_sqft=9800.0,
            zoning_status="unknown",
            municipality_status="unknown",
            distance_miles=0.4,
            sale_date="2026-04-01",
            now=datetime(2026, 6, 29, tzinfo=timezone.utc),
        )

        assert score == pytest.approx(0.55)


class TestUnitCompQualificationScore:
    def test_prefers_nearby_recent_same_market_exit_sales(self):
        from plotlot.pipeline.comps import _unit_comp_qualification_score

        high_score = _unit_comp_qualification_score(
            subject_lot_sqft=10000.0,
            comp_lot_sqft=9600.0,
            municipality_status="match",
            distance_miles=0.35,
            sale_date="2026-05-01",
            now=datetime(2026, 6, 29, tzinfo=timezone.utc),
        )
        low_score = _unit_comp_qualification_score(
            subject_lot_sqft=10000.0,
            comp_lot_sqft=3500.0,
            municipality_status="mismatch",
            distance_miles=4.9,
            sale_date="2024-09-01",
            now=datetime(2026, 6, 29, tzinfo=timezone.utc),
        )

        assert high_score > low_score
        assert high_score >= 0.85
        assert low_score <= 0.6

    def test_caps_unknown_exit_market_metadata_below_strong_support(self):
        from plotlot.pipeline.comps import _unit_comp_qualification_score

        score = _unit_comp_qualification_score(
            subject_lot_sqft=10000.0,
            comp_lot_sqft=9600.0,
            municipality_status="unknown",
            distance_miles=0.35,
            sale_date="2026-05-01",
            now=datetime(2026, 6, 29, tzinfo=timezone.utc),
        )

        assert score == pytest.approx(0.65)


class TestSalesQueryLimit:
    def test_caps_wide_vacant_lot_search_below_timeout_prone_volume(self):
        assert _sales_query_limit(
            vacant_single_family_subject=True,
            months=24,
            radius_miles=5.0,
        ) == 400


class TestVacantLandSalesWhereClause:
    def test_builds_miami_dade_vacant_land_filter_for_wide_search(self):
        subject = PropertyRecord(
            county="Miami-Dade",
            municipality="Miami Gardens",
            zoning_code="R-1",
            land_use_code="0066",
            land_use_description="VACANT RESIDENTIAL",
        )

        where_clause = _vacant_land_sales_where_clause(
            subject=subject,
            land_use_field="DOR_CODE_CUR",
        )

        assert where_clause == "DOR_CODE_CUR IN ('0066', '0081')"


class TestFeatureLatLng:
    def test_point_geometry(self):
        result = _feature_latlng({"x": -80.19, "y": 25.76})
        assert result == (25.76, -80.19)

    def test_polygon_centroid(self):
        rings = [[[-80.0, 25.0], [-80.0, 26.0], [-81.0, 26.0], [-81.0, 25.0]]]
        result = _feature_latlng({"rings": rings})
        assert result is not None
        lat, lng = result
        assert 25.0 <= lat <= 26.0
        assert -81.0 <= lng <= -80.0

    def test_empty_geometry(self):
        assert _feature_latlng({}) is None


class TestPolygonAreaSqft:
    def test_polygon_area_sqft_returns_positive_estimate(self):
        geom = {
            "rings": [[
                [-80.1600, 26.1450],
                [-80.1598, 26.1450],
                [-80.1598, 26.1452],
                [-80.1600, 26.1452],
                [-80.1600, 26.1450],
            ]]
        }
        area = _polygon_area_sqft(geom)
        assert area > 0


class TestQueryNearbySales:
    @pytest.mark.asyncio
    async def test_paginates_dense_arcgis_sales_queries(self, monkeypatch: pytest.MonkeyPatch):
        class _FakeResponse:
            def __init__(self, features):
                self._features = features

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, object]:
                return {"features": self._features}

        class _FakeClient:
            def __init__(self, *, timeout: float):
                self.timeout = timeout

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb) -> None:
                return None

            async def get(self, _url: str, *, params: dict[str, str]):
                offset = int(params["resultOffset"])
                count = int(params["resultRecordCount"])
                if offset == 0:
                    features = [{"attributes": {"OBJECTID": index}} for index in range(count)]
                elif offset == count:
                    features = [{"attributes": {"OBJECTID": count + index}} for index in range(30)]
                else:
                    features = []
                return _FakeResponse(features)

        monkeypatch.setattr("plotlot.pipeline.comps.httpx.AsyncClient", _FakeClient)

        features = await _query_nearby_sales(
            "https://example.test/FeatureServer/0",
            25.967404,
            -80.202576,
            radius_miles=5.0,
            limit=500,
            order_by="DATEOFSALE_UTC",
        )

        assert len(features) == 280

    async def test_retries_transient_sales_query_failure_before_success(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        transport_request = httpx.Request("GET", "https://example.test/FeatureServer/0/query")
        transient_error = httpx.ReadTimeout("timed out", request=transport_request)

        class _FakeResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, object]:
                return {"features": [{"attributes": {"OBJECTID": 1}}]}

        class _FakeClient:
            def __init__(self, *, timeout: httpx.Timeout | float):
                self.timeout = timeout
                self.calls = 0

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb) -> None:
                return None

            async def get(self, _url: str, *, params: dict[str, str]):
                self.calls += 1
                if self.calls == 1:
                    raise transient_error
                return _FakeResponse()

        sleep_mock = AsyncMock()
        monkeypatch.setattr("plotlot.pipeline.comps.httpx.AsyncClient", _FakeClient)
        monkeypatch.setattr("plotlot.pipeline.comps.anyio.sleep", sleep_mock)

        features = await _query_nearby_sales(
            "https://example.test/FeatureServer/0",
            25.967404,
            -80.202576,
            radius_miles=3.0,
            limit=1,
        )

        assert len(features) == 1
        sleep_mock.assert_awaited_once_with(1.0)


class TestCompQualityHelpers:
    def test_clean_comp_address_collapses_whitespace(self):
        assert _clean_comp_address(" 123  Main   St ") == "123 Main St"

    def test_zoning_blank_values_are_unknown_not_match(self):
        assert _zoning_comparability_status("R-1", "") == "unknown"
        assert _zoning_comparability_status("", "R-1") == "unknown"
        assert not _zoning_is_comparable("R-1", "")
        assert not _zoning_is_comparable("", "R-1")

    def test_zoning_is_comparable_requires_exact_match_when_both_present(self):
        assert _zoning_is_comparable("R-1", "R-1")
        assert not _zoning_is_comparable("R-1", "RU-1")


class TestScoreConfidence:
    def test_five_recent_comps_high(self):
        assert _score_confidence(5, 0.8) == 0.9

    def test_five_stale_comps_lower(self):
        assert _score_confidence(5, 0.1) == 0.8

    def test_three_comps(self):
        assert _score_confidence(3, 0.0) == 0.75

    def test_no_comps_zero(self):
        assert _score_confidence(0, 0.0) == 0.0


class TestCompAnalysis:
    def test_default_values(self):
        ca = CompAnalysis()
        assert ca.comparables == []
        assert ca.median_price_per_acre == 0.0
        assert ca.confidence == 0.0
        assert ca.unit_comparables == []
        assert ca.web_listing_candidates == []
        assert ca.adv_source == ""

    def test_with_comparables(self):
        comps = [
            ComparableSale(
                address="123 Main St",
                sale_price=200_000,
                lot_size_sqft=10_000,
                price_per_acre=871_200,
                distance_miles=1.5,
            ),
            ComparableSale(
                address="456 Oak Ave",
                sale_price=250_000,
                lot_size_sqft=12_000,
                price_per_acre=907_500,
                distance_miles=2.0,
            ),
        ]
        ca = CompAnalysis(
            comparables=comps,
            median_price_per_acre=889_350,
            estimated_land_value=220_000,
            confidence=0.5,
        )
        assert len(ca.comparables) == 2
        assert ca.median_price_per_acre == 889_350
        assert ca.confidence == 0.5


# ---------------------------------------------------------------------------
# Discovery keywords (B) + California radius widening (C)
# ---------------------------------------------------------------------------


class TestSanDiegoCompTuning:
    async def test_ca_search_radius_widens_to_5mi(self):
        """A CA subject widens the comp search radius from the 3mi default to 5mi."""
        from unittest.mock import AsyncMock, patch

        from plotlot.core.types import PropertyRecord
        from plotlot.pipeline.comps import find_comparables

        subject = PropertyRecord(county="San Diego", lat=32.76, lng=-117.19, lot_size_sqft=7710.0)
        with (
            patch(
                "plotlot.pipeline.comps_sources.resolve_sales_dataset",
                new=AsyncMock(return_value=None),
            ) as m_resolve,
            patch(
                "plotlot.pipeline.comps._discover_sales_dataset", new=AsyncMock(return_value=None)
            ),
        ):
            await find_comparables(subject, state="CA")

        # resolve_sales_dataset(state, county, lat, lng, radius_miles) — radius widened.
        assert m_resolve.call_args.args[4] == 5.0

    async def test_fl_radius_unchanged(self):
        from unittest.mock import AsyncMock, patch

        from plotlot.core.types import PropertyRecord
        from plotlot.pipeline.comps import find_comparables

        subject = PropertyRecord(county="Broward", lat=26.1, lng=-80.1, lot_size_sqft=7000.0)
        with (
            patch(
                "plotlot.pipeline.comps_sources.resolve_sales_dataset",
                new=AsyncMock(return_value=None),
            ) as m_resolve,
            patch(
                "plotlot.pipeline.comps._discover_sales_dataset", new=AsyncMock(return_value=None)
            ),
        ):
            await find_comparables(subject, state="FL")

        assert m_resolve.call_args.args[4] == 3.0

    async def test_discovery_includes_assessor_and_parcel_keywords(self):
        from unittest.mock import AsyncMock, MagicMock, patch

        from plotlot.pipeline.comps import _discover_sales_dataset

        issued: list[str] = []

        def _capture(url, params=None):
            issued.append((params or {}).get("q", ""))
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json = MagicMock(return_value={"data": []})
            return resp

        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.get = AsyncMock(side_effect=_capture)
        with patch("plotlot.pipeline.comps.httpx.AsyncClient", return_value=client):
            await _discover_sales_dataset("San Diego", "CA")

        assert any("assessor" in q.lower() for q in issued)
        assert any("parcel" in q.lower() for q in issued)


class TestComparableFallbacks:
    async def test_find_comparables_for_vacant_single_family_subject_avoids_unreliable_land_fallbacks(self):
        from unittest.mock import AsyncMock, patch

        from plotlot.core.types import PropertyRecord
        from plotlot.pipeline.comps import find_comparables

        subject = PropertyRecord(
            county="Miami-Dade",
            municipality="Miami Gardens",
            lat=25.967404,
            lng=-80.202576,
            lot_size_sqft=10105.0,
            zoning_code="R-1",
            land_use_description="VACANT RESIDENTIAL",
        )
        features = [
            {
                "attributes": {
                    "SALE_PRICE": 2862400,
                    "SALE_DATE": "2026-04-30",
                    "ADDRESS": "19646 NE 14 CT",
                    "TRUE_SITE_CITY": "Aventura",
                    "LOT_SIZE": 7016.0,
                    "UNIT_COUNT": 0,
                    "BUILDING_ACTUAL_AREA": 0.0,
                    "YEAR_BUILT": 0,
                },
                "geometry": {"x": -80.169, "y": 25.968},
            },
            {
                "attributes": {
                    "SALE_PRICE": 325000,
                    "SALE_DATE": "2026-05-13",
                    "ADDRESS": "2861 NW 213 ST",
                    "TRUE_SITE_CITY": "Miami Gardens",
                    "LOT_SIZE": 30622.68,
                    "UNIT_COUNT": 0,
                    "BUILDING_ACTUAL_AREA": 0.0,
                    "YEAR_BUILT": 0,
                },
                "geometry": {"x": -80.232, "y": 25.968},
            },
            {
                "attributes": {
                    "SALE_PRICE": 699000,
                    "SALE_DATE": "2026-04-21",
                    "ADDRESS": "105 NE 213 ST",
                    "TRUE_SITE_CITY": "Miami Gardens",
                    "LOT_SIZE": 7500.0,
                    "UNIT_COUNT": 1,
                    "BUILDING_ACTUAL_AREA": 1800.0,
                    "YEAR_BUILT": 1970,
                },
                "geometry": {"x": -80.204, "y": 25.971},
            },
            {
                "attributes": {
                    "SALE_PRICE": 505000,
                    "SALE_DATE": "2026-05-05",
                    "ADDRESS": "220 NE 211 ST",
                    "TRUE_SITE_CITY": "Miami Gardens",
                    "LOT_SIZE": 3007.0,
                    "UNIT_COUNT": 1,
                    "BUILDING_ACTUAL_AREA": 1550.0,
                    "YEAR_BUILT": 1980,
                },
                "geometry": {"x": -80.204, "y": 25.970},
            },
            {
                "attributes": {
                    "SALE_PRICE": 170000,
                    "SALE_DATE": "2026-04-29",
                    "ADDRESS": "464 NE 210 CIRCLE TER 20410A",
                    "TRUE_SITE_CITY": "Miami Gardens",
                    "LOT_SIZE": 0.0,
                    "UNIT_COUNT": 1,
                    "BUILDING_ACTUAL_AREA": 950.0,
                    "YEAR_BUILT": 1975,
                },
                "geometry": {"x": -80.203, "y": 25.969},
            },
            {
                "attributes": {
                    "SALE_PRICE": 465000,
                    "SALE_DATE": "2026-04-23",
                    "ADDRESS": "221 NE 212 ST",
                    "TRUE_SITE_CITY": "Miami Gardens",
                    "LOT_SIZE": 3023.0,
                    "UNIT_COUNT": 1,
                    "BUILDING_ACTUAL_AREA": 1525.0,
                    "YEAR_BUILT": 1985,
                },
                "geometry": {"x": -80.203, "y": 25.970},
            },
            {
                "attributes": {
                    "SALE_PRICE": 1475000,
                    "SALE_DATE": "2026-04-24",
                    "ADDRESS": "312 NE 210 WAY",
                    "TRUE_SITE_CITY": "Aventura",
                    "LOT_SIZE": 6100.0,
                    "UNIT_COUNT": 1,
                    "BUILDING_ACTUAL_AREA": 3200.0,
                    "YEAR_BUILT": 2024,
                },
                "geometry": {"x": -80.203, "y": 25.969},
            },
        ]

        with (
            patch(
                "plotlot.pipeline.comps_sources.resolve_sales_dataset",
                new=AsyncMock(
                    return_value=(
                        "https://example.test/sales",
                        [
                            "SALE_PRICE",
                            "SALE_DATE",
                            "ADDRESS",
                            "TRUE_SITE_CITY",
                            "LOT_SIZE",
                            "ZONING",
                            "UNIT_COUNT",
                            "BUILDING_ACTUAL_AREA",
                            "YEAR_BUILT",
                        ],
                    )
                ),
            ),
            patch("plotlot.pipeline.comps._query_nearby_sales", new=AsyncMock(return_value=features)),
        ):
            result = await find_comparables(subject, state="FL")

        assert result.comparables == []
        assert result.estimated_land_value == 0.0
        assert any("No reliable vacant-land comps" in note for note in result.notes)
        assert any(
            "No recent same-market new-build sales were available" in note
            for note in result.notes
        )
        assert result.rejected_land_comparables == []
        assert {comp.address for comp in result.unit_comparables} == {
            "105 NE 213 ST",
            "220 NE 211 ST",
            "221 NE 212 ST",
        }
        assert result.adv_per_unit == 505000.0
        assert result.adv_per_unit_low == 485000.0
        assert result.adv_per_unit_high == 602000.0

    async def test_find_comparables_prefers_same_market_recent_new_build_exit_sales(self):
        from unittest.mock import AsyncMock, patch

        from plotlot.core.types import PropertyRecord
        from plotlot.pipeline.comps import find_comparables

        subject = PropertyRecord(
            county="Miami-Dade",
            municipality="Miami Gardens",
            lat=25.967404,
            lng=-80.202576,
            lot_size_sqft=10105.0,
            zoning_code="R-1",
            land_use_description="VACANT RESIDENTIAL",
        )
        features = [
            {
                "attributes": {
                    "SALE_PRICE": 710000,
                    "SALE_DATE": "2026-04-30",
                    "ADDRESS": "200 NE 213 ST",
                    "TRUE_SITE_CITY": "Miami Gardens",
                    "LOT_SIZE": 7600.0,
                    "UNIT_COUNT": 1,
                    "BUILDING_ACTUAL_AREA": 1950.0,
                    "YEAR_BUILT": 2025,
                },
                "geometry": {"x": -80.204, "y": 25.971},
            },
            {
                "attributes": {
                    "SALE_PRICE": 699000,
                    "SALE_DATE": "2026-04-21",
                    "ADDRESS": "105 NE 213 ST",
                    "TRUE_SITE_CITY": "Miami Gardens",
                    "LOT_SIZE": 7500.0,
                    "UNIT_COUNT": 1,
                    "BUILDING_ACTUAL_AREA": 1800.0,
                    "YEAR_BUILT": 2026,
                },
                "geometry": {"x": -80.204, "y": 25.971},
            },
            {
                "attributes": {
                    "SALE_PRICE": 505000,
                    "SALE_DATE": "2026-05-05",
                    "ADDRESS": "220 NE 211 ST",
                    "TRUE_SITE_CITY": "Miami Gardens",
                    "LOT_SIZE": 3007.0,
                    "UNIT_COUNT": 1,
                    "BUILDING_ACTUAL_AREA": 1550.0,
                    "YEAR_BUILT": 1980,
                },
                "geometry": {"x": -80.204, "y": 25.970},
            },
        ]

        with (
            patch(
                "plotlot.pipeline.comps_sources.resolve_sales_dataset",
                new=AsyncMock(
                    return_value=(
                        "https://example.test/sales",
                        [
                            "SALE_PRICE",
                            "SALE_DATE",
                            "ADDRESS",
                            "TRUE_SITE_CITY",
                            "LOT_SIZE",
                            "ZONING",
                            "UNIT_COUNT",
                            "BUILDING_ACTUAL_AREA",
                            "YEAR_BUILT",
                        ],
                    )
                ),
            ),
            patch("plotlot.pipeline.comps._query_nearby_sales", new=AsyncMock(return_value=features)),
        ):
            result = await find_comparables(subject, state="FL")

        assert [comp.address for comp in result.unit_comparables] == [
            "200 NE 213 ST",
            "105 NE 213 ST",
        ]
        assert result.adv_per_unit == 704500.0
        assert not any("renovated or older improved sales" in note for note in result.notes)

    async def test_find_comparables_rejects_oversized_recent_new_build_outliers_for_vacant_single_family_subject(self):
        from unittest.mock import AsyncMock, patch

        from plotlot.core.types import PropertyRecord
        from plotlot.pipeline.comps import find_comparables

        subject = PropertyRecord(
            county="Miami-Dade",
            municipality="Miami Gardens",
            lat=25.967404,
            lng=-80.202576,
            lot_size_sqft=10105.0,
            zoning_code="R-1",
            land_use_description="VACANT RESIDENTIAL",
        )
        features = [
            {
                "attributes": {
                    "SALE_PRICE": 890000,
                    "SALE_DATE": "2026-04-30",
                    "ADDRESS": "320 Premium Build Way",
                    "TRUE_SITE_CITY": "Miami Gardens",
                    "LOT_SIZE": 22000.0,
                    "UNIT_COUNT": 1,
                    "BUILDING_ACTUAL_AREA": 3100.0,
                    "YEAR_BUILT": 2025,
                },
                "geometry": {"x": -80.204, "y": 25.971},
            },
            {
                "attributes": {
                    "SALE_PRICE": 905000,
                    "SALE_DATE": "2026-04-21",
                    "ADDRESS": "340 Premium Build Way",
                    "TRUE_SITE_CITY": "Miami Gardens",
                    "LOT_SIZE": 24500.0,
                    "UNIT_COUNT": 1,
                    "BUILDING_ACTUAL_AREA": 3300.0,
                    "YEAR_BUILT": 2026,
                },
                "geometry": {"x": -80.204, "y": 25.971},
            },
            {
                "attributes": {
                    "SALE_PRICE": 505000,
                    "SALE_DATE": "2026-05-05",
                    "ADDRESS": "220 NE 211 ST",
                    "TRUE_SITE_CITY": "Miami Gardens",
                    "LOT_SIZE": 3007.0,
                    "UNIT_COUNT": 1,
                    "BUILDING_ACTUAL_AREA": 1550.0,
                    "YEAR_BUILT": 1980,
                },
                "geometry": {"x": -80.204, "y": 25.970},
            },
            {
                "attributes": {
                    "SALE_PRICE": 465000,
                    "SALE_DATE": "2026-04-23",
                    "ADDRESS": "221 NE 212 ST",
                    "TRUE_SITE_CITY": "Miami Gardens",
                    "LOT_SIZE": 3023.0,
                    "UNIT_COUNT": 1,
                    "BUILDING_ACTUAL_AREA": 1525.0,
                    "YEAR_BUILT": 1985,
                },
                "geometry": {"x": -80.203, "y": 25.970},
            },
        ]

        with (
            patch(
                "plotlot.pipeline.comps_sources.resolve_sales_dataset",
                new=AsyncMock(
                    return_value=(
                        "https://example.test/sales",
                        [
                            "SALE_PRICE",
                            "SALE_DATE",
                            "ADDRESS",
                            "TRUE_SITE_CITY",
                            "LOT_SIZE",
                            "ZONING",
                            "UNIT_COUNT",
                            "BUILDING_ACTUAL_AREA",
                            "YEAR_BUILT",
                        ],
                    )
                ),
            ),
            patch("plotlot.pipeline.comps._query_nearby_sales", new=AsyncMock(return_value=features)),
        ):
            result = await find_comparables(subject, state="FL")

        assert {comp.address for comp in result.unit_comparables} == {
            "220 NE 211 ST",
            "221 NE 212 ST",
        }
        assert result.adv_per_unit == 485000.0
        assert any(
            "No recent same-market new-build sales were available" in note
            for note in result.notes
        )

    async def test_find_comparables_prefers_nearby_local_exit_cluster_for_vacant_single_family_subject(self):
        from unittest.mock import AsyncMock, patch

        from plotlot.core.types import PropertyRecord
        from plotlot.pipeline.comps import find_comparables

        subject = PropertyRecord(
            county="Miami-Dade",
            municipality="Miami Gardens",
            lat=25.967404,
            lng=-80.202576,
            lot_size_sqft=10105.0,
            zoning_code="R-1",
            land_use_description="VACANT RESIDENTIAL",
        )
        features = [
            {
                "attributes": {
                    "SALE_PRICE": 505000,
                    "SALE_DATE": "2026-05-05",
                    "ADDRESS": "220 NE 211 ST",
                    "TRUE_SITE_CITY": "Miami Gardens",
                    "LOT_SIZE": 3007.0,
                    "UNIT_COUNT": 1,
                    "BUILDING_ACTUAL_AREA": 1550.0,
                    "YEAR_BUILT": 1980,
                },
                "geometry": {"x": -80.204, "y": 25.970},
            },
            {
                "attributes": {
                    "SALE_PRICE": 465000,
                    "SALE_DATE": "2026-04-23",
                    "ADDRESS": "221 NE 212 ST",
                    "TRUE_SITE_CITY": "Miami Gardens",
                    "LOT_SIZE": 3023.0,
                    "UNIT_COUNT": 1,
                    "BUILDING_ACTUAL_AREA": 1525.0,
                    "YEAR_BUILT": 1985,
                },
                "geometry": {"x": -80.203, "y": 25.970},
            },
            {
                "attributes": {
                    "SALE_PRICE": 590000,
                    "SALE_DATE": "2026-05-01",
                    "ADDRESS": "450 NW 183 ST",
                    "TRUE_SITE_CITY": "Miami Gardens",
                    "LOT_SIZE": 3200.0,
                    "UNIT_COUNT": 1,
                    "BUILDING_ACTUAL_AREA": 1650.0,
                    "YEAR_BUILT": 1988,
                },
                "geometry": {"x": -80.227, "y": 25.944},
            },
        ]

        with (
            patch(
                "plotlot.pipeline.comps_sources.resolve_sales_dataset",
                new=AsyncMock(
                    return_value=(
                        "https://example.test/sales",
                        [
                            "SALE_PRICE",
                            "SALE_DATE",
                            "ADDRESS",
                            "TRUE_SITE_CITY",
                            "LOT_SIZE",
                            "ZONING",
                            "UNIT_COUNT",
                            "BUILDING_ACTUAL_AREA",
                            "YEAR_BUILT",
                        ],
                    )
                ),
            ),
            patch("plotlot.pipeline.comps._query_nearby_sales", new=AsyncMock(return_value=features)),
        ):
            result = await find_comparables(subject, state="FL")

        assert {comp.address for comp in result.unit_comparables} == {
            "220 NE 211 ST",
            "221 NE 212 ST",
        }
        assert result.adv_per_unit == 485000.0

    async def test_find_comparables_prefers_nearby_local_exit_cluster_over_premium_new_build_micro_market(self):
        from unittest.mock import AsyncMock, patch

        from plotlot.core.types import PropertyRecord
        from plotlot.pipeline.comps import find_comparables

        subject = PropertyRecord(
            county="Miami-Dade",
            municipality="Miami Gardens",
            lat=25.967404,
            lng=-80.202576,
            lot_size_sqft=10105.0,
            zoning_code="R-1",
            land_use_description="VACANT RESIDENTIAL",
        )
        features = [
            {
                "attributes": {
                    "SALE_PRICE": 710000,
                    "SALE_DATE": "2026-04-30",
                    "ADDRESS": "200 Premium Build Ct",
                    "TRUE_SITE_CITY": "Miami Gardens",
                    "LOT_SIZE": 7600.0,
                    "UNIT_COUNT": 1,
                    "BUILDING_ACTUAL_AREA": 1950.0,
                    "YEAR_BUILT": 2025,
                },
                "geometry": {"x": -80.225, "y": 25.956},
            },
            {
                "attributes": {
                    "SALE_PRICE": 699000,
                    "SALE_DATE": "2026-04-21",
                    "ADDRESS": "105 Premium Build Ct",
                    "TRUE_SITE_CITY": "Miami Gardens",
                    "LOT_SIZE": 7500.0,
                    "UNIT_COUNT": 1,
                    "BUILDING_ACTUAL_AREA": 1800.0,
                    "YEAR_BUILT": 2026,
                },
                "geometry": {"x": -80.223, "y": 25.957},
            },
            {
                "attributes": {
                    "SALE_PRICE": 505000,
                    "SALE_DATE": "2026-05-05",
                    "ADDRESS": "220 NE 211 ST",
                    "TRUE_SITE_CITY": "Miami Gardens",
                    "LOT_SIZE": 3007.0,
                    "UNIT_COUNT": 1,
                    "BUILDING_ACTUAL_AREA": 1550.0,
                    "YEAR_BUILT": 1980,
                },
                "geometry": {"x": -80.204, "y": 25.970},
            },
            {
                "attributes": {
                    "SALE_PRICE": 465000,
                    "SALE_DATE": "2026-04-23",
                    "ADDRESS": "221 NE 212 ST",
                    "TRUE_SITE_CITY": "Miami Gardens",
                    "LOT_SIZE": 3023.0,
                    "UNIT_COUNT": 1,
                    "BUILDING_ACTUAL_AREA": 1525.0,
                    "YEAR_BUILT": 1985,
                },
                "geometry": {"x": -80.203, "y": 25.970},
            },
        ]

        with (
            patch(
                "plotlot.pipeline.comps_sources.resolve_sales_dataset",
                new=AsyncMock(
                    return_value=(
                        "https://example.test/sales",
                        [
                            "SALE_PRICE",
                            "SALE_DATE",
                            "ADDRESS",
                            "TRUE_SITE_CITY",
                            "LOT_SIZE",
                            "ZONING",
                            "UNIT_COUNT",
                            "BUILDING_ACTUAL_AREA",
                            "YEAR_BUILT",
                        ],
                    )
                ),
            ),
            patch("plotlot.pipeline.comps._query_nearby_sales", new=AsyncMock(return_value=features)),
        ):
            result = await find_comparables(subject, state="FL")

        assert {comp.address for comp in result.unit_comparables} == {
            "220 NE 211 ST",
            "221 NE 212 ST",
        }
        assert result.adv_per_unit == pytest.approx(485000.0)
        assert any(
            "higher-priced nearby micro-market" in note
            for note in result.notes
        )

    async def test_find_comparables_prefers_nearby_local_land_cluster_for_vacant_single_family_subject(self):
        from unittest.mock import AsyncMock, patch

        from plotlot.core.types import PropertyRecord
        from plotlot.pipeline.comps import find_comparables

        subject = PropertyRecord(
            county="Miami-Dade",
            municipality="Miami Gardens",
            lat=25.967404,
            lng=-80.202576,
            lot_size_sqft=10105.0,
            zoning_code="R-1",
            land_use_description="VACANT RESIDENTIAL",
        )
        features = [
            {
                "attributes": {
                    "SALE_PRICE": 145000,
                    "SALE_DATE": "2026-02-01",
                    "ADDRESS": "17605 NW 19th Avenue",
                    "TRUE_SITE_CITY": "Miami Gardens",
                    "LOT_SIZE": 9500.0,
                    "ZONING": "R-1",
                    "UNIT_COUNT": 0,
                    "BUILDING_ACTUAL_AREA": 0.0,
                },
                "geometry": {"x": -80.2016, "y": 25.9693},
            },
            {
                "attributes": {
                    "SALE_PRICE": 138000,
                    "SALE_DATE": "2026-03-14",
                    "ADDRESS": "2940 NW 169th Ter",
                    "TRUE_SITE_CITY": "Miami Gardens",
                    "LOT_SIZE": 9100.0,
                    "ZONING": "R-1",
                    "UNIT_COUNT": 0,
                    "BUILDING_ACTUAL_AREA": 0.0,
                },
                "geometry": {"x": -80.2012, "y": 25.9687},
            },
            {
                "attributes": {
                    "SALE_PRICE": 152000,
                    "SALE_DATE": "2026-01-18",
                    "ADDRESS": "168 Terrace",
                    "TRUE_SITE_CITY": "Miami Gardens",
                    "LOT_SIZE": 9700.0,
                    "ZONING": "R-1",
                    "UNIT_COUNT": 0,
                    "BUILDING_ACTUAL_AREA": 0.0,
                },
                "geometry": {"x": -80.2450, "y": 25.9500},
            },
            {
                "attributes": {
                    "SALE_PRICE": 505000,
                    "SALE_DATE": "2026-05-05",
                    "ADDRESS": "220 NE 211 ST",
                    "TRUE_SITE_CITY": "Miami Gardens",
                    "LOT_SIZE": 3007.0,
                    "UNIT_COUNT": 1,
                    "BUILDING_ACTUAL_AREA": 1550.0,
                    "YEAR_BUILT": 1980,
                },
                "geometry": {"x": -80.204, "y": 25.970},
            },
            {
                "attributes": {
                    "SALE_PRICE": 465000,
                    "SALE_DATE": "2026-04-23",
                    "ADDRESS": "221 NE 212 ST",
                    "TRUE_SITE_CITY": "Miami Gardens",
                    "LOT_SIZE": 3023.0,
                    "UNIT_COUNT": 1,
                    "BUILDING_ACTUAL_AREA": 1525.0,
                    "YEAR_BUILT": 1985,
                },
                "geometry": {"x": -80.203, "y": 25.970},
            },
        ]

        with (
            patch(
                "plotlot.pipeline.comps_sources.resolve_sales_dataset",
                new=AsyncMock(
                    return_value=(
                        "https://example.test/sales",
                        [
                            "SALE_PRICE",
                            "SALE_DATE",
                            "ADDRESS",
                            "TRUE_SITE_CITY",
                            "LOT_SIZE",
                            "ZONING",
                            "UNIT_COUNT",
                            "BUILDING_ACTUAL_AREA",
                            "YEAR_BUILT",
                        ],
                    )
                ),
            ),
            patch("plotlot.pipeline.comps._query_nearby_sales", new=AsyncMock(return_value=features)),
        ):
            result = await find_comparables(subject, state="FL")

        assert {comp.address for comp in result.comparables} == {
            "17605 NW 19th Avenue",
            "2940 NW 169th Ter",
        }
        assert result.estimated_land_value == pytest.approx(153737.44, abs=0.01)

    async def test_find_comparables_allows_single_unit_exit_comps_for_low_density_subjects(self):
        from unittest.mock import AsyncMock, patch

        from plotlot.core.types import PropertyRecord
        from plotlot.pipeline.comps import find_comparables

        subject = PropertyRecord(
            county="Broward",
            municipality="Fort Lauderdale",
            lat=26.145103,
            lng=-80.159491,
            lot_size_sqft=10687.0,
            zoning_code="RS-8",
            living_units=1,
        )
        features = [
            {
                "attributes": {
                    "SALE_AMOUNT": 425000,
                    "SALE_DATE": "2026-03-15",
                    "ADDRESS": "101 Single Family Comp Dr",
                    "LOT_SIZE": 9800.0,
                    "ZONING": "RS-8",
                    "LIVING_UNITS": 1,
                    "BUILDING_AREA": 1840.0,
                    "YEAR_BUILT": 1987,
                },
                "geometry": {"x": -80.1598, "y": 26.1452},
            }
        ]

        with (
            patch(
                "plotlot.pipeline.comps_sources.resolve_sales_dataset",
                new=AsyncMock(
                    return_value=(
                        "https://example.test/sales",
                        [
                            "SALE_AMOUNT",
                            "SALE_DATE",
                            "ADDRESS",
                            "LOT_SIZE",
                            "ZONING",
                            "LIVING_UNITS",
                            "BUILDING_AREA",
                            "YEAR_BUILT",
                        ],
                    )
                ),
            ),
            patch(
                "plotlot.pipeline.comps._query_nearby_sales",
                new=AsyncMock(return_value=features),
            ),
            patch(
                "plotlot.pipeline.comps._enrich_broward_sales_features",
                new=AsyncMock(return_value=features),
            ),
        ):
            result = await find_comparables(subject, state="FL")

        assert len(result.unit_comparables) == 1
        assert result.unit_comparables[0].address == "101 Single Family Comp Dr"
        assert result.adv_per_unit == 425000.0
        assert result.adv_source == "comps"
        assert result.sales_source_type == "curated_arcgis"
        assert result.exit_comp_source_type == "curated_arcgis"

    async def test_find_comparables_enriches_broward_sales_with_property_info(self):
        from unittest.mock import AsyncMock, MagicMock, patch

        from plotlot.core.types import PropertyRecord
        from plotlot.pipeline.comps import find_comparables

        subject = PropertyRecord(
            county="Broward",
            municipality="Fort Lauderdale",
            lat=26.145103,
            lng=-80.159491,
            lot_size_sqft=10687.0,
            zoning_code="RS-8",
        )
        features = [
            {
                "attributes": {
                    "SQLGIS02.dbo.BCPA_SALES.FOLIO_NUMBER": "494233281490",
                    "SQLGIS02.dbo.BCPA_SALES.SALE_AMOUNT": 425000,
                    "SQLGIS02.dbo.BCPA_SALES.SALE_DATE": "2026-03-15",
                    "SQLGIS02.DATALAYER.Parcel_Polygons.SHAPE.STArea()": 9800.0,
                },
                "geometry": {"x": -80.1598, "y": 26.1452},
            }
        ]

        property_client = MagicMock()
        property_client.__aenter__ = AsyncMock(return_value=property_client)
        property_client.__aexit__ = AsyncMock(return_value=False)
        property_response = MagicMock()
        property_response.raise_for_status = MagicMock()
        property_response.json = MagicMock(
            return_value={
                "features": [
                    {
                        "attributes": {
                            "FOLIO_NUMBER": "494233281490",
                            "SITUS_STREET_NUMBER": "1234",
                            "SITUS_STREET_DIRECTION": "NW",
                            "SITUS_STREET_NAME": "15TH",
                            "SITUS_STREET_TYPE": "ST",
                            "SITUS_STREET_POST_DIR": "",
                            "SITUS_UNIT_NUMBER": "",
                            "BLDG_UNITS": 1,
                            "BLDG_ADJ_SQ_FOOTAGE": 1840.0,
                            "UNDER_AIR_SQFT": "1725",
                            "BLDG_YEAR_BUILT": 1987,
                            "JUST_BUILDING_VALUE": 215000,
                        }
                    }
                ]
            }
        )
        property_client.get = AsyncMock(return_value=property_response)

        with (
            patch(
                "plotlot.pipeline.comps_sources.resolve_sales_dataset",
                new=AsyncMock(
                    return_value=(
                        "https://example.test/sales",
                        [
                            "SQLGIS02.dbo.BCPA_SALES.FOLIO_NUMBER",
                            "SQLGIS02.dbo.BCPA_SALES.SALE_DATE",
                            "SQLGIS02.dbo.BCPA_SALES.SALE_AMOUNT",
                            "SQLGIS02.DATALAYER.Parcel_Polygons.SHAPE.STArea()",
                        ],
                    )
                ),
            ),
            patch(
                "plotlot.pipeline.comps._query_nearby_sales",
                new=AsyncMock(return_value=features),
            ),
            patch("plotlot.pipeline.comps.httpx.AsyncClient", return_value=property_client),
        ):
            result = await find_comparables(subject, state="FL")

        assert len(result.unit_comparables) == 1
        assert result.unit_comparables[0].address == "1234 NW 15TH ST"
        assert result.adv_per_unit == 425000.0
        assert any(
            "lower-confidence fallback improved sales outside the exact zoning filter" in note.lower()
            for note in result.notes
        )

    async def test_find_comparables_uses_lower_confidence_fallback_when_strict_land_filters_fail(self):
        from unittest.mock import AsyncMock, patch

        from plotlot.core.types import PropertyRecord
        from plotlot.pipeline.comps import find_comparables

        subject = PropertyRecord(
            county="Miami-Dade",
            municipality="Miami Gardens",
            lat=25.968392,
            lng=-80.198728,
            lot_size_sqft=7500.0,
            zoning_code="R-1",
        )
        features = [
            {
                "attributes": {
                    "SALE_PRICE": 320000,
                    "SALE_DATE": "2026-03-15",
                    "ADDRESS": "100 Fallback Land Ave",
                    "LOT_SIZE": 12000,
                    "ZONING": "RU-1",
                },
                "geometry": {"x": -80.198, "y": 25.969},
            }
        ]

        with (
            patch(
                "plotlot.pipeline.comps_sources.resolve_sales_dataset",
                new=AsyncMock(return_value=("https://example.test/sales", ["SALE_PRICE", "SALE_DATE", "ADDRESS", "LOT_SIZE", "ZONING"])),
            ),
            patch(
                "plotlot.pipeline.comps._query_nearby_sales",
                new=AsyncMock(return_value=features),
            ),
            patch(
                "plotlot.pipeline.comps._enrich_broward_sales_features",
                new=AsyncMock(return_value=features),
            ),
        ):
            result = await find_comparables(subject, state="FL")

        assert len(result.comparables) == 1
        assert result.comparables[0].address == "100 Fallback Land Ave"
        assert result.comparables[0].adjustments == {
            "zoning_mismatch": 1.0,
            "municipality_unknown": 1.0,
            "lot_size_outside_band": 1.0,
            "qualification_score": 0.555,
        }
        assert result.confidence == 0.45
        assert any("lower-confidence fallback land comps" in note for note in result.notes)
        assert result.used_relaxed_land_comps is True
        assert result.used_relaxed_unit_comps is False
        assert result.sales_source_type == "curated_arcgis"

    async def test_find_comparables_uses_lower_confidence_fallback_when_only_relaxed_improved_sales_exist(self):
        from unittest.mock import AsyncMock, patch

        from plotlot.core.types import PropertyRecord
        from plotlot.pipeline.comps import find_comparables

        subject = PropertyRecord(
            county="Miami-Dade",
            municipality="Miami Gardens",
            lat=25.967404,
            lng=-80.202576,
            lot_size_sqft=10105.0,
            zoning_code="R-1",
            land_use_description="VACANT RESIDENTIAL",
        )
        features = [
            {
                "attributes": {
                    "SALE_PRICE": 510000,
                    "SALE_DATE": "2026-05-05",
                    "ADDRESS": "101 Relaxed Exit Comp Way",
                    "TRUE_SITE_CITY": "North Miami Beach",
                    "LOT_SIZE": 7600.0,
                    "UNIT_COUNT": 1,
                    "BUILDING_ACTUAL_AREA": 1700.0,
                    "YEAR_BUILT": 1988,
                    "ZONING": "R-2",
                },
                "geometry": {"x": -80.204, "y": 25.970},
            },
            {
                "attributes": {
                    "SALE_PRICE": 480000,
                    "SALE_DATE": "2026-04-23",
                    "ADDRESS": "102 Relaxed Exit Comp Way",
                    "TRUE_SITE_CITY": "North Miami Beach",
                    "LOT_SIZE": 7400.0,
                    "UNIT_COUNT": 1,
                    "BUILDING_ACTUAL_AREA": 1650.0,
                    "YEAR_BUILT": 1985,
                    "ZONING": "R-2",
                },
                "geometry": {"x": -80.203, "y": 25.970},
            },
        ]

        with (
            patch(
                "plotlot.pipeline.comps_sources.resolve_sales_dataset",
                new=AsyncMock(
                    return_value=(
                        "https://example.test/sales",
                        [
                            "SALE_PRICE",
                            "SALE_DATE",
                            "ADDRESS",
                            "TRUE_SITE_CITY",
                            "LOT_SIZE",
                            "UNIT_COUNT",
                            "BUILDING_ACTUAL_AREA",
                            "YEAR_BUILT",
                            "ZONING",
                        ],
                    )
                ),
            ),
            patch("plotlot.pipeline.comps._query_nearby_sales", new=AsyncMock(return_value=features)),
        ):
            result = await find_comparables(subject, state="FL")

        assert {comp.address for comp in result.unit_comparables} == {
            "101 Relaxed Exit Comp Way",
            "102 Relaxed Exit Comp Way",
        }
        assert result.adv_per_unit == 495000.0
        assert result.confidence == 0.45
        assert result.used_relaxed_land_comps is False
        assert result.used_relaxed_unit_comps is True
        assert result.sales_source_type == "curated_arcgis"
        assert result.exit_comp_source_type == "curated_arcgis"
        assert any(
            "lower-confidence fallback improved sales outside the exact zoning filter" in note.lower()
            for note in result.notes
        )

    async def test_find_comparables_uses_folio_when_sales_layer_has_no_address_field(self):
        from unittest.mock import AsyncMock, patch

        from plotlot.core.types import PropertyRecord

        subject = PropertyRecord(
            county="Broward",
            municipality="Fort Lauderdale",
            lat=26.145103,
            lng=-80.159491,
            lot_size_sqft=10687.0,
            zoning_code="RS-8",
        )
        features = [
            {
                "attributes": {
                    "FOLIO_NUMBER": "494233281490",
                    "SALE_AMOUNT": 425000,
                    "SALE_DATE": "2026-03-15",
                    "SHAPE.STArea()": 9800.0,
                },
                "geometry": {"rings": [[[-80.16, 26.145], [-80.159, 26.145], [-80.159, 26.146], [-80.16, 26.145]]]},
            }
        ]

        with (
            patch(
                "plotlot.pipeline.comps_sources.resolve_sales_dataset",
                new=AsyncMock(
                    return_value=(
                        "https://example.test/sales",
                        ["FOLIO_NUMBER", "SALE_AMOUNT", "SALE_DATE", "SHAPE.STArea()"],
                    )
                ),
            ),
            patch(
                "plotlot.pipeline.comps._query_nearby_sales",
                new=AsyncMock(return_value=features),
            ),
            patch(
                "plotlot.pipeline.comps._enrich_broward_sales_features",
                new=AsyncMock(return_value=features),
            ),
        ):
            result = await find_comparables(subject, state="FL")

        assert len(result.comparables) == 1
        assert result.comparables[0].address == "494233281490"
        assert result.comparables[0].price_per_acre > 0

    async def test_find_comparables_does_not_treat_unknown_broward_metadata_as_direct_match(self):
        from unittest.mock import AsyncMock, patch

        from plotlot.core.types import PropertyRecord

        subject = PropertyRecord(
            county="Broward",
            municipality="Fort Lauderdale",
            lat=26.145103,
            lng=-80.159491,
            lot_size_sqft=10687.0,
            zoning_code="RS-8",
        )
        features = [
            {
                "attributes": {
                    "FOLIO_NUMBER": "494233281490",
                    "SALE_AMOUNT": 425000,
                    "SALE_DATE": "2026-03-15",
                    "SHAPE.STArea()": 9800.0,
                },
                "geometry": {
                    "rings": [[[-80.16, 26.145], [-80.159, 26.145], [-80.159, 26.146], [-80.16, 26.145]]]
                },
            },
            {
                "attributes": {
                    "FOLIO_NUMBER": "494233281491",
                    "SALE_AMOUNT": 435000,
                    "SALE_DATE": "2026-02-18",
                    "SHAPE.STArea()": 9950.0,
                },
                "geometry": {
                    "rings": [[[-80.161, 26.145], [-80.160, 26.145], [-80.160, 26.146], [-80.161, 26.145]]]
                },
            },
        ]

        with (
            patch(
                "plotlot.pipeline.comps_sources.resolve_sales_dataset",
                new=AsyncMock(
                    return_value=(
                        "https://example.test/sales",
                        ["FOLIO_NUMBER", "SALE_AMOUNT", "SALE_DATE", "SHAPE.STArea()"],
                    )
                ),
            ),
            patch("plotlot.pipeline.comps._query_nearby_sales", new=AsyncMock(return_value=features)),
            patch("plotlot.pipeline.comps._enrich_broward_sales_features", new=AsyncMock(return_value=features)),
        ):
            result = await find_comparables(subject, state="FL")

        assert len(result.comparables) == 2
        assert result.used_relaxed_land_comps is True
        assert result.confidence == 0.45
        for comp in result.comparables:
            assert comp.adjustments["zoning_unknown"] == 1.0
            assert comp.adjustments["municipality_unknown"] == 1.0
            assert isinstance(comp.adjustments["qualification_score"], float)
            if "identifier_only_address" in comp.adjustments:
                assert comp.adjustments["identifier_only_address"] == 1.0
        assert all(comp.adjustments["qualification_score"] <= 0.65 for comp in result.comparables)
        assert any("lower-confidence fallback land comps" in note for note in result.notes)

    async def test_find_comparables_promotes_relaxed_vacant_lot_land_comps_when_county_data_is_strong(self):
        from unittest.mock import AsyncMock, patch

        from plotlot.core.types import PropertyRecord

        subject = PropertyRecord(
            county="Miami-Dade",
            municipality="Miami Gardens",
            lat=25.967404,
            lng=-80.202576,
            lot_size_sqft=10105.0,
            zoning_code="R-1",
            land_use_code="0066",
            land_use_description="VACANT RESIDENTIAL",
        )
        features = [
            {
                "attributes": {
                    "FOLIO": "3421100011870",
                    "TRUE_SITE_ADDR": "",
                    "TRUE_SITE_CITY": "Miami Gardens",
                    "PRICE_1": 250000,
                    "DATEOFSALE_UTC": 1774324800000,
                    "LOT_SIZE": 7664.0,
                    "DOR_CODE_CUR": "0081",
                    "BEDROOM_COUNT": 0,
                    "BUILDING_ACTUAL_AREA": 0,
                    "BUILDING_HEATED_AREA": 0,
                    "UNIT_COUNT": 0,
                    "YEAR_BUILT": 0,
                },
                "geometry": {"x": -80.175, "y": 25.947},
            },
            {
                "attributes": {
                    "FOLIO": "3421100011880",
                    "TRUE_SITE_ADDR": "",
                    "TRUE_SITE_CITY": "Miami Gardens",
                    "PRICE_1": 250000,
                    "DATEOFSALE_UTC": 1774324800000,
                    "LOT_SIZE": 7664.0,
                    "DOR_CODE_CUR": "0081",
                    "BEDROOM_COUNT": 0,
                    "BUILDING_ACTUAL_AREA": 0,
                    "BUILDING_HEATED_AREA": 0,
                    "UNIT_COUNT": 0,
                    "YEAR_BUILT": 0,
                },
                "geometry": {"x": -80.174, "y": 25.948},
            },
        ]

        with (
            patch(
                "plotlot.pipeline.comps_sources.resolve_sales_dataset",
                new=AsyncMock(
                    return_value=(
                        "https://example.test/sales",
                        [
                            "FOLIO",
                            "TRUE_SITE_ADDR",
                            "TRUE_SITE_CITY",
                            "PRICE_1",
                            "DATEOFSALE_UTC",
                            "LOT_SIZE",
                            "DOR_CODE_CUR",
                            "BEDROOM_COUNT",
                            "BUILDING_ACTUAL_AREA",
                            "BUILDING_HEATED_AREA",
                            "UNIT_COUNT",
                            "YEAR_BUILT",
                        ],
                    )
                ),
            ),
            patch("plotlot.pipeline.comps._query_nearby_sales", new=AsyncMock(return_value=features)),
        ):
            result = await find_comparables(subject, state="FL", months=24, radius_miles=5.0)

        assert len(result.comparables) == 2
        assert result.used_relaxed_land_comps is True
        assert all(comp.adjustments["zoning_unknown"] == 1.0 for comp in result.comparables)
        assert all(comp.adjustments["qualification_score"] >= 0.55 for comp in result.comparables)
        assert any("lower-confidence fallback land comps" in note for note in result.notes)

    async def test_find_comparables_filters_wide_vacant_lot_search_to_land_use_codes(self):
        from unittest.mock import AsyncMock, patch

        subject = PropertyRecord(
            county="Miami-Dade",
            municipality="Miami Gardens",
            lat=25.967404,
            lng=-80.202576,
            lot_size_sqft=10105.0,
            zoning_code="R-1",
            land_use_code="0066",
            land_use_description="VACANT RESIDENTIAL",
        )
        query_mock = AsyncMock(return_value=[])

        with (
            patch(
                "plotlot.pipeline.comps_sources.resolve_sales_dataset",
                new=AsyncMock(
                    return_value=(
                        "https://example.test/sales",
                        ["PRICE_1", "DATEOFSALE_UTC", "FOLIO", "LOT_SIZE", "DOR_CODE_CUR"],
                    )
                ),
            ),
            patch("plotlot.pipeline.comps._query_nearby_sales", new=query_mock),
        ):
            await find_comparables(subject, state="FL", months=24, radius_miles=5.0)

        assert query_mock.await_args.kwargs["where"] == "DOR_CODE_CUR IN ('0066', '0081')"

    async def test_find_comparables_uses_polygon_geometry_when_sales_layer_has_no_area_field(self):
        from unittest.mock import AsyncMock, patch

        from plotlot.core.types import PropertyRecord

        subject = PropertyRecord(
            county="Broward",
            municipality="Fort Lauderdale",
            lat=26.145103,
            lng=-80.159491,
            lot_size_sqft=10687.0,
            zoning_code="RS-8",
        )
        features = [
            {
                "attributes": {
                    "FOLIO_NUMBER": "494233281490",
                    "SALE_AMOUNT": 425000,
                    "SALE_DATE": "2026-03-15",
                },
                "geometry": {
                    "rings": [[
                        [-80.1600, 26.1450],
                        [-80.1598, 26.1450],
                        [-80.1598, 26.1452],
                        [-80.1600, 26.1452],
                        [-80.1600, 26.1450],
                    ]]
                },
            }
        ]

        with (
            patch(
                "plotlot.pipeline.comps_sources.resolve_sales_dataset",
                new=AsyncMock(
                    return_value=("https://example.test/sales", ["FOLIO_NUMBER", "SALE_AMOUNT", "SALE_DATE"])
                ),
            ),
            patch(
                "plotlot.pipeline.comps._query_nearby_sales",
                new=AsyncMock(return_value=features),
            ),
            patch(
                "plotlot.pipeline.comps._enrich_broward_sales_features",
                new=AsyncMock(return_value=features),
            ),
        ):
            result = await find_comparables(subject, state="FL")

        assert len(result.comparables) == 1
        assert result.comparables[0].lot_size_sqft > 0
        assert result.comparables[0].price_per_acre > 0

    def test_resolved_comp_address_prefers_enriched_street_address_over_folio_identifier(self):
        attrs = {
            "ADDRESS": "3412100011870",
            "TRUE_SITE_ADDR": "17605 NW 19 AVE",
            "FOLIO": "3412100011870",
        }

        address = _resolved_comp_address(
            attrs,
            addr_field="ADDRESS",
            identifier_field="FOLIO",
        )

        assert address == "17605 NW 19 AVE"
