"""Validation tests: compare UniversalProvider output against hardcoded providers.

Run with: uv run pytest tests/integration/test_universal_validation.py -v -m live

These tests query the same addresses through both the legacy provider and
the UniversalProvider, then compare field values within tolerance.
"""

import pytest

from plotlot.property.miami_dade import MiamiDadeProvider
from plotlot.property.broward import BrowardProvider
from plotlot.property.palm_beach import PalmBeachProvider
from plotlot.property.universal import UniversalProvider


VALIDATION_CASES = [
    {
        "address": "18901 NW 27th Ave, Miami Gardens, FL",
        "county": "Miami-Dade",
        "state": "FL",
        "lat": 25.9530,
        "lng": -80.2449,
        "legacy_provider": MiamiDadeProvider,
    },
    {
        "address": "100 N Andrews Ave, Fort Lauderdale, FL",
        "county": "Broward",
        "state": "FL",
        "lat": 26.1224,
        "lng": -80.1439,
        "legacy_provider": BrowardProvider,
    },
    {
        "address": "300 S Dixie Hwy, Boca Raton, FL",
        "county": "Palm Beach",
        "state": "FL",
        "lat": 26.3448,
        "lng": -80.0838,
        "legacy_provider": PalmBeachProvider,
    },
]


@pytest.mark.live
class TestUniversalVsLegacy:
    """Compare UniversalProvider results against legacy hardcoded providers."""

    @pytest.fixture
    def universal(self):
        return UniversalProvider()

    @pytest.mark.parametrize(
        "case",
        VALIDATION_CASES,
        ids=[c["county"] for c in VALIDATION_CASES],
    )
    async def test_comparable_results(self, universal, case):
        """UniversalProvider should return comparable data to legacy provider."""
        legacy = case["legacy_provider"]()

        legacy_result = await legacy.lookup(
            case["address"],
            case["county"],
            lat=case["lat"],
            lng=case["lng"],
            state=case["state"],
        )

        universal_result = await universal.lookup(
            case["address"],
            case["county"],
            lat=case["lat"],
            lng=case["lng"],
            state=case["state"],
        )

        # Both should return something
        if legacy_result is None:
            pytest.skip(f"Legacy provider returned None for {case['county']}")

        assert universal_result is not None, (
            f"UniversalProvider returned None for {case['county']} but legacy returned data"
        )

        # Year built should match exactly (if both have it)
        if legacy_result.year_built and universal_result.year_built:
            assert universal_result.year_built == legacy_result.year_built, (
                f"Year built mismatch: "
                f"universal={universal_result.year_built}, legacy={legacy_result.year_built}"
            )

        # Lot size within 5% tolerance (different unit conversions possible)
        if legacy_result.lot_size_sqft > 0 and universal_result.lot_size_sqft > 0:
            ratio = universal_result.lot_size_sqft / legacy_result.lot_size_sqft
            assert 0.95 <= ratio <= 1.05, (
                f"Lot size mismatch beyond 5%: "
                f"universal={universal_result.lot_size_sqft}, "
                f"legacy={legacy_result.lot_size_sqft}"
            )

        # Zoning code should match (if both have it)
        if legacy_result.zoning_code and universal_result.zoning_code:
            assert universal_result.zoning_code == legacy_result.zoning_code, (
                f"Zoning mismatch: "
                f"universal={universal_result.zoning_code}, "
                f"legacy={legacy_result.zoning_code}"
            )
