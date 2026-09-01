"""PlotLot evaluation corpora and benchmark helpers."""

from plotlot.evaluation.leads import (
    LeadEvaluationCase,
    LeadFixtureManifest,
    LeadPrivacyError,
    assert_fixture_is_sanitized,
    load_lead_fixture,
    sanitize_lead_row,
    stable_case_id,
)

__all__ = [
    "LeadEvaluationCase",
    "LeadFixtureManifest",
    "LeadPrivacyError",
    "assert_fixture_is_sanitized",
    "load_lead_fixture",
    "sanitize_lead_row",
    "stable_case_id",
]
