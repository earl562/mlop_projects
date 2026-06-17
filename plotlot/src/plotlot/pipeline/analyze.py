"""Full single-address analysis used by batch screening.

``lookup_address`` runs geocode → property → zoning → LLM extraction → density
(and extraction verification). This wraps it with the residual pro forma so a
report can be ranked by "what it's worth."

For batch screening the residual is computed from the **regional cost-model
ADV** by default (no per-address comparable-sales network call) — fast enough to
screen a list, with full comps reserved for the shortlist. Set ``with_comps`` to
pull live sold-unit comps for a deeper pass.
"""

from __future__ import annotations

import logging

from plotlot.core.types import ZoningReport
from plotlot.pipeline.comps import find_comparables
from plotlot.pipeline.cost_model import get_cost_model
from plotlot.pipeline.guardrails import check_residual_plausibility
from plotlot.pipeline.lookup import lookup_address
from plotlot.pipeline.proforma import calculate_land_pro_forma

logger = logging.getLogger(__name__)


async def analyze_property_full(address: str, *, with_comps: bool = False) -> ZoningReport | None:
    """Analyze an address and attach a residual pro forma for ranking.

    Args:
        address: Street address.
        with_comps: If True, run live comparable-sales lookup; otherwise rank on
            the regional cost-model ADV (faster for batch screening).

    Returns:
        ZoningReport with ``pro_forma`` populated, or None if geocoding fails.
    """
    report: ZoningReport | None = await lookup_address(address)
    if report is None:
        return None

    density = report.density_analysis
    if density is None or density.max_units <= 0:
        if density is not None and density.max_gla_sqft:
            report.warnings = list(report.warnings or []) + [
                "Commercial pro forma not yet implemented — only residential density is calculated."
            ]
        return report

    cost_model = get_cost_model(report.state, report.county)

    comps = None
    if with_comps and report.property_record and report.property_record.lat:
        try:
            comps = await find_comparables(report.property_record, state=report.state or "FL")
            report.comp_analysis = comps
        except Exception as exc:  # non-blocking — fall back to regional ADV
            logger.warning("Comps lookup failed for %s: %s", address[:60], exc)

    report.pro_forma = calculate_land_pro_forma(density=density, comps=comps, cost_model=cost_model)

    lot_sqft = report.property_record.lot_size_sqft if report.property_record else 0.0
    report.warnings = list(report.warnings or []) + check_residual_plausibility(
        density, lot_sqft, report.pro_forma
    )
    return report
