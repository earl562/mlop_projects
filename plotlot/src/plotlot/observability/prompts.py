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

## NUMERIC EXTRACTION — TOP PRIORITY

The submit_report tool has BOTH text description fields AND numeric fields. You MUST fill BOTH \
for every dimensional standard you find. The numeric fields power the density calculator — \
the core product feature. Without them, the user gets no max-units calculation.

**Text fields** (human-readable — describe each standard):
- setbacks_front, setbacks_side, setbacks_rear → e.g. "25 feet"
- max_height → e.g. "35 feet / 2 stories"
- max_density → e.g. "6 dwelling units per acre"
- floor_area_ratio → e.g. "0.50"
- lot_coverage → e.g. "40%"
- min_lot_size → e.g. "7,500 sq ft per dwelling unit"
- parking_requirements → e.g. "2 spaces per unit"

**Numeric fields** (REQUIRED for calculator — extract the raw number):
- max_density_units_per_acre → 6.0
- min_lot_area_per_unit_sqft → 7500
- far_numeric → 0.50
- max_lot_coverage_pct → 40.0
- max_height_ft → 35.0
- max_stories → 2
- setback_front_ft → 25.0
- setback_side_ft → 7.5
- setback_rear_ft → 25.0
- min_unit_size_sqft → 750
- min_lot_width_ft → 75.0
- parking_spaces_per_unit → 2.0

For EVERY number you mention in a text field, set the corresponding numeric field too. \
Example: if you set setbacks_front="25 feet", you MUST also set setback_front_ft=25.0.

If the ordinance doesn't state a value explicitly but you know the typical standard for \
this district type in South Florida, use that value and set confidence to "medium".\
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
