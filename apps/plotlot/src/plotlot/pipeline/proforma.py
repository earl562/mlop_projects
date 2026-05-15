"""Residual land valuation pro forma for land deal intelligence.

Calculates the maximum land offer price using:
  GDV = Max Units × ADV per Unit
  Max Land Price = GDV - Hard Costs - Soft Costs - Builder Margin

This is the developer's "back into the land price" calculation used by
land wholesalers and builders to determine what they can pay for a site.
"""

from __future__ import annotations

import logging

from plotlot.core.types import CompAnalysis, DensityAnalysis, LandProForma

logger = logging.getLogger(__name__)

# Default construction costs by market (South Florida defaults)
DEFAULT_CONSTRUCTION_COST_PSF = 175.0  # multifamily
DEFAULT_AVG_UNIT_SIZE_SQFT = 1000.0  # average unit
DEFAULT_SOFT_COST_PCT = 20.0
DEFAULT_BUILDER_MARGIN_PCT = 25.0


def calculate_land_pro_forma(
    density: DensityAnalysis | None = None,
    comps: CompAnalysis | None = None,
    *,
    max_units: int | None = None,
    adv_per_unit: float | None = None,
    construction_cost_psf: float = DEFAULT_CONSTRUCTION_COST_PSF,
    avg_unit_size_sqft: float = DEFAULT_AVG_UNIT_SIZE_SQFT,
    soft_cost_pct: float = DEFAULT_SOFT_COST_PCT,
    builder_margin_pct: float = DEFAULT_BUILDER_MARGIN_PCT,
) -> LandProForma:
    """Calculate residual land value (max offer price).

    Args:
        density: DensityAnalysis from calculator (provides max_units)
        comps: CompAnalysis from comps step (provides adv_per_unit)
        max_units: Override max units (if density analysis unavailable)
        adv_per_unit: Override ADV per unit (if comps unavailable)
        construction_cost_psf: Construction cost per square foot
        avg_unit_size_sqft: Average unit size in sqft
        soft_cost_pct: Soft costs as % of hard costs
        builder_margin_pct: Builder margin as % of GDV

    Returns:
        LandProForma with calculated max land price
    """
    pf = LandProForma(
        construction_cost_psf=construction_cost_psf,
        avg_unit_size_sqft=avg_unit_size_sqft,
        soft_cost_pct=soft_cost_pct,
        builder_margin_pct=builder_margin_pct,
    )

    # Determine max units
    units = max_units
    if units is None and density is not None:
        units = density.max_units
    if units is None or units <= 0:
        pf.notes.append("Cannot calculate pro forma: no max units available")
        return pf
    pf.max_units = units

    # Determine ADV per unit
    adv = adv_per_unit
    if adv is None and comps is not None and comps.adv_per_unit:
        adv = comps.adv_per_unit
    if adv is None or adv <= 0:
        # Fall back to estimated land value / units if available
        if comps and comps.estimated_land_value > 0:
            pf.notes.append(
                f"No ADV per unit — estimated land value from comps: "
                f"${comps.estimated_land_value:,.0f}"
            )
            pf.max_land_price = comps.estimated_land_value
            return pf
        pf.notes.append(
            "Cannot calculate full pro forma: no ADV per unit available. "
            "Provide ADV (after-development value per unit) or recent new "
            "construction sales data."
        )
        return pf
    pf.adv_per_unit = adv

    # GDV = units × ADV
    pf.gross_development_value = units * adv

    # Hard costs = units × construction $/sf × avg sf/unit
    pf.hard_costs = units * construction_cost_psf * avg_unit_size_sqft

    # Soft costs = hard costs × soft_cost_pct
    pf.soft_costs = pf.hard_costs * (soft_cost_pct / 100)

    # Builder margin = GDV × margin_pct
    pf.builder_margin = pf.gross_development_value * (builder_margin_pct / 100)

    # Max land price = GDV - hard - soft - margin
    pf.max_land_price = (
        pf.gross_development_value - pf.hard_costs - pf.soft_costs - pf.builder_margin
    )

    # Cost per door
    total_costs = pf.hard_costs + pf.soft_costs
    pf.cost_per_door = total_costs / units if units > 0 else 0

    # Sanity checks
    if pf.max_land_price < 0:
        pf.notes.append(
            "Negative residual: development costs exceed GDV. "
            "This deal may not be feasible at current assumptions."
        )
    else:
        pf.notes.append(
            f"Max offer: ${pf.max_land_price:,.0f} (${pf.max_land_price / units:,.0f}/door)"
        )

    return pf
