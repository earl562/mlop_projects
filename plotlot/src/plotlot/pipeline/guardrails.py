"""Deterministic plausibility guardrails for the residual valuation.

The residual pro forma, sensitivity table, and Deal Paper are all pure
arithmetic — they never call the LLM. But they consume ``max_units``, which is
computed by the deterministic calculator from LLM-*extracted* zoning parameters.
If the LLM hallucinates a density (as happened on a San Diego land parcel), the
calculator faithfully produces too many units and the residual prints a
confident — but wrong — dollar figure.

These checks run after the calculator and flag inputs that are implausible or
uncorroborated, so a human verifies before trusting the number. They are
non-destructive: they raise warnings, they never silently change a result.
"""

from __future__ import annotations

from plotlot.core.types import DensityAnalysis, LandProForma

SQFT_PER_ACRE = 43_560

# Above this implied residential density, a result is almost certainly an
# extraction error outside a true downtown high-rise — worth a human check.
MAX_PLAUSIBLE_UNITS_PER_ACRE = 300.0


def check_residual_plausibility(
    density: DensityAnalysis | None,
    lot_size_sqft: float,
    pro_forma: LandProForma | None = None,
) -> list[str]:
    """Return human-readable warnings for implausible/uncorroborated inputs.

    Args:
        density: DensityAnalysis from the calculator.
        lot_size_sqft: Subject lot size.
        pro_forma: Optional residual pro forma (for ADV provenance).

    Returns:
        A list of warning strings (empty when everything looks sound).
    """
    warnings: list[str] = []
    if density is None or density.max_units <= 0 or lot_size_sqft <= 0:
        return warnings

    units = density.max_units

    # 1. Gross over-count — implied density far above anything but a high-rise.
    acres = lot_size_sqft / SQFT_PER_ACRE
    if acres > 0:
        implied_dpa = units / acres
        if implied_dpa > MAX_PLAUSIBLE_UNITS_PER_ACRE:
            warnings.append(
                f"Implied density is {implied_dpa:,.0f} units/acre "
                f"({units} units on {lot_size_sqft:,.0f} sqft) — unusually high. "
                f"Verify the zoning density before relying on the offer price."
            )

    # 2. Uncorroborated unit count — a single constraint with nothing to check
    #    it against (the calculator marks this 'low'). This is the failure mode
    #    where one hallucinated density value drives the whole result.
    if density.confidence == "low":
        governing = density.governing_constraint or "a single constraint"
        warnings.append(
            f"Max units ({units}) was derived from {governing} with no corroborating "
            f"zoning constraint — verify the buildable unit count against the ordinance."
        )

    # 3. ADV provenance — residual built on a regional estimate, not local comps.
    if pro_forma is not None and pro_forma.adv_source == "regional_default":
        warnings.append(
            "ADV per unit is a regional market estimate, not local sold-unit comps — "
            "confirm exit pricing before treating the offer as firm."
        )

    return warnings
