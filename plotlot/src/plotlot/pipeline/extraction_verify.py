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
_MIN_LOT_PATTERNS = (
    r"(?:minimum|min)\s+lot\s+(?:size|area)[^.]{0,80}?"
    r"(\d[\d,]*(?:\.\d+)?)\s*(?:square feet|sq\.?\s*ft|sqft)",
    r"lot\s+area\s+per\s+unit[^.]{0,80}?(\d[\d,]*(?:\.\d+)?)\s*(?:square feet|sq\.?\s*ft|sqft)",
)
_FAR_PATTERNS = (r"(?:floor area ratio|\bFAR\b)[^.]{0,40}?(\d+(?:\.\d+)?)",)

# Multifamily zone codes whose *single* trailing number denotes units/acre
# (RM-25, RD-1.5, MF18). Anchored to one number so multi-segment codes like
# San Diego's "RM-3-9" — where the digits are NOT density — never misfire.
_DENSITY_CODE_RE = re.compile(
    r"^\s*(RM|RD|RH|RMF|MF)\s*-?\s*(\d+(?:\.\d+)?)\s*$", re.IGNORECASE
)


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
) -> FieldVerification:
    """Cross-check one LLM value against the source text."""
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
    )
    min_lot = _verify_field(
        "min_lot_area_per_unit_sqft",
        "Min lot area per unit (sqft)",
        params.min_lot_area_per_unit_sqft,
        text,
        _MIN_LOT_PATTERNS,
        section,
    )
    far = _verify_field(
        "far",
        "Floor area ratio",
        params.far,
        text,
        _FAR_PATTERNS,
        section,
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

    result.fields = [density, min_lot, far]

    # A driver (density or min lot area) decides max units; if either is in
    # conflict or could not be corroborated, the offer is provisional.
    drivers = [density, min_lot]
    extracted_drivers = [f for f in drivers if f.llm_value is not None]

    if any(f.status == "conflict" for f in result.fields):
        result.overall = "conflict"
    elif extracted_drivers and all(f.status == "verified" for f in extracted_drivers):
        result.overall = "verified"
    elif any(f.status == "verified" for f in result.fields):
        result.overall = "partial"
    else:
        result.overall = "unverified"

    driver_ok = bool(extracted_drivers) and all(f.status == "verified" for f in extracted_drivers)
    result.offer_is_provisional = not driver_ok

    for f in result.fields:
        if f.status == "conflict":
            result.warnings.append(f"{f.label}: {f.note}")
    if result.offer_is_provisional and result.overall != "conflict":
        result.warnings.append(
            "Buildable-unit drivers are not fully corroborated by the ordinance text — "
            "treat the offer price as provisional until verified."
        )

    return result
