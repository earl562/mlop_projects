"""Tests for comparable sales pipeline step."""

from plotlot.core.types import CompAnalysis, ComparableSale
from plotlot.pipeline.comps import _haversine_miles, _is_arms_length, _parse_sale_date


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


class TestCompAnalysis:
    def test_default_values(self):
        ca = CompAnalysis()
        assert ca.comparables == []
        assert ca.median_price_per_acre == 0.0
        assert ca.confidence == 0.0

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
