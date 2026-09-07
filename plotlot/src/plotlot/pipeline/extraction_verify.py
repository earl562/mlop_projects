"""Deterministic verification of LLM-extracted zoning numbers.

The LLM extracts the value-drivers that decide max buildable units — density,
minimum lot area per unit, and FAR. A wrong number here (the San Diego incident)
silently propagates into a confident offer price. This module corroborates each
value against two independent, deterministic sources:

  1. A regex read of the *same* retrieved ordinance text (source grounding).
  2. The zoning code's self-described density (e.g. RM-25 → 25 du/ac).

Each value is marked ``verified`` (corroborated), ``conflict`` (the source says
something else), or ``unverified`` (no corroboration found). A driver that is
not verified makes the offer *provisional* — never silently shown as firm.

Pure functions, no I/O — fully unit-testable.
"""

from __future__ import annotations

import re

from plotlot.core.types import (
    ExtractionVerification,
    FieldVerification,
    NumericZoningParams,
)

SQFT_PER_ACRE = 43_560

# Relative tolerance for treating two numbers as the same value.
_REL_TOL = 0.02
# Zone-code density prior is a soft check: flag only when the LLM value deviates
# from the code's self-described density by more than this fraction.
_ZONE_PRIOR_TOL = 0.40

# Regex grounding patterns per field (value captured in group 1).
_DENSITY_PATTERNS = (
    r"(?:maximum|max)\s+density[^.]{0,80}?(\d+(?:\.\d+)?)\s*"
    r"(?:dwelling\s+units|units|du)\s*(?:per acre|/acre|du/ac)",
    r"(\d+(?:\.\d+)?)\s*(?:dwelling\s+units|units|du)\s*(?:per acre|/acre|du/ac)",
)
# Lot area per dwelling unit. Includes San Diego's table phrasing —
# "1 dwelling unit per 1,000 square feet of lot area" / "1,000 sf of lot area
# per dwelling unit" — which earlier patterns missed (left density unverified).
_SQFT = r"(?:square\s*feet|sq\.?\s*ft|sqft|sf)"
_MIN_LOT_PATTERNS = (
    r"(?:minimum|min)\s+lot\s+(?:size|area)[^.]{0,80}?(\d[\d,]*(?:\.\d+)?)\s*" + _SQFT,
    r"lot\s+area\s+per\s+(?:dwelling\s+)?unit[^.]{0,80}?(\d[\d,]*(?:\.\d+)?)\s*" + _SQFT,
    r"(?:1|one)\s+(?:dwelling\s+)?units?[^.\d;:]{0,25}?(?:per|for\s+each|/)\s+"
    r"(\d[\d,]*(?:\.\d+)?)\s*" + _SQFT,
    r"(\d[\d,]*(?:\.\d+)?)\s*"
    + _SQFT
    + r"\s*(?:of\s+lot\s+area\s*)?(?:per|/)\s*(?:dwelling\s+)?unit",
)
_FAR_PATTERNS = (r"(?:floor area ratio|\bFAR\b)[^.]{0,40}?(\d+(?:\.\d+)?)",)

# Multifamily zone codes whose *single* trailing number denotes units/acre
# (RM-25, RD-1.5, MF18). Anchored to one number so multi-segment codes like
# San Diego's "RM-3-9" — where the digits are NOT density — never misfire.
_DENSITY_CODE_RE = re.compile(r"^\s*(RM|RD|RH|RMF|MF)\s*-?\s*(\d+(?:\.\d+)?)\s*$", re.IGNORECASE)


def _close(a: float, b: float) -> bool:
    """True if a and b are equal within relative tolerance."""
    return abs(a - b) <= max(1e-9, _REL_TOL * max(abs(a), abs(b)))


def _combine_text(search_results: list | None) -> tuple[str, str]:
    """Join retrieved chunk text and return (normalized_text, top_section)."""
    if not search_results:
        return "", ""
    parts = [getattr(r, "chunk_text", "") or "" for r in search_results]
    text = re.sub(r"\s+", " ", " ".join(p for p in parts if p))
    section = ""
    for r in search_results:
        if getattr(r, "section", ""):
            section = r.section
            break
    return text, section


def _ground(text: str, patterns: tuple[str, ...]) -> tuple[float | None, str]:
    """Find a value + its surrounding sentence snippet in the source text."""
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if not m:
            continue
        try:
            value = float(m.group(1).replace(",", ""))
        except (ValueError, TypeError):
            continue
        start = max(0, m.start() - 60)
        end = min(len(text), m.end() + 60)
        snippet = text[start:end].strip()
        if start > 0:
            snippet = "…" + snippet
        if end < len(text):
            snippet = snippet + "…"
        return value, snippet
    return None, ""


# Start of a segmented zone code (RM-3-7, CC-3-6, RS-1-1, OTRM-2-4). Used to
# split a multi-zone density table so each zone's value can be read in isolation.
_ZONE_TOKEN_RE = re.compile(r"\b[A-Z]{1,5}-\d{1,2}(?:-\d{1,2})?\b")


def _ground_for_zone(
    text: str, patterns: tuple[str, ...], zone_code: str
) -> tuple[float | None, str]:
    """Ground a value anchored to a specific zone code within the text.

    San Diego lists every RM/CC zone's density in ONE chunk — e.g. "…RM-3-7
    permits a maximum density of 1 dwelling unit for each 1,000 square feet of
    lot area; RM-3-8 … 800 …". A plain first-match grab (``_ground``) returns a
    *different* zone's number (RM-1-2's 2,500), so the LLM's correct 1,000 looks
    like a conflict and the offer is wrongly marked provisional.

    This scans only the clause introduced by the target zone code, bounded by the
    next zone code, so RM-3-7 grounds to 1,000 — not its neighbor. Returns
    ``(None, "")`` when the zone code isn't present, so the caller falls back to
    the global first-match behavior (single-zone chunks are unaffected).
    """
    if not zone_code.strip():
        return None, ""
    for m in re.finditer(re.escape(zone_code.strip()), text, re.IGNORECASE):
        nxt = _ZONE_TOKEN_RE.search(text, m.end())
        end = min(nxt.start(), m.end() + 200) if nxt else m.end() + 200
        value, snippet = _ground(text[m.start() : end], patterns)
        if value is not None:
            return value, snippet
    return None, ""


def _zone_expected_density(zone_code: str) -> float | None:
    """Density implied by a self-describing multifamily zone code (RM-25 → 25)."""
    if not zone_code:
        return None
    m = _DENSITY_CODE_RE.match(zone_code)
    if not m:
        return None
    try:
        return float(m.group(2))
    except (ValueError, TypeError):
        return None


def _verify_field(
    field: str,
    label: str,
    llm_value: float | None,
    text: str,
    patterns: tuple[str, ...],
    section: str,
    zone_code: str = "",
) -> FieldVerification:
    """Cross-check one LLM value against the source text.

    Grounding is zone-aware: when the chunk lists many zones, prefer the value in
    the target zone's own clause, falling back to a global first match so single-
    zone chunks behave exactly as before.
    """
    source_value, snippet = _ground_for_zone(text, patterns, zone_code)
    if source_value is None:
        source_value, snippet = _ground(text, patterns)
    fv = FieldVerification(
        field=field,
        label=label,
        llm_value=llm_value,
        source_value=source_value,
        citation=snippet,
        section=section if snippet else "",
    )
    if llm_value is None:
        if source_value is not None:
            fv.status = "conflict"
            fv.note = f"Source states {source_value:g} but it was not extracted."
        else:
            fv.status = "unverified"
            fv.note = "Not extracted; no value found in source text."
        return fv

    if source_value is None:
        fv.status = "unverified"
        fv.note = "No corroborating value found in the retrieved ordinance text."
        return fv

    if _close(llm_value, source_value):
        fv.status = "verified"
        fv.note = "Corroborated by source text."
    else:
        fv.status = "conflict"
        fv.note = f"Extracted {llm_value:g}, but source text states {source_value:g}."
    return fv


def is_field_verified(verification: ExtractionVerification | None, field: str) -> bool:
    """True if a named field was source-verified in the verification result."""
    if verification is None:
        return False
    return any(f.field == field and f.status == "verified" for f in verification.fields)


def verify_numeric_params(
    params: NumericZoningParams | None,
    search_results: list | None,
    zone_code: str = "",
) -> ExtractionVerification:
    """Verify the max-units value-drivers against the source text + zone code.

    Args:
        params: LLM-extracted NumericZoningParams.
        search_results: The retrieved ordinance chunks (each has ``chunk_text``).
        zone_code: Zoning district code (for the self-described-density prior).

    Returns:
        ExtractionVerification with per-field status, citations, and warnings.
        ``offer_is_provisional`` is True when a max-units driver is unverified
        or in conflict.
    """
    result = ExtractionVerification()
    if params is None:
        result.warnings.append("No zoning parameters were extracted — cannot verify.")
        return result

    text, section = _combine_text(search_results)

    density = _verify_field(
        "max_density_units_per_acre",
        "Max density (units/acre)",
        params.max_density_units_per_acre,
        text,
        _DENSITY_PATTERNS,
        section,
        zone_code,
    )
    min_lot = _verify_field(
        "min_lot_area_per_unit_sqft",
        "Min lot area per unit (sqft)",
        params.min_lot_area_per_unit_sqft,
        text,
        _MIN_LOT_PATTERNS,
        section,
        zone_code,
    )
    far = _verify_field(
        "far",
        "Floor area ratio",
        params.far,
        text,
        _FAR_PATTERNS,
        section,
        zone_code,
    )

    # Zone-code self-described density prior (soft, density only).
    expected = _zone_expected_density(zone_code)
    if expected is not None and params.max_density_units_per_acre is not None:
        lo, hi = expected * (1 - _ZONE_PRIOR_TOL), expected * (1 + _ZONE_PRIOR_TOL)
        if not (lo <= params.max_density_units_per_acre <= hi):
            result.warnings.append(
                f"Extracted density {params.max_density_units_per_acre:g} u/ac disagrees with "
                f"zone code {zone_code} (implies ~{expected:g} u/ac) — verify."
            )
            if density.status == "verified":
                density.status = "conflict"
                density.note += f" Also conflicts with zone code {zone_code} (~{expected:g} u/ac)."

    # Cross-check the two density encodings. If the source grounded a
    # min-lot-area but the LLM's units/acre disagrees with what it implies, the
    # units/acre value is the artifact — flag it so it can't masquerade as data.
    if min_lot.source_value and density.llm_value and density.source_value is None:
        implied = SQFT_PER_ACRE / min_lot.source_value
        hi, lo = max(implied, density.llm_value), min(implied, density.llm_value)
        if hi > 0 and (hi - lo) / hi > 0.25:
            density.status = "conflict"
            density.note = (
                f"Extracted {density.llm_value:g} u/ac contradicts source min lot area "
                f"{min_lot.source_value:,.0f} sqft/unit (≈ {implied:.1f} u/ac)."
            )

    result.fields = [density, min_lot, far]

    # Density and min-lot-area are two encodings of the SAME limit; the limit is
    # corroborated if EITHER encoding is source-verified. That governing limit —
    # not a redundant or non-governing field — decides whether the offer is firm.
    density_limit_extracted = density.llm_value is not None or min_lot.llm_value is not None
    density_limit_verified = density.status == "verified" or min_lot.status == "verified"
    result.offer_is_provisional = not (density_limit_extracted and density_limit_verified)

    has_conflict = any(f.status == "conflict" for f in result.fields)
    if not density_limit_extracted:
        result.overall = "unverified"
    elif density_limit_verified:
        result.overall = "partial" if has_conflict else "verified"
    else:
        result.overall = "conflict" if has_conflict else "unverified"

    for f in result.fields:
        if f.status == "conflict":
            result.warnings.append(f"{f.label}: {f.note}")
    if result.offer_is_provisional:
        result.warnings.append(
            "Buildable-unit density limit is not source-verified — "
            "treat the offer price as provisional until confirmed."
        )

    return result
