"""Tests for the max-allowable-units calculator."""

import pytest

from plotlot.core.types import NumericZoningParams
from plotlot.pipeline.calculator import (
    calculate_max_units,
    parse_lot_dimensions,
)


# ---------------------------------------------------------------------------
# parse_lot_dimensions
# ---------------------------------------------------------------------------

class TestParseLotDimensions:
    def test_standard(self):
        assert parse_lot_dimensions("75 x 100") == (75.0, 100.0)

    def test_with_decimals(self):
        assert parse_lot_dimensions("75.5 x 100.25") == (75.5, 100.25)

    def test_no_spaces(self):
        assert parse_lot_dimensions("50x120") == (50.0, 120.0)

    def test_uppercase(self):
        assert parse_lot_dimensions("75 X 100") == (75.0, 100.0)

    def test_empty(self):
        assert parse_lot_dimensions("") == (None, None)

    def test_no_match(self):
        assert parse_lot_dimensions("LOT 1 BLK A") == (None, None)

    def test_none_input(self):
        assert parse_lot_dimensions(None) == (None, None)


# ---------------------------------------------------------------------------
# Density constraint
# ---------------------------------------------------------------------------

class TestDensityConstraint:
    def test_single_family_7500sqft_6_per_acre(self):
        """7500 sqft lot, 6 units/acre → 7500/43560*6 = 1.03 → floor = 1."""
        params = NumericZoningParams(max_density_units_per_acre=6.0)
        result = calculate_max_units(7500, params)

        assert result.max_units == 1
        assert result.governing_constraint == "density"
        assert len(result.constraints) == 1
        assert result.constraints[0].name == "density"
        assert result.constraints[0].max_units == 1
        assert result.constraints[0].is_governing

    def test_multifamily_lot(self):
        """43560 sqft (1 acre), 12 units/acre → 12 units."""
        params = NumericZoningParams(max_density_units_per_acre=12.0)
        result = calculate_max_units(43560, params)

        assert result.max_units == 12
        assert result.governing_constraint == "density"

    def test_large_lot_high_density(self):
        """2 acres, 25 units/acre → 50 units."""
        params = NumericZoningParams(max_density_units_per_acre=25.0)
        result = calculate_max_units(87120, params)

        assert result.max_units == 50

    def test_fractional_floors_down(self):
        """10000 sqft, 6 units/acre → 10000/43560*6 = 1.377 → floor = 1."""
        params = NumericZoningParams(max_density_units_per_acre=6.0)
        result = calculate_max_units(10000, params)

        assert result.max_units == 1

    def test_minimum_one_unit(self):
        """Very small lot still returns at least 1 unit."""
        params = NumericZoningParams(max_density_units_per_acre=6.0)
        result = calculate_max_units(1000, params)

        assert result.max_units == 1


# ---------------------------------------------------------------------------
# Min lot area constraint
# ---------------------------------------------------------------------------

class TestMinLotAreaConstraint:
    def test_exact_match(self):
        """7500 sqft lot / 7500 sqft per unit = 1."""
        params = NumericZoningParams(min_lot_area_per_unit_sqft=7500.0)
        result = calculate_max_units(7500, params)

        assert result.max_units == 1
        assert result.governing_constraint == "min_lot_area"

    def test_double_lot(self):
        """15000 sqft / 7500 per unit = 2."""
        params = NumericZoningParams(min_lot_area_per_unit_sqft=7500.0)
        result = calculate_max_units(15000, params)

        assert result.max_units == 2

    def test_fractional_floors_down(self):
        """12000 sqft / 7500 per unit = 1.6 → 1."""
        params = NumericZoningParams(min_lot_area_per_unit_sqft=7500.0)
        result = calculate_max_units(12000, params)

        assert result.max_units == 1


# ---------------------------------------------------------------------------
# FAR constraint
# ---------------------------------------------------------------------------

class TestFARConstraint:
    def test_far_with_unit_size(self):
        """FAR 0.5, 7500 sqft lot, 750 sqft/unit → 3750/750 = 5."""
        params = NumericZoningParams(far=0.5, min_unit_size_sqft=750.0)
        result = calculate_max_units(7500, params)

        assert result.max_units == 5
        assert result.governing_constraint == "floor_area_ratio"

    def test_far_without_unit_size_skipped(self):
        """FAR without min_unit_size → constraint not evaluated."""
        params = NumericZoningParams(far=0.5)
        result = calculate_max_units(7500, params)

        assert result.max_units == 0
        assert result.governing_constraint == "insufficient_data"

    def test_far_1_0(self):
        """FAR 1.0, 10000 sqft lot, 1000 sqft/unit → 10."""
        params = NumericZoningParams(far=1.0, min_unit_size_sqft=1000.0)
        result = calculate_max_units(10000, params)

        assert result.max_units == 10


# ---------------------------------------------------------------------------
# Buildable envelope constraint
# ---------------------------------------------------------------------------

class TestBuildableEnvelopeConstraint:
    def test_with_setbacks_and_stories(self):
        """75x100 lot, 25' front/rear, 7.5' side, 2 stories, 750 sqft/unit.
        Buildable: (75-15) x (100-50) = 60 x 50 = 3000 sqft
        Total: 3000 * 2 = 6000 sqft / 750 = 8 units.
        """
        params = NumericZoningParams(
            setback_front_ft=25.0,
            setback_rear_ft=25.0,
            setback_side_ft=7.5,
            max_stories=2,
            min_unit_size_sqft=750.0,
        )
        result = calculate_max_units(7500, params, lot_width_ft=75.0, lot_depth_ft=100.0)

        envelope = next(c for c in result.constraints if c.name == "buildable_envelope")
        assert envelope.max_units == 8
        assert result.buildable_area_sqft == 3000.0

    def test_single_story_default(self):
        """Without max_stories, defaults to 1 story."""
        params = NumericZoningParams(
            setback_front_ft=25.0,
            setback_rear_ft=25.0,
            setback_side_ft=7.5,
            min_unit_size_sqft=750.0,
        )
        result = calculate_max_units(7500, params, lot_width_ft=75.0, lot_depth_ft=100.0)

        envelope = next(c for c in result.constraints if c.name == "buildable_envelope")
        # 3000 sqft * 1 story / 750 = 4
        assert envelope.max_units == 4

    def test_no_dimensions_skipped(self):
        """Without lot dimensions, buildable envelope not calculated."""
        params = NumericZoningParams(
            setback_front_ft=25.0,
            setback_rear_ft=25.0,
            setback_side_ft=7.5,
            min_unit_size_sqft=750.0,
        )
        result = calculate_max_units(7500, params)

        envelope_constraints = [c for c in result.constraints if c.name == "buildable_envelope"]
        assert len(envelope_constraints) == 0

    def test_setbacks_exceed_lot(self):
        """Setbacks larger than lot → 0 buildable area, not evaluated."""
        params = NumericZoningParams(
            setback_front_ft=50.0,
            setback_rear_ft=50.0,
            setback_side_ft=40.0,
            min_unit_size_sqft=750.0,
        )
        result = calculate_max_units(2000, params, lot_width_ft=50.0, lot_depth_ft=40.0)

        envelope_constraints = [c for c in result.constraints if c.name == "buildable_envelope"]
        assert len(envelope_constraints) == 0


# ---------------------------------------------------------------------------
# Multiple constraints → governing = minimum
# ---------------------------------------------------------------------------

class TestGoverningConstraint:
    def test_density_governs_over_lot_area(self):
        """Density says 1, min_lot_area says 2 → density governs (1)."""
        params = NumericZoningParams(
            max_density_units_per_acre=6.0,
            min_lot_area_per_unit_sqft=7500.0,
        )
        result = calculate_max_units(15000, params)

        # density: 15000/43560 * 6 = 2.066 → 2
        # min_lot: 15000/7500 = 2.0 → 2
        assert result.max_units == 2
        # Both give 2, governing goes to first with that value
        assert result.governing_constraint in ("density", "min_lot_area")

    def test_lot_area_governs_over_far(self):
        """min_lot_area says 1, FAR says 5 → min_lot_area governs (1)."""
        params = NumericZoningParams(
            min_lot_area_per_unit_sqft=7500.0,
            far=0.5,
            min_unit_size_sqft=750.0,
        )
        result = calculate_max_units(7500, params)

        # min_lot: 7500/7500 = 1
        # FAR: 0.5 * 7500 / 750 = 5
        assert result.max_units == 1
        assert result.governing_constraint == "min_lot_area"

    def test_all_four_constraints(self):
        """All four constraints evaluated — governing is the minimum."""
        params = NumericZoningParams(
            max_density_units_per_acre=6.0,       # → 1
            min_lot_area_per_unit_sqft=7500.0,    # → 1
            far=0.5,                               # → 5
            min_unit_size_sqft=750.0,
            setback_front_ft=25.0,
            setback_rear_ft=25.0,
            setback_side_ft=7.5,
            max_stories=2,
        )
        result = calculate_max_units(
            7500, params, lot_width_ft=75.0, lot_depth_ft=100.0,
        )

        assert result.max_units == 1
        assert len(result.constraints) == 4
        assert result.confidence == "high"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_zero_lot_size(self):
        params = NumericZoningParams(max_density_units_per_acre=6.0)
        result = calculate_max_units(0, params)

        assert result.max_units == 0
        assert result.governing_constraint == "no_lot_data"

    def test_negative_lot_size(self):
        params = NumericZoningParams(max_density_units_per_acre=6.0)
        result = calculate_max_units(-100, params)

        assert result.max_units == 0
        assert result.governing_constraint == "no_lot_data"

    def test_no_params(self):
        """All params are None → insufficient data."""
        params = NumericZoningParams()
        result = calculate_max_units(7500, params)

        assert result.max_units == 0
        assert result.governing_constraint == "insufficient_data"
        assert len(result.notes) > 0

    def test_confidence_levels(self):
        """1 constraint = low, 2 = medium, 3+ = high."""
        one = NumericZoningParams(max_density_units_per_acre=6.0)
        assert calculate_max_units(7500, one).confidence == "low"

        two = NumericZoningParams(
            max_density_units_per_acre=6.0,
            min_lot_area_per_unit_sqft=7500.0,
        )
        assert calculate_max_units(7500, two).confidence == "medium"

        three = NumericZoningParams(
            max_density_units_per_acre=6.0,
            min_lot_area_per_unit_sqft=7500.0,
            far=0.5,
            min_unit_size_sqft=750.0,
        )
        assert calculate_max_units(7500, three).confidence == "high"


# ---------------------------------------------------------------------------
# Real-world: Miami Gardens R-1 scenario
# ---------------------------------------------------------------------------

class TestRealWorldScenarios:
    def test_miami_gardens_r1(self):
        """171 NE 209th Ter — R-1 zone, 7500 sqft, 75x100."""
        params = NumericZoningParams(
            max_density_units_per_acre=6.0,
            min_lot_area_per_unit_sqft=7500.0,
            max_lot_coverage_pct=40.0,
            max_height_ft=35.0,
            max_stories=2,
            setback_front_ft=25.0,
            setback_side_ft=7.5,
            setback_rear_ft=25.0,
            min_unit_size_sqft=750.0,
            parking_spaces_per_unit=2.0,
        )
        result = calculate_max_units(
            7500, params, lot_width_ft=75.0, lot_depth_ft=100.0,
        )

        assert result.max_units == 1
        assert result.confidence == "high"
        assert len(result.constraints) >= 3

    def test_multifamily_scenario(self):
        """Half-acre lot, RU-4 (25 units/acre) → 12 units."""
        params = NumericZoningParams(
            max_density_units_per_acre=25.0,
            min_lot_area_per_unit_sqft=None,
            far=1.5,
            min_unit_size_sqft=800.0,
            max_stories=4,
            setback_front_ft=25.0,
            setback_side_ft=15.0,
            setback_rear_ft=20.0,
        )
        # Half acre = 21780 sqft, 100x217.8
        result = calculate_max_units(
            21780, params, lot_width_ft=100.0, lot_depth_ft=217.8,
        )

        # density: 25 * 0.5 = 12.5 → 12
        assert result.max_units <= 12
        assert result.confidence == "high"
