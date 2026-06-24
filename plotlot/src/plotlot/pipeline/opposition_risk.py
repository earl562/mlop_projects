"""Neighbor / political opposition risk — qualitative heuristic assessment.

No centralized data source exists for opposition risk. This module uses:
  1. Deterministic rules based on parcel context (density delta, zone type).
  2. An LLM-based qualitative assessment when the LLM is available.
  3. LLM-suggested possible controversies — UNVERIFIED leads from the model's
     training knowledge (``call_llm`` has no web access), surfaced but not scored.

Every output is labeled as LOW confidence / qualitative — this is NOT a
data-driven model. It surfaces risk factors a human should investigate,
not predictions to act on without verification.
"""

from __future__ import annotations

import json
import logging
import re

from plotlot.core.types import OppositionRiskAssessment

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Deterministic risk rules
# ---------------------------------------------------------------------------


def _density_delta_description(
    max_units: int | None,
    zoning_district: str,
    municipality: str,
) -> tuple[str, list[str]]:
    """Describe the density context and return risk flags.

    Returns (description, flags).
    """
    if not max_units or max_units <= 0:
        return "Density not determined — cannot assess opposition context.", []
    flags: list[str] = []

    if max_units >= 50:
        desc = (
            f"Large project ({max_units}+ units) — likely to draw planning board and "
            f"neighborhood attention regardless of zoning compliance."
        )
        flags.append(f"Project scale ({max_units} units) — larger projects face higher scrutiny")
    elif max_units >= 10:
        desc = (
            f"Medium-density project ({max_units} units) — opposition risk depends on "
            f"neighborhood character and the degree of change from existing uses."
        )
        flags.append(f"Project density ({max_units} units) may exceed surrounding density")
    else:
        desc = (
            f"Low-density project ({max_units} units) — lower community profile, "
            f"but still subject to design review and neighbor notice requirements."
        )

    # Single-family zone flag
    sf_prefixes = ("R-1", "RS", "R1", "RE", "RA", "RSF", "ER")
    if zoning_district and zoning_district.upper().startswith(sf_prefixes):
        flags.append(
            "Located in a single-family zone — multifamily development here is likely "
            "to face community opposition"
        )
        desc += " The property is in a single-family zone, which increases opposition risk."

    return desc, flags


# ---------------------------------------------------------------------------
# LLM-based qualitative assessment
# ---------------------------------------------------------------------------


async def _llm_opposition_assessment(
    address: str,
    municipality: str,
    county: str,
    max_units: int,
    zoning_district: str,
) -> str:
    """Ask the LLM for a qualitative opposition risk assessment.

    Uses the existing LLM pipeline (Claude/Gemini/NIM fallback chain).
    Returns a plain-language paragraph or empty string on failure.
    """
    try:
        from plotlot.retrieval.llm import call_llm

        prompt = (
            f"You are a real estate development risk analyst. Assess the neighbor and "
            f"political opposition risk for this property:\n"
            f"Address: {address}\n"
            f"Municipality: {municipality}, {county}\n"
            f"Zoning: {zoning_district}\n"
            f"Proposed density: {max_units} units\n\n"
            f"Consider: (1) Is the proposed density a significant change from the surrounding "
            f"neighborhood? (2) Has this municipality seen recent opposition to similar "
            f"projects? (3) What specific risk factors should a developer investigate?\n\n"
            f"Return a concise 2-3 paragraph qualitative assessment. Be honest about what "
            f"you don't know. This is a LOW confidence assessment — do not fabricate specific "
            f"meeting dates, opposition groups, or legal challenges you cannot verify."
        )
        response = await call_llm(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a real estate risk analyst. Provide a qualitative assessment of "
                        "opposition risk. Be concise and honest about uncertainty. Do not fabricate "
                        "specific facts you cannot verify."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )
        result = (response or {}).get("content", "")
        return result.strip() if result else ""
    except Exception as exc:
        logger.debug("LLM opposition assessment failed: %s", exc)
        return ""


# ---------------------------------------------------------------------------
# LLM-suggested possible controversies (UNVERIFIED — no web access)
# ---------------------------------------------------------------------------


async def _suggest_possible_controversies(municipality: str) -> list[str]:
    """Ask the LLM for POSSIBLE recent planning controversies in a municipality.

    IMPORTANT: ``call_llm`` has no web access, so these are unverified leads
    from the model's training knowledge, not live search results. Returns a
    list of suggested leads or an empty list.
    """
    try:
        from plotlot.retrieval.llm import call_llm

        prompt = (
            f"Based only on your existing knowledge (you do NOT have web access), "
            f"list any notable planning-board or zoning controversies, neighbor "
            f"opposition, or public-hearing disputes you are aware of in {municipality}, "
            f"focused on residential development. These are UNVERIFIED leads — do not "
            f"fabricate specifics you are unsure of. Return a JSON array of strings, each "
            f"a 1-sentence lead. If you know of none, return []. Return ONLY valid JSON."
        )
        response = await call_llm(
            messages=[
                {
                    "role": "system",
                    "content": "Return only valid JSON. Never invent unverifiable specifics.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        raw = (response or {}).get("content", "")
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            raw = raw.rsplit("\n", 1)[0] if raw.endswith("```") else raw
            raw = raw.strip()
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if m:
            items = json.loads(m.group())
            if isinstance(items, list):
                return [str(i) for i in items if i]
        return []
    except Exception as exc:
        logger.debug("Controversy suggestion failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Risk level heuristic
# ---------------------------------------------------------------------------


def _heuristic_risk_level(max_units: int, flags: list[str], sf_zone: bool) -> str:
    """Determine risk level from deterministic rules.

    Returns "low" | "moderate" | "high" | "unknown".
    """
    score = 0
    if max_units >= 50:
        score += 4
    elif max_units >= 20:
        score += 3
    elif max_units >= 10:
        score += 2
    elif max_units >= 5:
        score += 1
    if sf_zone:
        score += 3
    score += len(flags) * 2

    if score >= 6:
        return "high"
    if score >= 3:
        return "moderate"
    return "low"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def assess_opposition_risk(
    address: str,
    municipality: str,
    county: str,
    state: str,
    max_units: int | None,
    zoning_district: str,
    lat: float | None = None,
    lng: float | None = None,
) -> OppositionRiskAssessment:
    """Assess neighbor/political opposition risk for a parcel.

    All calls degrade gracefully. The result is labeled as LOW confidence
    because this is inherently a qualitative assessment.
    """
    sf_zone = bool(
        zoning_district and zoning_district.upper().startswith(("R-1", "RS", "R1", "RE", "RA"))
    )

    desc, det_flags = _density_delta_description(max_units, zoning_district, municipality)

    all_flags = list(det_flags)

    # Unverified LLM-suggested controversy leads — surfaced but NOT scored.
    try:
        controversies = await _suggest_possible_controversies(municipality)
    except Exception as exc:
        logger.debug("Controversy suggestion failed: %s", exc)
        controversies = []
    if controversies:
        all_flags.append(
            f"Possible controversies in {municipality} to verify "
            f"(LLM-suggested, unverified): {'; '.join(controversies[:3])}"
        )

    # LLM qualitative assessment (runs with reasonable timeout)
    assessment_text = ""
    if max_units and max_units > 0:
        try:
            assessment_text = await _llm_opposition_assessment(
                address, municipality, county, max_units, zoning_district
            )
        except Exception as exc:
            logger.debug("LLM opposition assessment failed: %s", exc)

    # Risk level is driven by DETERMINISTIC factors only (density, zone type) —
    # unverified controversy leads are surfaced but never raise the score.
    risk_level = _heuristic_risk_level(max_units or 0, det_flags, sf_zone)

    data_sources = ["Heuristic rules (density delta, zone type)"]
    if controversies:
        data_sources.append("LLM-suggested controversy leads (unverified)")
    if assessment_text:
        data_sources.append("LLM-based qualitative analysis (low confidence)")

    return OppositionRiskAssessment(
        risk_level=risk_level,
        flags=all_flags,
        density_delta_description=desc,
        assessment=assessment_text or desc,
        data_sources=data_sources,
        confidence="low",
    )
