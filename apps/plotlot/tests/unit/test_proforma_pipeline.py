"""Tests for residual land valuation pro forma pipeline step."""

from plotlot.core.types import CompAnalysis, DensityAnalysis
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
