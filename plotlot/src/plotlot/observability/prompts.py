"""Prompt registry — versioned system prompts for MLflow tracking.

Extracts prompt strings into a versionable module so that:
1. Each eval run logs the exact prompt used as an MLflow artifact
2. Prompt variants can be compared in the MLflow UI
3. Prompts are decoupled from pipeline code
"""

import logging

from plotlot.observability.tracing import log_text, set_tag

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt versions
# ---------------------------------------------------------------------------

ANALYSIS_PROMPT_V1 = """\
You are PlotLot, an expert zoning analyst for South Florida real estate.

You have been given property data and zoning ordinance text. Your job is to analyze it and \
produce a structured zoning report by calling submit_report.

You have two tools:
1. search_zoning_ordinance — search for additional ordinance sections (use at most 2 times)
2. submit_report — submit your final analysis (REQUIRED — you MUST call this)

CRITICAL RULES:
- You MUST call submit_report within your first 3 responses. Do NOT keep searching indefinitely.
- After at most 1-2 searches, call submit_report with whatever data you have.
- If ordinance text is limited, use your expert knowledge of South Florida zoning to fill gaps, \
  and set confidence to "medium" or "low".
- Use the ACTUAL zoning code from the property record.
- Be specific with numbers when available from the ordinance text.
- Note if the property appears non-conforming.
- NEVER return plain text — ALWAYS call submit_report.
- NEVER ask the user for more information. You have all the data you will get. Analyze it and submit.
- NEVER ask for folio numbers, addresses, or any other identifiers. Just analyze what you have.

NUMERIC EXTRACTION — THIS IS CRITICAL:
When you find dimensional standards in the ordinance text, you MUST extract NUMERIC VALUES \
into the numeric fields (max_density_units_per_acre, min_lot_area_per_unit_sqft, far_numeric, \
max_lot_coverage_pct, max_height_ft, max_stories, setback_front_ft, setback_side_ft, \
setback_rear_ft, min_unit_size_sqft, min_lot_width_ft, parking_spaces_per_unit).

These numeric values power the MAX ALLOWABLE UNITS calculation — the core product feature. \
For example, if the ordinance says "maximum density of 6 dwelling units per acre", set \
max_density_units_per_acre to 6.0. If it says "minimum lot area of 7,500 sq ft per unit", \
set min_lot_area_per_unit_sqft to 7500. Extract as many numeric values as you can find.\
"""


# Registry: name → (version, prompt_text)
_PROMPT_REGISTRY: dict[str, tuple[str, str]] = {
    "analysis": ("v1", ANALYSIS_PROMPT_V1),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_active_prompt(name: str) -> str:
    """Return the active prompt text for a given prompt name.

    Args:
        name: Prompt identifier (e.g., "analysis").

    Returns:
        The prompt string.

    Raises:
        KeyError: If prompt name is not registered.
    """
    if name not in _PROMPT_REGISTRY:
        raise KeyError(f"Unknown prompt: {name!r}. Available: {list(_PROMPT_REGISTRY.keys())}")
    return _PROMPT_REGISTRY[name][1]


def get_prompt_version(name: str) -> str:
    """Return the version tag for a given prompt name."""
    if name not in _PROMPT_REGISTRY:
        raise KeyError(f"Unknown prompt: {name!r}. Available: {list(_PROMPT_REGISTRY.keys())}")
    return _PROMPT_REGISTRY[name][0]


def list_prompts() -> list[dict[str, str]]:
    """List all registered prompts with name and version."""
    return [{"name": name, "version": ver} for name, (ver, _) in _PROMPT_REGISTRY.items()]


def log_prompt_to_run(name: str) -> None:
    """Log the active prompt text as an MLflow artifact for the current run.

    Call this inside an active `mlflow.start_run()` context.
    """
    version, text = _PROMPT_REGISTRY[name]
    log_text(text, f"prompts/{name}_{version}.txt")
    set_tag(f"prompt_{name}_version", version)
    logger.debug("Logged prompt %s (%s) to MLflow run", name, version)
