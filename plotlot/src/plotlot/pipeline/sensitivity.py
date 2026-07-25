"""Two-way sensitivity analysis for the residual land pro forma.

The residual max land offer hangs on a handful of uncertain assumptions. This
module sweeps the two most impactful — ADV per unit (revenue) and construction
cost per sqft (cost) — and recomputes the max land offer for each combination,
reusing :func:`plotlot.pipeline.proforma.calculate_land_pro_forma` so the base
cell always equals the headline number.

The output ``SensitivityTable`` shows developers their walk-away vs. stretch
price and where the deal stops penciling (negative residual).
"""

from __future__ import annotations

import logging

from plotlot.core.types import CompAnalysis, DensityAnalysis, SensitivityTable
from plotlot.pipeline.cost_model import RegionalCostModel
from plotlot.pipeline.proforma import calculate_land_pro_forma

logger = logging.getLogger(__name__)

# Default ± variation applied to each axis (percent), base case at 0.
DEFAULT_VARIATION_PCT: tuple[int, ...] = (-20, -10, 0, 10, 20)


def _base_index(variation_pct: tuple[int, ...]) -> int:
    """Index of the base case (the step closest to 0%)."""
    return min(range(len(variation_pct)), key=lambda i: abs(variation_pct[i]))


def build_sensitivity_table(
    density: DensityAnalysis | None = None,
    comps: CompAnalysis | None = None,
    *,
    max_units: int | None = None,
    adv_per_unit: float | None = None,
    cost_model: RegionalCostModel | None = None,
    construction_cost_psf: float | None = None,
    avg_unit_size_sqft: float | None = None,
    soft_cost_pct: float | None = None,
    builder_margin_pct: float | None = None,
    adv_variation_pct: tuple[int, ...] = DEFAULT_VARIATION_PCT,
    cost_variation_pct: tuple[int, ...] = DEFAULT_VARIATION_PCT,
) -> SensitivityTable:
    """Build a 2-way (ADV × construction cost) sensitivity table.

    Accepts the same inputs as ``calculate_land_pro_forma`` and resolves the
    base case through it, then sweeps both axes around the resolved base values.

    Returns:
        SensitivityTable. When the base case can't be priced (no units or no
        ADV available), the grid is empty and ``notes`` explains why.
    """
    base = calculate_land_pro_forma(
        density=density,
        comps=comps,
        max_units=max_units,
        adv_per_unit=adv_per_unit,
        cost_model=cost_model,
        construction_cost_psf=construction_cost_psf,
        avg_unit_size_sqft=avg_unit_size_sqft,
        soft_cost_pct=soft_cost_pct,
        builder_margin_pct=builder_margin_pct,
    )

    table = SensitivityTable()
    if base.max_units <= 0 or base.adv_per_unit <= 0:
        table.notes.append(
            "Sensitivity unavailable: base case needs both max units and an ADV per unit."
        )
        return table

    units = base.max_units
    base_adv = base.adv_per_unit
    base_cost = base.construction_cost_psf
    unit_size = base.avg_unit_size_sqft
    soft = base.soft_cost_pct
    margin = base.builder_margin_pct
    impact_fees = base.impact_fees_per_unit

    table.col_values = [round(base_adv * (1 + p / 100.0)) for p in adv_variation_pct]
    table.row_values = [round(base_cost * (1 + p / 100.0), 1) for p in cost_variation_pct]
    table.base_col_index = _base_index(adv_variation_pct)
    table.base_row_index = _base_index(cost_variation_pct)

    grid: list[list[float]] = []
    for cost in table.row_values:
        row: list[float] = []
        for adv in table.col_values:
            pf = calculate_land_pro_forma(
                max_units=units,
                adv_per_unit=adv,
                construction_cost_psf=cost,
                avg_unit_size_sqft=unit_size,
                soft_cost_pct=soft,
                builder_margin_pct=margin,
                impact_fees_per_unit=impact_fees,
            )
            row.append(round(pf.max_land_price, 2))
        grid.append(row)
    table.grid = grid
    table.base_value = grid[table.base_row_index][table.base_col_index]

    return table
