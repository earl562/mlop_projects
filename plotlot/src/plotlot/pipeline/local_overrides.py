"""LLM-proposed, deterministically-verified local density overrides.

The state-program engine (``density_bonus``) applies the California baseline.
Cities layer *local* programs on top (e.g. San Diego's Complete Communities /
Transit-Priority-Area ADU bonuses) that live only in ordinance text. This module
lets an LLM **propose** such local overrides — but every proposed number is gated
by a deterministic check before it is trusted:

  1. The LLM must return a **verbatim quote** from the retrieved ordinance text.
  2. The quote must be a real substring of that text (kills fabricated quotes).
  3. The proposed number must actually appear in the quote (kills misreads).
  4. The quote must contain the expected terms for the provision (kills
     wrong-field grabs).

Only overrides that pass all four are applied — additively, labeled ``source=
"local"``. Unverified proposals are surfaced but never change a number. Statutory
math, tiers, and citations remain deterministic constants elsewhere; the LLM here
only extracts *local parameters from text*. Any failure (no credentials, timeout,
bad JSON) degrades silently to the deterministic baseline.
"""

from __future__ import annotations

import json
import logging
import math
import re

from plotlot.core.types import DensityUplift, LocalOverride, UpliftProgram

logger = logging.getLogger(__name__)

# Minimum quote length to consider — guards against trivial/empty "citations".
_MIN_QUOTE_LEN = 20

# Expected terms per field — the cited quote must mention at least one.
_FIELD_KEYWORDS: dict[str, tuple[str, ...]] = {
    "local_adu_additional": ("accessory dwelling", "adu", "junior accessory"),
    "local_density_bonus_pct": ("density bonus", "bonus density", "incentive"),
}
_FIELD_LABELS: dict[str, str] = {
    "local_adu_additional": "Local ADU bonus",
    "local_density_bonus_pct": "Local density bonus",
}

_TOOL = {
    "type": "function",
    "function": {
        "name": "report_local_density_overrides",
        "description": (
            "Report ONLY local ordinance provisions that grant MORE residential units "
            "than California state law. Every value MUST be supported by a verbatim quote "
            "copied exactly from the provided ordinance text. If the text does not "
            "explicitly grant a local bonus, return null — never infer, estimate, or "
            "rely on outside knowledge."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "local_adu_additional": {
                    "type": ["integer", "null"],
                    "description": (
                        "Extra ADUs beyond the state default that THIS jurisdiction's code "
                        "explicitly allows (e.g. a transit-area ADU bonus). Null if not stated."
                    ),
                },
                "local_adu_quote": {
                    "type": "string",
                    "description": "Verbatim sentence from the provided text. Empty if null.",
                },
                "local_density_bonus_pct": {
                    "type": ["number", "null"],
                    "description": (
                        "A LOCAL density-bonus percentage that exceeds the state 50% maximum, "
                        "only if explicitly in the provided code. Null otherwise."
                    ),
                },
                "local_density_bonus_quote": {
                    "type": "string",
                    "description": "Verbatim sentence from the provided text. Empty if null.",
                },
            },
            "required": [
                "local_adu_additional",
                "local_adu_quote",
                "local_density_bonus_pct",
                "local_density_bonus_quote",
            ],
        },
    },
}


# ---------------------------------------------------------------------------
# Deterministic verification (the safety mechanism — no LLM, fully testable)
# ---------------------------------------------------------------------------


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def _number_in_quote(value: float, quote: str) -> bool:
    """True if the proposed value appears as a number in the quote."""
    nums = re.findall(r"\d+(?:\.\d+)?", quote.replace(",", ""))
    for n in nums:
        try:
            if abs(float(n) - float(value)) < 1e-6:
                return True
        except ValueError:
            continue
    return False


def verify_local_overrides(
    proposed: list[dict],
    search_results: list | None,
    section: str = "",
) -> list[LocalOverride]:
    """Validate LLM-proposed overrides against the retrieved ordinance text."""
    source_text = _normalize(
        " ".join(getattr(r, "chunk_text", "") or "" for r in (search_results or []))
    )
    results: list[LocalOverride] = []
    for p in proposed:
        field = str(p.get("field", ""))
        value = p.get("value")
        quote = str(p.get("quote") or "").strip()
        if field not in _FIELD_KEYWORDS or value is None:
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if value <= 0:
            continue

        ov = LocalOverride(
            field=field,
            label=_FIELD_LABELS.get(field, field),
            value=value,
            quote=quote,
            section=section,
        )
        nq = _normalize(quote)
        if len(nq) < _MIN_QUOTE_LEN or nq not in source_text:
            ov.note = "Cited quote was not found verbatim in the ordinance text — ignored."
        elif not _number_in_quote(value, quote):
            ov.note = "The value does not appear in the cited quote — ignored."
        elif not any(kw in nq for kw in _FIELD_KEYWORDS[field]):
            ov.note = "Quote lacks the expected terms for this provision — ignored."
        else:
            ov.status = "verified"
            ov.note = "Corroborated by a cited ordinance sentence."
        results.append(ov)
    return results


def apply_local_overrides(uplift: DensityUplift, overrides: list[LocalOverride]) -> None:
    """Fold verified overrides into the uplift as labeled local programs."""
    uplift.local_overrides = overrides
    base = uplift.base_units

    for ov in overrides:
        if ov.status != "verified":
            uplift.notes.append(
                f"Local override claimed ({ov.label}: {ov.value:g}) but not verified — ignored."
            )
            continue

        if ov.field == "local_adu_additional":
            additional = int(ov.value)
            potential = base + additional
        elif ov.field == "local_density_bonus_pct":
            additional = math.floor(base * ov.value / 100.0)
            potential = base + additional
        else:
            continue

        uplift.programs.append(
            UpliftProgram(
                name=ov.label,
                statute="Local ordinance (verified)",
                source="local",
                eligibility="eligible",
                additional_units=additional,
                potential_units=potential,
                basis=ov.quote[:160],
                requirements="Local provision — confirm current code with the municipality.",
            )
        )

    eligible = [p for p in uplift.programs if p.eligibility == "eligible"]
    uplift.max_potential_units = max((p.potential_units for p in eligible), default=base)


# ---------------------------------------------------------------------------
# LLM proposer (constrained; degrades to [] on any failure)
# ---------------------------------------------------------------------------


def _combine_text(search_results: list | None, limit: int = 6000) -> str:
    parts = [getattr(r, "chunk_text", "") or "" for r in (search_results or [])]
    return " ".join(p for p in parts if p)[:limit]


async def propose_local_overrides(
    municipality: str,
    zone_code: str,
    search_results: list | None,
) -> list[dict]:
    """Ask the LLM to propose local overrides. Returns [] on any failure."""
    text = _combine_text(search_results)
    if not text:
        return []

    from plotlot.retrieval.llm import call_llm

    system = (
        "You extract LOCAL zoning provisions that grant more residential units than "
        "California state law. Use ONLY the provided ordinance text. Copy quotes verbatim. "
        "If a local bonus is not explicitly stated, return null. Never infer or estimate."
    )
    user = (
        f"Municipality: {municipality}\nZone: {zone_code}\n\n"
        f"Ordinance text:\n{text}\n\n"
        "Call report_local_density_overrides with only what the text explicitly states."
    )
    try:
        response = await call_llm(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            tools=[_TOOL],
        )
    except Exception as exc:  # noqa: BLE001 — best-effort; never break the pipeline
        logger.warning("Local-override LLM call failed: %s", exc)
        return []

    if not response or not response.get("tool_calls"):
        return []
    try:
        args = json.loads(response["tool_calls"][0]["function"]["arguments"])
    except (KeyError, IndexError, json.JSONDecodeError, TypeError):
        return []

    proposed: list[dict] = []
    if args.get("local_adu_additional"):
        proposed.append(
            {
                "field": "local_adu_additional",
                "value": args.get("local_adu_additional"),
                "quote": args.get("local_adu_quote", ""),
            }
        )
    if args.get("local_density_bonus_pct"):
        proposed.append(
            {
                "field": "local_density_bonus_pct",
                "value": args.get("local_density_bonus_pct"),
                "quote": args.get("local_density_bonus_quote", ""),
            }
        )
    return proposed


async def get_local_overrides(
    uplift: DensityUplift,
    municipality: str,
    zone_code: str,
    search_results: list | None,
    section: str = "",
) -> None:
    """Propose → verify → apply local overrides onto an existing uplift.

    Best-effort: any failure leaves the deterministic uplift untouched.
    """
    try:
        proposed = await propose_local_overrides(municipality, zone_code, search_results)
        if not proposed:
            return
        verified = verify_local_overrides(proposed, search_results, section)
        apply_local_overrides(uplift, verified)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Local-override processing failed (non-blocking): %s", exc)
