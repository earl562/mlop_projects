"""Conservative acquisition decisions derived from comps and residual value."""

from __future__ import annotations

import math

from plotlot.application.market.models import (
    AcquisitionDecision,
    AcquisitionDecisionInputs,
    AcquisitionDecisionStatus,
    CompStatus,
)


def build_acquisition_decision(
    inputs: AcquisitionDecisionInputs,
) -> AcquisitionDecision:
    """Build an evidence-backed review signal, never an autonomous purchase order."""

    comp_floor = (
        inputs.comps.valuation_low
        if inputs.comps.status == CompStatus.QUALIFIED
        else None
    )
    residual_ceiling = (
        inputs.residual_land_value
        if inputs.residual_land_value is not None
        and inputs.residual_land_value > 0
        else None
    )

    if comp_floor is None or residual_ceiling is None:
        reasons: list[str] = []
        questions: list[str] = []
        if comp_floor is None:
            reasons.append("Qualified comparable-sale support is unavailable.")
            questions.append("Obtain at least three qualified comparable sales.")
        if residual_ceiling is None:
            reasons.append(
                "A positive deterministic residual land-value ceiling is unavailable."
            )
            questions.append(
                "Complete deterministic feasibility and residual underwriting."
            )
        return AcquisitionDecision(
            status=AcquisitionDecisionStatus.INSUFFICIENT_EVIDENCE,
            purchase_price=inputs.purchase_price,
            comp_floor=comp_floor,
            residual_ceiling=residual_ceiling,
            pricing_signal="insufficient_evidence",
            reasons=tuple(reasons),
            open_questions=tuple(questions),
            evidence_ids=inputs.comps.evidence_ids,
        )

    supported_basis = min(comp_floor, residual_ceiling)
    if inputs.purchase_price is None:
        return AcquisitionDecision(
            status=AcquisitionDecisionStatus.HOLD_FOR_INPUTS,
            comp_floor=comp_floor,
            residual_ceiling=residual_ceiling,
            supported_basis=supported_basis,
            pricing_signal="price_required",
            reasons=("An explicit asking or purchase price is required.",),
            open_questions=("Provide the current asking or proposed purchase price.",),
            evidence_ids=inputs.comps.evidence_ids,
        )

    cushion_dollars = supported_basis - inputs.purchase_price
    tolerance = max(1e-6, supported_basis * 1e-9)
    if cushion_dollars < -tolerance:
        status = AcquisitionDecisionStatus.REJECT_BUY_BOX
        pricing_signal = "above_supported_basis"
        reasons = (
            "The supplied price exceeds the conservative supported basis by "
            f"${abs(cushion_dollars):,.0f}.",
        )
    elif math.isclose(cushion_dollars, 0.0, abs_tol=tolerance):
        status = AcquisitionDecisionStatus.HOLD_FOR_INPUTS
        pricing_signal = "at_supported_basis"
        cushion_dollars = 0.0
        reasons = (
            "The supplied price equals the conservative supported basis and "
            "leaves no modeled cushion.",
        )
    else:
        status = AcquisitionDecisionStatus.ADVANCE_FOR_REVIEW
        pricing_signal = "below_supported_basis"
        reasons = (
            f"The supplied price is ${cushion_dollars:,.0f} below the "
            "conservative supported basis.",
            "Advance means human diligence is warranted; it is not a purchase "
            "instruction.",
        )

    cushion_percent = (
        cushion_dollars / supported_basis * 100 if supported_basis > 0 else None
    )
    return AcquisitionDecision(
        status=status,
        purchase_price=inputs.purchase_price,
        comp_floor=comp_floor,
        residual_ceiling=residual_ceiling,
        supported_basis=supported_basis,
        cushion_dollars=round(cushion_dollars, 2),
        cushion_percent=(
            round(cushion_percent, 2) if cushion_percent is not None else None
        ),
        pricing_signal=pricing_signal,
        reasons=reasons,
        evidence_ids=inputs.comps.evidence_ids,
    )


__all__ = ["build_acquisition_decision"]
