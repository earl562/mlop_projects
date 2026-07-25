"""Residual land valuation pro forma for land deal intelligence.

Calculates the maximum land offer price using:
  GDV = Max Units × ADV per Unit
  Max Land Price = GDV - Hard Costs - Soft Costs - Builder Margin

This is the developer's "back into the land price" calculation used by
land wholesalers and builders to determine what they can pay for a site.

The after-development value (ADV) per unit is resolved in priority order:
  1. An explicit caller override
  2. Sold-unit comparables (CompAnalysis.adv_per_unit)
  3. The regional cost model's market default
  4. Last resort — the comps' estimated land value (no development residual)

Cost levers (hard cost $/sf, soft %, builder margin) come from the regional
cost model unless the caller overrides them, so a San Diego deal no longer
inherits South Florida construction costs.
"""

from __future__ import annotations

import logging

from plotlot.core.types import CompAnalysis, DensityAnalysis, LandProForma
from plotlot.pipeline.cost_model import RegionalCostModel

logger = logging.getLogger(__name__)

# Module-level fallbacks when neither a caller override nor a cost model is given.
DEFAULT_CONSTRUCTION_COST_PSF = 200.0
DEFAULT_AVG_UNIT_SIZE_SQFT = 1000.0
DEFAULT_SOFT_COST_PCT = 20.0
DEFAULT_BUILDER_MARGIN_PCT = 25.0


def _resolve_adv(
    adv_per_unit: float | None,
    comps: CompAnalysis | None,
    cost_model: RegionalCostModel | None,
) -> tuple[float | None, str]:
    """Resolve ADV per unit and its provenance per the priority chain."""
    if adv_per_unit is not None and adv_per_unit > 0:
        return adv_per_unit, "override"
    if comps is not None and comps.adv_per_unit and comps.adv_per_unit > 0:
        return comps.adv_per_unit, "comps"
    if cost_model is not None and cost_model.adv_per_unit_default > 0:
        return cost_model.adv_per_unit_default, "regional_default"
    return None, ""


def calculate_land_pro_forma(
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
    impact_fees_per_unit: float | None = None,
) -> LandProForma:
    """Calculate residual land value (max offer price).

    Args:
        density: DensityAnalysis from calculator (provides max_units).
        comps: CompAnalysis from comps step (provides adv_per_unit).
        max_units: Override max units (if density analysis unavailable).
        adv_per_unit: Override ADV per unit (highest priority).
        cost_model: Regional cost model; fills cost levers + a fallback ADV.
        construction_cost_psf: Override construction cost per square foot.
        avg_unit_size_sqft: Override average unit size in sqft.
        soft_cost_pct: Override soft costs as % of hard costs.
        builder_margin_pct: Override builder margin as % of GDV.
        impact_fees_per_unit: Government impact/development fees per unit; a real
            cost deducted from the residual. Defaults to the cost model's value
            (or 0 when no model is given).

    Returns:
        LandProForma with calculated max land price.
    """
    # Resolve cost levers: explicit override → cost model → module default.
    construction_cost_psf = (
        construction_cost_psf
        if construction_cost_psf is not None and construction_cost_psf > 0
        else (cost_model.construction_cost_psf if cost_model else DEFAULT_CONSTRUCTION_COST_PSF)
    )
    avg_unit_size_sqft = (
        avg_unit_size_sqft
        if avg_unit_size_sqft is not None and avg_unit_size_sqft > 0
        else (cost_model.avg_unit_size_sqft if cost_model else DEFAULT_AVG_UNIT_SIZE_SQFT)
    )
    soft_cost_pct = (
        soft_cost_pct
        if soft_cost_pct is not None
        else (cost_model.soft_cost_pct if cost_model else DEFAULT_SOFT_COST_PCT)
    )
    builder_margin_pct = (
        builder_margin_pct
        if builder_margin_pct is not None
        else (cost_model.builder_margin_pct if cost_model else DEFAULT_BUILDER_MARGIN_PCT)
    )
    impact_fees_per_unit = (
        impact_fees_per_unit
        if impact_fees_per_unit is not None
        else (cost_model.impact_fee_per_unit if cost_model else 0.0)
    )

    pf = LandProForma(
        construction_cost_psf=construction_cost_psf,
        avg_unit_size_sqft=avg_unit_size_sqft,
        soft_cost_pct=soft_cost_pct,
        builder_margin_pct=builder_margin_pct,
        impact_fees_per_unit=impact_fees_per_unit,
        market=cost_model.market if cost_model else "",
    )

    # Determine max units
    units = max_units
    if units is None and density is not None:
        units = density.max_units
    if units is None or units <= 0:
        pf.notes.append("Cannot calculate pro forma: no max units available")
        return pf
    pf.max_units = units

    # Determine ADV per unit + provenance
    adv, adv_source = _resolve_adv(adv_per_unit, comps, cost_model)
    if adv is None or adv <= 0:
        # Fall back to estimated land value / units if available
        if comps and comps.estimated_land_value > 0:
            pf.adv_source = "comps_land_value"
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
    pf.adv_source = adv_source

    # GDV = units × ADV
    pf.gross_development_value = units * adv

    # Hard costs = units × construction $/sf × avg sf/unit
    pf.hard_costs = units * construction_cost_psf * avg_unit_size_sqft

    # Soft costs = hard costs × soft_cost_pct
    pf.soft_costs = pf.hard_costs * (soft_cost_pct / 100)

    # Builder margin = GDV × margin_pct
    pf.builder_margin = pf.gross_development_value * (builder_margin_pct / 100)

    # Impact/development fees = units × per-unit fee
    pf.impact_fees = units * impact_fees_per_unit

    # Max land price = GDV - hard - soft - margin - impact fees
    pf.max_land_price = (
        pf.gross_development_value
        - pf.hard_costs
        - pf.soft_costs
        - pf.builder_margin
        - pf.impact_fees
    )

    # Cost per door
    total_costs = pf.hard_costs + pf.soft_costs + pf.impact_fees
    pf.cost_per_door = total_costs / units if units > 0 else 0

    if adv_source == "regional_default":
        pf.notes.append(
            f"ADV per unit is a {pf.market or 'regional'} market estimate "
            f"(${adv:,.0f}/unit) — no nearby sold-unit comps were available."
        )

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
