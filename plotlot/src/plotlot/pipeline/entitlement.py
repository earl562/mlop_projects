"""Entitlement path, timeline, and impact fees — "what it takes to build."

Beyond "how many units," a developer needs the approval path (by-right vs.
conditional-use vs. rezoning), a rough timeline, and the government fees to get
there. This module derives all of that deterministically:

  * The path is classified from the zoning use lists (with a residential
    zone-code fallback) — no LLM involvement, so no hallucination risk.
  * Impact fees come from the regional cost model.

The result feeds a "cost to build" line into the residual (via the pro forma's
impact-fee deduction) and an entitlement checklist into the report + Deal Paper.
"""

from __future__ import annotations

from plotlot.core.types import EntitlementAssessment, EntitlementStep, ZoningReport
from plotlot.pipeline.cost_model import get_cost_model

# Use-list keywords that indicate residential / multifamily development.
_RESIDENTIAL_KEYWORDS = (
    "multifamily",
    "multi-family",
    "multiple-family",
    "multiple family",
    "dwelling",
    "residential",
    "apartment",
    "townhouse",
    "town house",
    "duplex",
    "triplex",
    "fourplex",
    "four-plex",
    "two-family",
    "three-family",
    "four-family",
    "condominium",
)

# Zone-code prefixes that are inherently multifamily-residential.
_MF_CODE_PREFIXES = ("RM", "RD", "RH", "RMF", "MF")


def _has_residential(uses: list[str] | None) -> bool:
    if not uses:
        return False
    return any(any(k in (u or "").lower() for k in _RESIDENTIAL_KEYWORDS) for u in uses)


def _classify_path(report: ZoningReport) -> tuple[str, str]:
    """Return (path, note) classifying the residential entitlement path."""
    if _has_residential(report.allowed_uses):
        return "by_right", "Residential use is permitted by-right."
    if _has_residential(report.conditional_uses):
        return "conditional_use", "Residential use requires a conditional-use permit."
    if _has_residential(report.prohibited_uses):
        return "rezoning", "Residential use is prohibited — a rezoning would be required."

    # No clear signal from the use lists — fall back to the zone code.
    district = (report.zoning_district or "").upper()
    if district.startswith(_MF_CODE_PREFIXES):
        return "by_right", "Inferred by-right from a multifamily zone code (verify uses)."
    return "unknown", "Entitlement path could not be determined from zoning data."


def _steps_for_path(path: str, state: str, max_units: int) -> list[EntitlementStep]:
    """Deterministic step checklist for an entitlement path."""
    steps: list[EntitlementStep] = []

    if path == "rezoning":
        steps.append(
            EntitlementStep(
                "Rezoning / General Plan amendment",
                "required",
                9.0,
                "Legislative approval — public hearings, uncertain outcome.",
            )
        )
    if path == "conditional_use":
        steps.append(
            EntitlementStep(
                "Conditional-use permit / public hearing",
                "required",
                4.0,
                "Discretionary approval before a planning commission.",
            )
        )

    # California discretionary projects typically trigger CEQA review.
    if state.upper() == "CA" and path in ("conditional_use", "rezoning"):
        steps.append(
            EntitlementStep(
                "CEQA environmental review",
                "likely",
                6.0,
                "California Environmental Quality Act — a common timeline driver.",
            )
        )

    if path != "unknown":
        steps.append(
            EntitlementStep(
                "Site plan / design review",
                "likely",
                3.0,
                "Staff or board review of the site layout.",
            )
        )
        if max_units >= 2:
            steps.append(
                EntitlementStep(
                    "Subdivision / final map (if creating lots)",
                    "conditional",
                    4.0,
                    "Required only if the project subdivides land.",
                )
            )
        steps.append(
            EntitlementStep(
                "Building permit",
                "required",
                2.0,
                "Plan check and permit issuance before construction.",
            )
        )
    else:
        steps.append(
            EntitlementStep(
                "Confirm entitlement path with planning department",
                "required",
                0.0,
                "Zoning use data was inconclusive.",
            )
        )

    return steps


def assess_entitlement(report: ZoningReport) -> EntitlementAssessment:
    """Assess the residential entitlement path, timeline, and impact fees."""
    assessment = EntitlementAssessment()

    path, _note = _classify_path(report)
    assessment.path = path
    assessment.complexity = {
        "by_right": "low",
        "conditional_use": "medium",
        "rezoning": "high",
    }.get(path, "unknown")

    max_units = report.density_analysis.max_units if report.density_analysis else 0
    assessment.steps = _steps_for_path(path, report.state, max_units)
    assessment.est_timeline_months = round(sum(s.timeline_months for s in assessment.steps), 1)

    # Impact fees: prefer a real itemized jurisdiction schedule when one is
    # registered; otherwise fall back to the coarse regional aggregate.
    from plotlot.pipeline.fee_schedule import get_fee_schedule

    schedule = get_fee_schedule(report.state, report.county)
    # A schedule sets the fee total only when it covers ALL per-unit fees. A partial
    # schedule (SD city DIFs only) keeps the conservative coarse aggregate so the
    # entitlement fee total is never understated (RTCIP/school/utility are separate).
    if schedule is not None and schedule.is_itemized and schedule.covers_all_fees:
        assessment.fee_market = schedule.jurisdiction
        assessment.impact_fee_per_unit = schedule.total_per_unit
    else:
        cost_model = get_cost_model(report.state, report.county)
        assessment.fee_market = cost_model.market
        assessment.impact_fee_per_unit = cost_model.impact_fee_per_unit
    assessment.impact_fees_total = assessment.impact_fee_per_unit * max_units

    # Utilities — we don't yet have a utility GIS feed, so flag honestly.
    assessment.utilities_note = (
        "Utility availability not verified — confirm water, sewer, and power service "
        "(or extension cost) at the site with the local utility provider."
    )

    if path == "rezoning":
        assessment.warnings.append(
            "Rezoning path: long, discretionary, and not guaranteed — budget time and risk."
        )
    elif path == "unknown":
        assessment.warnings.append(
            "Entitlement path unknown — treat timeline and fees as placeholders."
        )

    return assessment
