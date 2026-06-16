"""Tests for residual land valuation pro forma pipeline step."""

from plotlot.core.types import CompAnalysis, DensityAnalysis
from plotlot.pipeline.cost_model import get_cost_model
from plotlot.pipeline.proforma import calculate_land_pro_forma


class TestCalculateLandProForma:
    def test_basic_calculation(self):
        """GDV - costs - margin = max land price."""
        density = DensityAnalysis(max_units=10, governing_constraint="density", constraints=[])
        pf = calculate_land_pro_forma(
            density=density,
            adv_per_unit=300_000,
            construction_cost_psf=175,
            avg_unit_size_sqft=1000,
            soft_cost_pct=20,
            builder_margin_pct=25,
        )
        assert pf.max_units == 10
        assert pf.gross_development_value == 3_000_000  # 10 × 300K
        assert pf.hard_costs == 1_750_000  # 10 × 175 × 1000
        assert pf.soft_costs == 350_000  # 1.75M × 20%
        assert pf.builder_margin == 750_000  # 3M × 25%
        assert pf.max_land_price == 150_000  # 3M - 1.75M - 350K - 750K

    def test_no_units_returns_early(self):
        pf = calculate_land_pro_forma()
        assert pf.max_units == 0
        assert pf.max_land_price == 0
        assert len(pf.notes) > 0

    def test_no_adv_returns_early(self):
        density = DensityAnalysis(max_units=5, governing_constraint="density", constraints=[])
        pf = calculate_land_pro_forma(density=density)
        assert pf.max_units == 5
        assert "ADV" in pf.notes[0]

    def test_negative_residual(self):
        """When costs exceed GDV, max_land_price is negative."""
        density = DensityAnalysis(max_units=2, governing_constraint="density", constraints=[])
        pf = calculate_land_pro_forma(
            density=density,
            adv_per_unit=150_000,
            construction_cost_psf=200,
            avg_unit_size_sqft=1500,
        )
        # GDV = 300K, hard = 600K — negative residual
        assert pf.max_land_price < 0
        assert "Negative" in pf.notes[0]

    def test_comps_provide_adv(self):
        """CompAnalysis.adv_per_unit flows into pro forma."""
        density = DensityAnalysis(max_units=5, governing_constraint="density", constraints=[])
        comps = CompAnalysis(adv_per_unit=400_000)
        pf = calculate_land_pro_forma(density=density, comps=comps)
        assert pf.adv_per_unit == 400_000
        assert pf.gross_development_value == 2_000_000
        assert pf.adv_source == "comps"


class TestAdvResolution:
    def test_comps_adv_beats_regional_default(self):
        """Real sold-unit comps take priority over the market fallback."""
        density = DensityAnalysis(max_units=4, governing_constraint="density", constraints=[])
        comps = CompAnalysis(adv_per_unit=500_000)
        cm = get_cost_model("CA", "San Diego")  # default ADV 750k
        pf = calculate_land_pro_forma(density=density, comps=comps, cost_model=cm)
        assert pf.adv_per_unit == 500_000
        assert pf.adv_source == "comps"

    def test_regional_default_when_no_comps(self):
        """With no comp ADV, the pro forma still computes via the market default."""
        density = DensityAnalysis(max_units=4, governing_constraint="density", constraints=[])
        cm = get_cost_model("CA", "San Diego")
        pf = calculate_land_pro_forma(density=density, cost_model=cm)
        assert pf.adv_source == "regional_default"
        assert pf.adv_per_unit == 750_000
        assert pf.gross_development_value == 3_000_000  # 4 × 750k
        assert pf.market == "San Diego"
        assert any("market estimate" in n for n in pf.notes)

    def test_explicit_override_beats_everything(self):
        density = DensityAnalysis(max_units=2, governing_constraint="density", constraints=[])
        comps = CompAnalysis(adv_per_unit=500_000)
        cm = get_cost_model("CA", "San Diego")
        pf = calculate_land_pro_forma(
            density=density, comps=comps, cost_model=cm, adv_per_unit=600_000
        )
        assert pf.adv_per_unit == 600_000
        assert pf.adv_source == "override"

    def test_regional_costs_applied(self):
        """Cost levers come from the cost model when not overridden."""
        density = DensityAnalysis(max_units=1, governing_constraint="density", constraints=[])
        cm = get_cost_model("CA", "San Diego")  # 350 psf, 1050 sf, soft 22%
        pf = calculate_land_pro_forma(density=density, adv_per_unit=800_000, cost_model=cm)
        assert pf.construction_cost_psf == 350.0
        assert pf.avg_unit_size_sqft == 1050.0
        assert pf.hard_costs == 350.0 * 1050.0  # 1 unit
        assert pf.soft_cost_pct == 22.0

    def test_land_value_fallback_when_no_adv_anywhere(self):
        """Last resort: comps land value, no regional default available."""
        density = DensityAnalysis(max_units=3, governing_constraint="density", constraints=[])
        comps = CompAnalysis(estimated_land_value=250_000)
        pf = calculate_land_pro_forma(density=density, comps=comps)
        assert pf.max_land_price == 250_000
        assert pf.adv_source == "comps_land_value"


class TestImpactFees:
    def test_impact_fees_deducted_from_residual(self):
        density = DensityAnalysis(max_units=10, governing_constraint="density", constraints=[])
        base = calculate_land_pro_forma(
            density=density,
            adv_per_unit=400_000,
            construction_cost_psf=175,
            avg_unit_size_sqft=1000,
            soft_cost_pct=20,
            builder_margin_pct=25,
        )
        with_fees = calculate_land_pro_forma(
            density=density,
            adv_per_unit=400_000,
            construction_cost_psf=175,
            avg_unit_size_sqft=1000,
            soft_cost_pct=20,
            builder_margin_pct=25,
            impact_fees_per_unit=20_000,
        )
        assert base.impact_fees == 0
        assert with_fees.impact_fees == 200_000  # 10 × 20k
        assert with_fees.max_land_price == base.max_land_price - 200_000
        assert with_fees.cost_per_door == base.cost_per_door + 20_000  # fees per door

    def test_cost_model_supplies_impact_fees(self):
        density = DensityAnalysis(max_units=4, governing_constraint="density", constraints=[])
        cm = get_cost_model("CA", "San Diego")  # 40k/unit
        pf = calculate_land_pro_forma(density=density, cost_model=cm)
        assert pf.impact_fees_per_unit == 40_000
        assert pf.impact_fees == 160_000

    def test_no_impact_fees_without_model_or_arg(self):
        density = DensityAnalysis(max_units=5, governing_constraint="density", constraints=[])
        pf = calculate_land_pro_forma(density=density, adv_per_unit=300_000)
        assert pf.impact_fees == 0
        assert pf.impact_fees_per_unit == 0

    def test_cost_per_door(self):
        density = DensityAnalysis(max_units=4, governing_constraint="density", constraints=[])
        pf = calculate_land_pro_forma(
            density=density,
            adv_per_unit=500_000,
            construction_cost_psf=175,
            avg_unit_size_sqft=1000,
        )
        # Hard = 700K, Soft = 140K, total = 840K, per door = 210K
        assert pf.cost_per_door == 210_000
