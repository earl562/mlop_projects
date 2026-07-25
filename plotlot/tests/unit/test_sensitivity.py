"""Tests for the pro forma sensitivity table."""

from plotlot.core.types import CompAnalysis, DensityAnalysis
from plotlot.pipeline.cost_model import get_cost_model
from plotlot.pipeline.proforma import calculate_land_pro_forma
from plotlot.pipeline.sensitivity import build_sensitivity_table


def _density(units: int = 10) -> DensityAnalysis:
    return DensityAnalysis(max_units=units, governing_constraint="density", constraints=[])


class TestBuildSensitivityTable:
    def test_base_cell_matches_headline_residual(self):
        density = _density(10)
        comps = CompAnalysis(adv_per_unit=400_000)
        cost_model = get_cost_model("FL", "Miami-Dade")
        table = build_sensitivity_table(density=density, comps=comps, cost_model=cost_model)
        pf = calculate_land_pro_forma(density=density, comps=comps, cost_model=cost_model)
        base = table.grid[table.base_row_index][table.base_col_index]
        assert base == round(pf.max_land_price, 2)
        assert table.base_value == base

    def test_grid_dimensions(self):
        table = build_sensitivity_table(max_units=10, adv_per_unit=400_000)
        assert len(table.row_values) == 5
        assert len(table.col_values) == 5
        assert len(table.grid) == 5
        assert all(len(row) == 5 for row in table.grid)

    def test_adv_increases_offer_across_row(self):
        """Holding cost fixed, higher ADV → higher max land offer."""
        table = build_sensitivity_table(max_units=10, adv_per_unit=400_000)
        row = table.grid[table.base_row_index]
        assert row[0] < row[-1]
        assert row == sorted(row)

    def test_cost_decreases_offer_down_column(self):
        """Holding ADV fixed, higher construction cost → lower max land offer."""
        table = build_sensitivity_table(max_units=10, adv_per_unit=400_000)
        col = [table.grid[r][table.base_col_index] for r in range(len(table.row_values))]
        assert col[0] > col[-1]
        assert col == sorted(col, reverse=True)

    def test_negative_cells_when_costs_dominate(self):
        """Low ADV + high cost corner should be upside-down."""
        table = build_sensitivity_table(
            max_units=10, adv_per_unit=250_000, construction_cost_psf=300, avg_unit_size_sqft=1200
        )
        # Bottom-left corner: highest cost, lowest ADV
        assert table.grid[-1][0] < 0

    def test_base_indices_point_to_unmodified_case(self):
        table = build_sensitivity_table(max_units=10, adv_per_unit=400_000)
        # Default variation has 0% at index 2.
        assert table.base_row_index == 2
        assert table.base_col_index == 2
        assert table.col_values[table.base_col_index] == 400_000

    def test_empty_when_no_units(self):
        table = build_sensitivity_table(adv_per_unit=400_000)
        assert table.grid == []
        assert any("Sensitivity unavailable" in n for n in table.notes)

    def test_empty_when_no_adv(self):
        table = build_sensitivity_table(density=_density(5))
        assert table.grid == []

    def test_regional_default_adv_drives_grid(self):
        """With no comps, the cost model's ADV default still builds a grid."""
        cost_model = get_cost_model("CA", "San Diego")  # ADV default 750k
        table = build_sensitivity_table(density=_density(4), cost_model=cost_model)
        assert table.col_values[table.base_col_index] == 750_000
        assert len(table.grid) == 5
