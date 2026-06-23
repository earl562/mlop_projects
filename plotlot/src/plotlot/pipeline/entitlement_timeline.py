"""Entitlement timeline risk — real-time enhancement of the base entitlement assessment.

Augments the deterministic ``EntitlementAssessment`` (path, hardcoded step
timelines) with:
  1. LLM-suggested CEQA document leads (CA only) — UNVERIFIED, not a live
     lookup; advisory drivers only, they never move the headline range.
  2. Active permit data from the existing ``permits.py`` pipeline (real data).
  3. Timeline risk range (optimistic vs pessimistic) and confidence level.

All external calls degrade gracefully — a failure in any single data source
does not block the assessment; it just lowers confidence.
"""

from __future__ import annotations

import json
import logging
import re

from plotlot.core.types import CEQADocument, EntitlementTimelineRisk

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CEQA document suggestions — the LLM proposes UNVERIFIED leads (no web access)
# ---------------------------------------------------------------------------


async def _suggest_ceqa_documents(address: str, municipality: str) -> list[CEQADocument]:
    """Ask the LLM which CEQA documents MIGHT apply to a parcel.

    IMPORTANT: this is NOT a live CEQAnet lookup. ``call_llm`` has no web
    access, so these are the model's UNVERIFIED suggestions from training
    knowledge — leads for a human to confirm against CEQAnet, never facts.
    Returns an empty list on any failure.
    """
    try:
        from plotlot.retrieval.llm import call_llm

        search_prompt = (
            "Based only on your existing knowledge (you do NOT have web access), "
            "identify any CEQA environmental-review documents that may be associated "
            f"with, or likely required for, development at {address}, {municipality}, "
            "California. These will be treated as UNVERIFIED leads to confirm against "
            "CEQAnet — do NOT fabricate filing numbers, dates, or URLs you are not "
            "confident about; omit any field you do not know. "
            "Return a JSON array of objects with keys: doc_type (EIR/MND/ND/CE/Other), "
            "status, description, lead_agency, source_url, and filed_date (YYYY-MM-DD). "
            "If you know of none, return an empty array []. Only return valid JSON."
        )
        response = await call_llm(
            messages=[
                {
                    "role": "system",
                    "content": "Return only valid JSON. Never invent unverifiable specifics.",
                },
                {"role": "user", "content": search_prompt},
            ],
        )
        result = (response or {}).get("content", "")
        docs = _parse_ceqa_llm_response(result)
        if docs:
            logger.info("CEQA leads suggested: %d for %s (unverified)", len(docs), address)
        return docs
    except Exception as exc:
        logger.debug("CEQA suggestion failed for %s: %s", address, exc)
        return []


def _parse_ceqa_llm_response(raw: str) -> list[CEQADocument]:
    """Extract a JSON array of CEQADocument from an LLM response."""
    raw = raw.strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        raw = raw.rsplit("\n", 1)[0] if raw.endswith("```") else raw
        raw = raw.strip()
    # Try to find a JSON array in the response
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if not m:
        return []
    try:
        entries = json.loads(m.group())
    except (json.JSONDecodeError, TypeError):
        return []
    docs: list[CEQADocument] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        doc_type = str(entry.get("doc_type", "Other"))
        docs.append(
            CEQADocument(
                doc_type=doc_type if doc_type in ("EIR", "MND", "ND", "CE", "Other") else "Other",
                status=str(entry.get("status", "")),
                filed_date=str(entry.get("filed_date", "")),
                description=str(entry.get("description", "")),
                lead_agency=str(entry.get("lead_agency", "")),
                source_url=str(entry.get("source_url", "")),
            )
        )
    return docs


# ---------------------------------------------------------------------------
# Timeline risk estimation
# ---------------------------------------------------------------------------

# Timeline multipliers per complexity level
# Optimistic = best-case processing (fast-track, cooperative board)
# Pessimistic = worst-case (appeals, resubmittals, full EIR)
_TIMELINE_RANGES: dict[str, tuple[float, float]] = {
    "by_right": (2.0, 6.0),
    "conditional_use": (6.0, 18.0),
    "rezoning": (12.0, 36.0),
    "unknown": (0.0, 0.0),
}


def _estimate_timeline_range(
    path: str,
    ceqa_docs: list[CEQADocument],
    complexity: str,
) -> tuple[float, float, list[str]]:
    """Compute (min_months, max_months, key_drivers) for the entitlement path.

    The headline range is DETERMINISTIC — derived only from the entitlement
    path and its complexity. CEQA documents are unverified LLM-suggested leads
    (see ``_suggest_ceqa_documents``); they are surfaced as advisory drivers to
    verify, but never move the headline range or the risk level.
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

    # CEQA leads are UNVERIFIED — advisory only, no effect on the range/risk.
    for doc in ceqa_docs:
        if doc.doc_type == "EIR":
            drivers.append(
                "Possible EIR (unverified lead — confirm via CEQAnet): a full EIR "
                "would add ~12–24 months of environmental review"
            )
        elif doc.doc_type == "MND":
            drivers.append(
                "Possible Mitigated Negative Declaration (unverified lead): "
                "~4–8 months of environmental review"
            )
        elif doc.doc_type == "ND":
            drivers.append(
                "Possible Negative Declaration (unverified lead): ~3–6 months "
                "of environmental review"
            )
        elif doc.doc_type == "CE":
            drivers.append(
                "Possible categorical exemption (unverified lead): minimal CEQA timeline impact"
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
) -> EntitlementTimelineRisk:
    """Assess entitlement timeline risk with live data augmentations.

    Called after the base ``EntitlementAssessment`` to add real-time data:
    CEQAnet search (CA only), permit status, and a risk range.
    """
    ceqa_docs: list[CEQADocument] = []
    if state.upper() == "CA":
        try:
            ceqa_docs = await _suggest_ceqa_documents(address, municipality)
        except Exception as exc:
            logger.debug("CEQA suggestion failed in assess_timeline_risk: %s", exc)

    try:
        active_permits = await _check_active_permits(apn, county)
    except Exception as exc:
        logger.debug("Permit check failed in assess_timeline_risk: %s", exc)
        active_permits = False

    est_min, est_max, drivers = _estimate_timeline_range(
        entitlement_path, ceqa_docs, entitlement_complexity
    )

    data_sources: list[str] = []
    if ceqa_docs:
        data_sources.append("LLM-suggested CEQA leads (unverified — confirm via CEQAnet)")
    if active_permits:
        data_sources.append("County permit system (Accela)")

    risk = EntitlementTimelineRisk(
        est_months_min=est_min,
        est_months_max=est_max,
        risk_level=_risk_level(est_min, est_max),
        # Only real permit data raises confidence; unverified CEQA leads never do.
        confidence="medium" if active_permits else "low",
        key_drivers=drivers,
        ceqa_documents=ceqa_docs,
        active_permits_exist=active_permits,
        data_sources=data_sources,
    )

    if active_permits and est_min > 0:
        risk.notes.append(
            "Parcel has active permits — some approvals may already be in process, "
            "which could shorten the remaining timeline."
        )
    if ceqa_docs:
        risk.notes.append(
            "Listed CEQA documents are unverified LLM suggestions, not confirmed "
            "filings — verify each against CEQAnet before relying on them."
        )
    elif state.upper() == "CA":
        risk.notes.append(
            "No CEQA leads were suggested for this parcel — confirm environmental "
            "status directly via CEQAnet (ceqanet.lci.ca.gov); this is not a live lookup."
        )

    return risk
