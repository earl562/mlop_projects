"""Entitlement timeline risk — real-time enhancement of the base entitlement assessment.

Augments the deterministic ``EntitlementAssessment`` (path, hardcoded step
timelines) with:
  1. Real CEQA filings from CEQAnet (CA only), matched to the parcel via
     ``pipeline/ceqanet.py``. Strong (parcel-confirmed) matches may drive the
     range/confidence; weaker candidates are carried separately for display and
     never drive anything.
  2. Active permit data from the existing ``permits.py`` pipeline (real data).
  3. Timeline risk range (optimistic vs pessimistic) and confidence level.

All external calls degrade gracefully — a failure in any single data source
does not block the assessment; it just lowers confidence.
"""

from __future__ import annotations

import logging

from plotlot.core.types import CEQADocument, EntitlementTimelineRisk

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Timeline risk estimation
# ---------------------------------------------------------------------------

# Deterministic base range per entitlement path (optimistic, pessimistic months).
_TIMELINE_RANGES: dict[str, tuple[float, float]] = {
    "by_right": (2.0, 6.0),
    "conditional_use": (6.0, 18.0),
    "rezoning": (12.0, 36.0),
    "unknown": (0.0, 0.0),
}


def _estimate_timeline_range(
    path: str,
    strong_ceqa: list[CEQADocument],
    complexity: str,
) -> tuple[float, float, list[str]]:
    """Compute (min_months, max_months, key_drivers) for the entitlement path.

    The base range is deterministic (entitlement path + complexity). STRONG CEQA
    matches are REAL filings confirmed on this parcel, so they legitimately
    extend the range (an active EIR genuinely implies a 12–24mo review) and add
    SCH-cited drivers. Candidate (Tier 2) matches are NOT passed here and never
    affect the range.
    """
    base_min, base_max = _TIMELINE_RANGES.get(path, (0.0, 0.0))
    drivers: list[str] = []

    if path == "conditional_use":
        drivers.append("CUP requires a public hearing before the planning commission")
    if path == "rezoning":
        drivers.append(
            "Rezoning is a legislative act — multiple public hearings, uncertain outcome"
        )

    # Pessimistic adjustment for complexity (deterministic).
    if complexity == "high":
        base_max = max(base_max * 1.5, base_max + 6.0)
        if path != "rezoning":
            drivers.append("High complexity path — appeals and resubmittals likely")
    elif complexity == "medium":
        base_max = max(base_max * 1.25, base_max + 3.0)

    # Strong, parcel-confirmed CEQA filings adjust the range by review stage.
    for d in strong_ceqa:
        sch = f" (SCH {d.sch_number})" if d.sch_number else ""
        if d.status == "in_progress" and d.doc_type == "EIR":
            base_min = max(base_min, 12.0)
            base_max = max(base_max, 24.0)
            drivers.append(
                f"Active EIR on file for this parcel{sch} — 12–24 month environmental review"
            )
        elif d.status == "in_progress" and d.doc_type in ("MND", "ND"):
            base_max = max(base_max, base_min + 8.0)
            drivers.append(
                f"Active {d.doc_type} on file for this parcel{sch} — ~3–8 month "
                "environmental review"
            )
        elif d.status in ("completed", "exempt"):
            label = "exemption (NOE)" if d.status == "exempt" else "determination (NOD)"
            drivers.append(
                f"CEQA {label} already on file for this parcel{sch} — environmental review complete"
            )

    return round(base_min, 1), round(base_max, 1), drivers


# ---------------------------------------------------------------------------
# Permit data check
# ---------------------------------------------------------------------------


async def _check_active_permits(apn: str, county: str) -> bool:
    """Check if the parcel has active permits via the existing permit pipeline.

    ``apn`` is the Assessor Parcel Number (folio) — required by the Accela
    permit system, not interchangeable with the street address.
    """
    if not apn:
        return False
    try:
        from plotlot.pipeline.permits import fetch_development_signals

        signals = await fetch_development_signals(apn, county)
        if signals:
            active = signals.get("active_permit_count", 0) if isinstance(signals, dict) else 0
            return int(active) > 0
        return False
    except Exception as exc:
        logger.debug("Permit check failed for %s: %s", apn, exc)
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _risk_level(est_min: float, est_max: float) -> str:
    if est_max >= 24:
        return "high"
    if est_max >= 12:
        return "moderate"
    if est_max <= 0:
        return "unknown"
    return "low"


async def assess_timeline_risk(
    address: str,
    municipality: str,
    county: str,
    state: str,
    entitlement_path: str,
    entitlement_complexity: str,
    apn: str = "",
    lat: float | None = None,
    lng: float | None = None,
    parcel_zip: str = "",
    owner: str = "",
) -> EntitlementTimelineRisk:
    """Assess entitlement timeline risk with live data augmentations.

    Pulls real CEQA filings (CA) matched to the parcel, checks active permits,
    and returns a risk range. Strong CEQA matches and active permits raise
    confidence; candidate CEQA matches are carried for display only.
    """
    strong_ceqa: list[CEQADocument] = []
    candidate_ceqa: list[CEQADocument] = []
    if state.upper() == "CA":
        try:
            from plotlot.pipeline.ceqanet import find_parcel_ceqa

            strong_ceqa, candidate_ceqa = await find_parcel_ceqa(
                county=county,
                city=municipality,
                parcel_apn=apn,
                parcel_lat=lat,
                parcel_lng=lng,
                parcel_zip=parcel_zip,
                parcel_address=address,
                owner=owner,
            )
        except Exception as exc:
            logger.debug("CEQAnet lookup failed in assess_timeline_risk: %s", exc)

    try:
        active_permits = await _check_active_permits(apn, county)
    except Exception as exc:
        logger.debug("Permit check failed in assess_timeline_risk: %s", exc)
        active_permits = False

    est_min, est_max, drivers = _estimate_timeline_range(
        entitlement_path, strong_ceqa, entitlement_complexity
    )

    data_sources: list[str] = []
    if strong_ceqa or candidate_ceqa:
        data_sources.append("CEQAnet — State Clearinghouse (ceqanet.lci.ca.gov)")
    if active_permits:
        data_sources.append("County permit system (Accela)")

    # Strong CEQA matches are parcel-confirmed real filings → high confidence.
    # Active permits are real but coarser → medium. Otherwise low.
    if strong_ceqa:
        confidence = "high"
    elif active_permits:
        confidence = "medium"
    else:
        confidence = "low"

    risk = EntitlementTimelineRisk(
        est_months_min=est_min,
        est_months_max=est_max,
        risk_level=_risk_level(est_min, est_max),
        confidence=confidence,
        key_drivers=drivers,
        ceqa_documents=strong_ceqa,
        ceqa_candidates=candidate_ceqa,
        active_permits_exist=active_permits,
        data_sources=data_sources,
    )

    if active_permits and est_min > 0:
        risk.notes.append(
            "Parcel has active permits — some approvals may already be in process, "
            "which could shorten the remaining timeline."
        )
    if strong_ceqa:
        risk.notes.append(
            f"{len(strong_ceqa)} CEQA filing(s) confirmed on this parcel — see the SCH "
            "link(s) for the official record."
        )
    elif candidate_ceqa:
        risk.notes.append(
            f"No CEQA filing confirmed on this parcel; {len(candidate_ceqa)} nearby/possible "
            "filing(s) are listed separately for verification — they do not affect the timeline."
        )
    elif state.upper() == "CA":
        risk.notes.append(
            "No CEQA filings found for this parcel in CEQAnet (State Clearinghouse). "
            "Not all local CEQA actions are submitted to the SCH — confirm with the city."
        )

    return risk
