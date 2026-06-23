"""Entitlement timeline risk — real-time enhancement of the base entitlement assessment.

Augments the deterministic ``EntitlementAssessment`` (path, hardcoded step
timelines) with live checks:
  1. CEQAnet web search for CEQA documents on the parcel (CA only).
  2. Active permit data from the existing ``permits.py`` pipeline.
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
# CEQAnet web search — uses the LLM to find CEQA documents for a parcel
# ---------------------------------------------------------------------------


async def _search_ceqanet(address: str, municipality: str) -> list[CEQADocument]:
    """Search CEQAnet via the LLM for CEQA documents near the given address.

    Returns an empty list on any failure — this is a soft data source.
    """
    try:
        from plotlot.retrieval.llm import call_llm

        search_prompt = (
            "Search the web for CEQA documents filed with the State Clearinghouse "
            f"(ceqanet.lci.ca.gov or ceqanet.opr.ca.gov) for this address: "
            f"{address}, {municipality}, California. "
            "Look for environmental impact reports, negative declarations, mitigated "
            "negative declarations, categorical exemptions, or notices of determination. "
            "Return a JSON array of objects with keys: doc_type (EIR/MND/ND/CE/Other), "
            "status, description, lead_agency, source_url, and filed_date (YYYY-MM-DD). "
            "If no documents found, return an empty array []. "
            "Only return valid JSON, nothing else."
        )
        response = await call_llm(
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise search tool. Return only valid JSON.",
                },
                {"role": "user", "content": search_prompt},
            ],
        )
        result = (response or {}).get("content", "")
        docs = _parse_ceqa_llm_response(result)
        if docs:
            logger.info("CEQAnet search returned %d document(s) for %s", len(docs), address)
        return docs
    except Exception as exc:
        logger.debug("CEQAnet search failed for %s: %s", address, exc)
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

_CEQA_EXTENSION: dict[str, tuple[float, float]] = {
    "CE": (0.0, 0.0),  # exempt — no timeline impact
    "ND": (3.0, 6.0),
    "MND": (4.0, 8.0),
    "EIR": (12.0, 24.0),
    "Other": (3.0, 6.0),
}


def _estimate_timeline_range(
    path: str,
    ceqa_docs: list[CEQADocument],
    complexity: str,
) -> tuple[float, float, list[str]]:
    """Compute (min_months, max_months, key_drivers) from path and live data."""
    base_min, base_max = _TIMELINE_RANGES.get(path, (0.0, 0.0))
    drivers: list[str] = []

    # Adjust for CEQA — the biggest timeline multiplier
    max_ceqa_months = 0.0
    for doc in ceqa_docs:
        c_min, c_max = _CEQA_EXTENSION.get(doc.doc_type, (3.0, 6.0))
        max_ceqa_months = max(max_ceqa_months, c_max)
        if doc.doc_type == "EIR":
            drivers.append("Full EIR identified — 12–24 month environmental review")
        elif doc.doc_type == "MND":
            drivers.append("Mitigated Negative Declaration — ~6 month environmental review")
        elif doc.doc_type == "CE":
            drivers.append("Categorical exemption — minimal CEQA timeline impact")

    if max_ceqa_months > 0 and path == "by_right":
        # CEQA can apply even to by-right if the project triggers discretionary review
        base_max = max(base_max, max_ceqa_months + 3.0)

    if path == "conditional_use":
        drivers.append("CUP requires a public hearing before the planning commission")
        if max_ceqa_months > 6:
            drivers.append("CEQA runs concurrently but may delay the hearing date")

    if path == "rezoning":
        drivers.append(
            "Rezoning is a legislative act — multiple public hearings, uncertain outcome"
        )

    # Pessimistic adjustment for complexity
    if complexity == "high":
        base_max = max(base_max * 1.5, base_max + 6.0)
        if "rezoning" not in str(drivers).lower():
            drivers.append("High complexity path — appeals and resubmittals likely")
    elif complexity == "medium":
        base_max = max(base_max * 1.25, base_max + 3.0)

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
            active = signals.get("active_permits", 0) if isinstance(signals, dict) else 0
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
            ceqa_docs = await _search_ceqanet(address, municipality)
        except Exception as exc:
            logger.debug("CEQAnet search failed in assess_timeline_risk: %s", exc)

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
        data_sources.append("CEQAnet (State Clearinghouse)")
    if active_permits:
        data_sources.append("County permit system (Accela)")

    risk = EntitlementTimelineRisk(
        est_months_min=est_min,
        est_months_max=est_max,
        risk_level=_risk_level(est_min, est_max),
        confidence="medium" if ceqa_docs or active_permits else "low",
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
    if not ceqa_docs and state.upper() == "CA":
        risk.notes.append(
            "No CEQA documents found via CEQAnet search — the project may not yet have "
            "filed environmental review, or may qualify for a categorical exemption."
        )

    return risk
