"""Tests for the max-allowable-units calculator."""

from plotlot.core.types import NumericZoningParams
from plotlot.domain.dimensional_standard import DistrictDimensionalStandard
from plotlot.pipeline.calculator import (
    _effective_stories,
    _reconcile_density,
    calculate_max_units,
    parse_lot_dimensions,
)


# ---------------------------------------------------------------------------
# Density / min-lot-area reconciliation (regression: 1233 Hueneme St, RM-3-7)
# ---------------------------------------------------------------------------


class TestDensityReconciliation:
    def test_san_diego_rm37_regression(self):
        """1233 Hueneme St: contradictory density must not crush units to 1.

        LLM extracted 6 u/ac AND 1,000 sqft/unit (≈43.6 u/ac) — a 7x conflict.
        Trusting min-lot-area, a 6,470 sqft lot yields 6 units, not 1.
        """
        params = NumericZoningParams(
            max_density_units_per_acre=6.0,
            min_lot_area_per_unit_sqft=1000.0,
            far=1.25,
            min_unit_size_sqft=500.0,
        )
        result = calculate_max_units(6470.6, params)
        assert result.max_units == 6
        assert any("contradicts min lot area" in n for n in result.notes)
        # density constraint should now agree with min-lot-area (~6), not 1
        density = next(c for c in result.constraints if c.name == "density")
        assert density.max_units == 6

    def test_no_contradiction_keeps_density(self):
        # 6 u/ac and 7,260 sqft/unit (≈6 u/ac) agree → unchanged.
        d, ml, note = _reconcile_density(6.0, 7260.0)
        assert d == 6.0
        assert ml == 7260.0
        assert note is None

    def test_contradiction_prefers_min_lot_area(self):
        # Neither verified → trust min-lot-area (the granular form).
        d, ml, note = _reconcile_density(6.0, 1000.0)
        assert round(d, 1) == 43.6
        assert ml == 1000.0
        assert note is not None and "min lot area" in note

    def test_contradiction_prefers_verified_density(self):
        # Density is source-verified, min-lot-area is not → trust density.
        d, ml, note = _reconcile_density(43.0, 6000.0, density_verified=True)
        assert d == 43.0
        assert round(ml) == 1013  # 43,560 / 43
        assert "density (source-verified)" in note

    def test_contradiction_prefers_verified_min_lot(self):
        d, ml, note = _reconcile_density(6.0, 1000.0, min_lot_area_verified=True)
        assert round(d, 1) == 43.6
        assert "min lot area (source-verified)" in note

    def test_only_density_present_unchanged(self):
        assert _reconcile_density(25.0, None) == (25.0, None, None)

    def test_only_min_lot_area_present_unchanged(self):
        assert _reconcile_density(None, 1000.0) == (None, 1000.0, None)

    def test_verified_density_governs_in_full_calc(self):
        """When density is verified and contradicts min-lot-area, density wins."""
        params = NumericZoningParams(
            max_density_units_per_acre=43.0,
            min_lot_area_per_unit_sqft=6000.0,  # spurious (implies ~7 u/ac)
        )
        # Without verification → trust min-lot-area → 6000 sqft/unit on 43,560 = 7 units
        heuristic = calculate_max_units(43560.0, params)
        assert heuristic.max_units == 7
        # With density verified → 43 u/ac × 1 acre = 43 units
        verified = calculate_max_units(43560.0, params, density_verified=True)
        assert verified.max_units == 43

    def test_contradiction_caps_confidence(self):
        params = NumericZoningParams(
            max_density_units_per_acre=6.0,
            min_lot_area_per_unit_sqft=1000.0,
            far=1.25,
            min_unit_size_sqft=500.0,
        )
        # 3 constraints would normally be "high"; contradiction caps it to medium.
        assert calculate_max_units(6470.6, params).confidence == "medium"


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
        """Very small lot returns 0 — no artificial floor of 1."""
        params = NumericZoningParams(max_density_units_per_acre=6.0)
        result = calculate_max_units(1000, params)

        assert result.max_units == 0


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
            max_density_units_per_acre=6.0,  # → 1
            min_lot_area_per_unit_sqft=7500.0,  # → 1
            far=0.5,  # → 5
            min_unit_size_sqft=750.0,
            setback_front_ft=25.0,
            setback_rear_ft=25.0,
            setback_side_ft=7.5,
            max_stories=2,
        )
        result = calculate_max_units(
            7500,
            params,
            lot_width_ft=75.0,
            lot_depth_ft=100.0,
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
            7500,
            params,
            lot_width_ft=75.0,
            lot_depth_ft=100.0,
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
            21780,
            params,
            lot_width_ft=100.0,
            lot_depth_ft=217.8,
        )

        # density: 25 * 0.5 = 12.5 → 12
        assert result.max_units <= 12
        assert result.confidence == "high"


# ---------------------------------------------------------------------------
# Height-limited stories — zoning height + external coastal cap (Prop D)
# ---------------------------------------------------------------------------


def _envelope(result):
    return next(c for c in result.constraints if c.name == "buildable_envelope")


# 100 x 200 lot, 20' front/rear, 10' side →
#   buildable = (100 - 20) x (200 - 40) = 80 x 160 = 12,800 sqft.
def _envelope_params(**overrides) -> NumericZoningParams:
    base = dict(
        setback_front_ft=20.0,
        setback_rear_ft=20.0,
        setback_side_ft=10.0,
        min_unit_size_sqft=800.0,
        max_stories=6,
    )
    base.update(overrides)
    return NumericZoningParams(**base)


class TestEffectiveStories:
    def test_no_height_info_uses_max_stories(self):
        stories, note = _effective_stories(NumericZoningParams(max_stories=4), None, 11.0)
        assert stories == 4
        assert note is None

    def test_no_stories_at_all_defaults_to_one(self):
        stories, note = _effective_stories(NumericZoningParams(), None, 11.0)
        assert stories == 1
        assert note is None

    def test_external_coastal_cap_reduces_and_notes(self):
        # 30 ft / 11 ft = 2 stories, below the zoning's 6.
        stories, note = _effective_stories(NumericZoningParams(max_stories=6), 30.0, 11.0)
        assert stories == 2
        assert note is not None and "Coastal height limit" in note

    def test_coastal_cap_not_binding_no_note(self):
        # Zoning already allows only 2 stories — coastal 30 ft (also 2) changes nothing.
        stories, note = _effective_stories(NumericZoningParams(max_stories=2), 30.0, 11.0)
        assert stories == 2
        assert note is None

    def test_zoning_height_binds_without_coastal(self):
        # max_height 22 ft / 11 = 2 stories, below max_stories 6 — silent (no coastal note).
        stories, note = _effective_stories(
            NumericZoningParams(max_stories=6, max_height_ft=22.0), None, 11.0
        )
        assert stories == 2
        assert note is None

    def test_zoning_height_more_restrictive_than_coastal(self):
        # Zoning 11 ft (1 story) beats coastal 30 ft — coastal is not the binding source.
        stories, note = _effective_stories(
            NumericZoningParams(max_stories=6, max_height_ft=11.0), 30.0, 11.0
        )
        assert stories == 1
        assert note is None


class TestCoastalHeightLimit:
    def test_prop_d_halves_envelope_units(self):
        params = _envelope_params(max_stories=6)
        base = calculate_max_units(20000, params, lot_width_ft=100.0, lot_depth_ft=200.0)
        # 12,800 * 6 / 800 = 96
        assert _envelope(base).max_units == 96

        capped = calculate_max_units(
            20000, params, lot_width_ft=100.0, lot_depth_ft=200.0, height_limit_ft=30.0
        )
        # 30/11 → 2 stories → 12,800 * 2 / 800 = 32
        assert _envelope(capped).max_units == 32
        assert any("Coastal height limit" in n for n in capped.notes)

    def test_prop_d_governs_when_density_allows_more(self):
        # Density alone would allow ~55 units; Prop D envelope caps to 32 and governs.
        params = _envelope_params(max_density_units_per_acre=120.0, max_stories=6)
        capped = calculate_max_units(
            20000, params, lot_width_ft=100.0, lot_depth_ft=200.0, height_limit_ft=30.0
        )
        assert capped.governing_constraint == "buildable_envelope"
        assert capped.max_units == 32

    def test_story_height_param_is_configurable(self):
        params = _envelope_params(max_stories=6)
        # 30 / 10 = 3 stories → 12,800 * 3 / 800 = 48
        res = calculate_max_units(
            20000,
            params,
            lot_width_ft=100.0,
            lot_depth_ft=200.0,
            height_limit_ft=30.0,
            story_height_ft=10.0,
        )
        assert _envelope(res).max_units == 48

    def test_zoning_max_height_now_binds_envelope(self):
        # Latent-gap fix: max_height_ft was previously ignored by the calculator.
        params = _envelope_params(max_stories=6, max_height_ft=22.0)
        res = calculate_max_units(20000, params, lot_width_ft=100.0, lot_depth_ft=200.0)
        # 22/11 → 2 stories → 32 (not 96)
        assert _envelope(res).max_units == 32
        assert not any("Coastal height limit" in n for n in res.notes)

    def test_no_height_limit_leaves_units_unchanged(self):
        params = _envelope_params(max_stories=6)
        res = calculate_max_units(
            20000, params, lot_width_ft=100.0, lot_depth_ft=200.0, height_limit_ft=None
        )
        assert _envelope(res).max_units == 96


class TestVerifiedEntitlementProtection:
    """A source-verified statutory entitlement is not silently overridden by a
    coarse floor-area estimate (buildable envelope / FAR). This is the live
    1233 Hueneme regression: the Prop D 30 ft cap dragged the envelope to 4 and
    it wrongly governed below the verified 6-unit density entitlement.
    """

    def _hueneme_with_coastal(self, **kw):
        # 6,470.6 / 1,000 = 6 (the entitlement). Large min unit + 30 ft cap make
        # the envelope bind at 4 (60x108 lot → 50x88 = 4,400 buildable, 2 stories).
        params = NumericZoningParams(
            min_lot_area_per_unit_sqft=1000.0,
            min_unit_size_sqft=2000.0,
            setback_front_ft=10.0,
            setback_rear_ft=10.0,
            setback_side_ft=5.0,
            max_stories=6,
        )
        return calculate_max_units(
            6470.6,
            params,
            lot_width_ft=60.0,
            lot_depth_ft=108.0,
            height_limit_ft=30.0,
            **kw,
        )

    def test_unverified_envelope_can_still_govern(self):
        # Without verification the conservative envelope still governs (unchanged).
        res = self._hueneme_with_coastal()
        assert res.governing_constraint == "buildable_envelope"
        assert res.max_units == 4

    def test_verified_entitlement_is_not_overridden_by_envelope(self):
        res = self._hueneme_with_coastal(min_lot_area_verified=True)
        assert res.max_units == 6
        assert res.governing_constraint != "buildable_envelope"
        assert any("verified entitlement governs" in n for n in res.notes)
        # The envelope figure is still reported for transparency, just not governing.
        assert any(c.name == "buildable_envelope" for c in res.constraints)

    def test_verified_via_density_flag_also_protects(self):
        res = self._hueneme_with_coastal(density_verified=True)
        assert res.max_units == 6

    def test_far_estimate_also_demoted_when_below_verified(self):
        params = NumericZoningParams(
            min_lot_area_per_unit_sqft=1000.0,  # → 6 (verified entitlement)
            far=0.5,
            min_unit_size_sqft=2000.0,  # FAR units: 0.5*6470.6/2000 = 1.6 → 1
        )
        res = calculate_max_units(6470.6, params, min_lot_area_verified=True)
        assert res.max_units == 6
        assert res.governing_constraint != "floor_area_ratio"


class TestDistrictDimensionalStandardWiring:
    """WIRE-1.1b: calculate_max_units consumes the typed verified-fact source.

    The typed DistrictDimensionalStandard (extracted from the ordinance's
    Schedule of District Regulations at ingestion time) is the verified-fact
    replacement for LLM-extracted NumericZoningParams on the hot path. These
    tests pin the wiring contract: the calculator accepts the standard, labels
    the result ``origin="local_authority"`` (not LLM-extracted), keeps the
    NumericZoningParams fallback, and produces the same max_units as the
    equivalent NumericZoningParams.
    """

    @staticmethod
    def _rs8_standard(**overrides) -> DistrictDimensionalStandard:
        # RS-8: 8 du/ac → 5,445 sqft/unit. Density + min-lot-area are consistent
        # by construction (the standard derives one from the other), so parity is
        # about the conversion being lossless for the density path — the
        # standard's load-bearing fields.
        base = {
            "municipality": "Sandbox Springs",
            "county": "Test County",
            "state": "FL",
            "district_code": "RS-8",
            "min_lot_area_sqft": 5445.0,  # 43,560 / 8
            "min_lot_width_ft": 50.0,
            "setback_front_ft": 25.0,
            "setback_side_ft": 5.0,
            "setback_rear_ft": 25.0,
            "max_height_ft": 35.0,
            "max_lot_coverage_pct": 40.0,
            "far": 0.50,
            "max_density_units_per_acre": 8.0,
            "source_section_id": "sandbox_rs8_dim_table",
            "source_url": "https://example.gov/zoning/rs8",
        }
        base.update(overrides)
        return DistrictDimensionalStandard(**base)

    def test_accepts_district_dimensional_standard(self):
        # Criterion 1: the calculator accepts a DistrictDimensionalStandard.
        result = calculate_max_units(
            43560.0, self._rs8_standard(), lot_width_ft=100.0, lot_depth_ft=435.6
        )
        assert result.max_units == 8  # 8 du/ac × 1 acre

    def test_typed_standard_labeled_local_authority(self):
        # Criterion 2: a typed standard labels the result verified-fact grade.
        result = calculate_max_units(
            43560.0, self._rs8_standard(), lot_width_ft=100.0, lot_depth_ft=435.6
        )
        assert result.origin == "local_authority"

    def test_numeric_params_fallback_labeled_unknown(self):
        # Criterion 3: the LLM-extracted NumericZoningParams path still works and
        # is labeled assumption grade (origin=unknown).
        equiv = self._rs8_standard().to_numeric_zoning_params()
        result = calculate_max_units(43560.0, equiv, lot_width_ft=100.0, lot_depth_ft=435.6)
        assert result.max_units == 8
        assert result.origin == "unknown"

    def test_parity_standard_vs_equivalent_numeric_params(self):
        # Criterion 4: a DistrictDimensionalStandard for RS-8 returns the same
        # max_units as its .to_numeric_zoning_params() equivalent.
        standard = self._rs8_standard()
        equiv = standard.to_numeric_zoning_params()
        r_standard = calculate_max_units(43560.0, standard, lot_width_ft=100.0, lot_depth_ft=435.6)
        r_equiv = calculate_max_units(43560.0, equiv, lot_width_ft=100.0, lot_depth_ft=435.6)
        assert r_standard.max_units == r_equiv.max_units == 8
        assert r_standard.governing_constraint == r_equiv.governing_constraint

    def test_origin_override_for_caller_converted_path(self):
        # Criterion 1, Path B ("or a caller converts via .to_numeric_zoning_params()"):
        # a caller that converted the standard itself can still label the result
        # local_authority via the origin override.
        equiv = self._rs8_standard().to_numeric_zoning_params()
        result = calculate_max_units(
            43560.0,
            equiv,
            lot_width_ft=100.0,
            lot_depth_ft=435.6,
            origin="local_authority",
        )
        assert result.origin == "local_authority"
        assert result.max_units == 8

    def test_origin_override_wins_over_inferred(self):
        # An explicit origin override takes precedence over the inferred label —
        # the caller owns the provenance claim when it bypasses the standard.
        forced_unknown = calculate_max_units(
            43560.0,
            self._rs8_standard(),
            lot_width_ft=100.0,
            lot_depth_ft=435.6,
            origin="unknown",
        )
        assert forced_unknown.origin == "unknown"

    def test_no_lot_data_return_carries_origin(self):
        # Provenance propagates to the early no_lot_data return path, both grades.
        r_standard = calculate_max_units(0.0, self._rs8_standard())
        assert r_standard.governing_constraint == "no_lot_data"
        assert r_standard.origin == "local_authority"
        r_params = calculate_max_units(0.0, self._rs8_standard().to_numeric_zoning_params())
        assert r_params.origin == "unknown"

    def test_insufficient_data_return_carries_origin(self):
        # A standard with no dimensional values → insufficient_data, but the
        # provenance label still reflects the verified-fact source.
        empty_standard = self._rs8_standard(
            min_lot_area_sqft=None,
            max_density_units_per_acre=None,
            far=None,
            max_lot_coverage_pct=None,
            max_height_ft=None,
        )
        result = calculate_max_units(
            43560.0, empty_standard, lot_width_ft=100.0, lot_depth_ft=435.6
        )
        assert result.governing_constraint == "insufficient_data"
        assert result.origin == "local_authority"
