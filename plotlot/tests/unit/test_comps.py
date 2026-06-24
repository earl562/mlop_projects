"""Tests for comparable sales pipeline step."""

from datetime import datetime, timezone

from plotlot.core.types import CompAnalysis, ComparableSale
from plotlot.pipeline.comps import (
    _classify_improved,
    _feature_latlng,
    _haversine_miles,
    _is_arms_length,
    _parse_sale_date,
    _percentile,
    _price_range,
    _score_confidence,
    _within_months,
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

    def test_year_built_marks_improved(self):
        attrs = {"YR": "1998"}
        improved, units = _classify_improved(attrs, None, None, "YR", None)
        assert improved is True


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
# Sales dataset discovery tests
# ---------------------------------------------------------------------------


class TestDiscoverSalesDataset:
    async def test_discover_sales_dataset_uses_cascade(self, monkeypatch):
        """Mock hub_discovery to verify _discover_sales_dataset returns correct tuple."""
        from datetime import datetime, timezone

        from plotlot.property.models import DatasetInfo

        mock_info = DatasetInfo(
            dataset_id="test-sales-123",
            name="Test Sales Dataset",
            url="https://example.com/arcgis/rest/services/Sales/FeatureServer",
            layer_id=0,
            dataset_type="sales",
            county="Miami-Dade",
            state="FL",
            fields=["PRICE_1", "DOS_1", "SALE_PRICE", "SALE_DATE"],
            discovered_at=datetime.now(timezone.utc),
        )

        async def mock_discover(lat, lng, county, state, **kwargs):
            return mock_info

        monkeypatch.setattr(
            "plotlot.property.hub_discovery.discover_sales_dataset",
            mock_discover,
        )

        from plotlot.pipeline.comps import _discover_sales_dataset

        result = await _discover_sales_dataset(
            "Miami-Dade", "FL", lat=25.7617, lng=-80.1918
        )
        assert result is not None
        url, fields = result
        assert url == "https://example.com/arcgis/rest/services/Sales/FeatureServer"
        assert "PRICE_1" in fields
        assert "DOS_1" in fields

    async def test_discover_sales_dataset_no_lat_lng(self):
        """Call without lat/lng should return None."""
        from plotlot.pipeline.comps import _discover_sales_dataset

        result = await _discover_sales_dataset("Miami-Dade", "FL")
        assert result is None
