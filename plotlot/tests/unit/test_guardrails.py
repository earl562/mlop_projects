"""Tests for deterministic residual plausibility guardrails.

Includes the San Diego regression: an over-counted buildable-unit figure must
raise a warning rather than silently flow into a confident offer price.
"""

from plotlot.core.types import ConstraintResult, DensityAnalysis, LandProForma
from plotlot.pipeline.guardrails import check_residual_plausibility


def _density(max_units: int, n_constraints: int, confidence: str) -> DensityAnalysis:
    constraints = [
        ConstraintResult(name=f"c{i}", max_units=max_units, raw_value=float(max_units), formula="")
        for i in range(n_constraints)
    ]
    return DensityAnalysis(
        max_units=max_units,
        governing_constraint="density",
        constraints=constraints,
        confidence=confidence,
    )


class TestPlausibility:
    def test_normal_corroborated_deal_no_warnings(self):
        # 10 units on ~0.5 acre, 3 corroborating constraints, high confidence.
        density = _density(10, n_constraints=3, confidence="high")
        warnings = check_residual_plausibility(density, lot_size_sqft=21_780)
        assert warnings == []

    def test_san_diego_overcount_regression(self):
        """A hallucinated density that yields ~50 units on a 7,000 sqft lot.

        50 units / (7000/43560 acre) ≈ 311 units/acre — must be flagged.
        """
        density = _density(50, n_constraints=1, confidence="low")
        warnings = check_residual_plausibility(density, lot_size_sqft=7_000)
        assert warnings, "implausible San Diego over-count must raise a warning"
        joined = " ".join(warnings).lower()
        assert "units/acre" in joined or "density" in joined
        assert "verify" in joined

    def test_high_density_flagged(self):
        # 400 units on 1 acre = 400 u/ac > 300 ceiling.
        density = _density(400, n_constraints=3, confidence="high")
        warnings = check_residual_plausibility(density, lot_size_sqft=43_560)
        assert any("units/acre" in w for w in warnings)

    def test_single_constraint_low_confidence_flagged(self):
        density = _density(8, n_constraints=1, confidence="low")
        warnings = check_residual_plausibility(density, lot_size_sqft=43_560)
        assert any("corroborating" in w for w in warnings)

    def test_regional_default_adv_flagged(self):
        density = _density(8, n_constraints=3, confidence="high")
        pf = LandProForma(max_units=8, adv_per_unit=450_000, adv_source="regional_default")
        warnings = check_residual_plausibility(density, lot_size_sqft=43_560, pro_forma=pf)
        assert any("regional market estimate" in w for w in warnings)

    def test_comps_adv_not_flagged(self):
        density = _density(8, n_constraints=3, confidence="high")
        pf = LandProForma(max_units=8, adv_per_unit=450_000, adv_source="comps")
        warnings = check_residual_plausibility(density, lot_size_sqft=43_560, pro_forma=pf)
        assert not any("regional market estimate" in w for w in warnings)

    def test_no_density_no_warnings(self):
        assert check_residual_plausibility(None, 10_000) == []

    def test_zero_units_no_warnings(self):
        density = _density(0, n_constraints=0, confidence="low")
        assert check_residual_plausibility(density, 10_000) == []

    def test_deterministic(self):
        density = _density(50, n_constraints=1, confidence="low")
        runs = [check_residual_plausibility(density, 7_000) for _ in range(20)]
        assert all(r == runs[0] for r in runs)
