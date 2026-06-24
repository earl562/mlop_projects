from __future__ import annotations

from typing import TypedDict

from plotlot.core.lookup_snapshot import DisplayState, FreshnessStatus
from plotlot.pipeline.lookup_snapshot_eval import (
    ExpectedLookupField,
    LookupSnapshotEvalMetrics,
    LookupSnapshotEvalResult,
    LookupSnapshotFieldDiff,
    LookupSnapshotGoldenCase,
)
from plotlot.pipeline.lookup_snapshot_json import JsonScalar


class ExpectedLookupFieldJson(TypedDict):
    key: str
    value: JsonScalar
    display_state: str | None
    requires_evidence: bool
    freshness: str | None


class LookupSnapshotGoldenCaseJson(TypedDict):
    case_id: str
    jurisdiction: str
    expected_fields: list[ExpectedLookupFieldJson]
    expected_warnings: list[str]
    expected_quality_flags: list[str]
    required_calculations: list[str]


class LookupSnapshotEvalMetricsJson(TypedDict):
    field_value_accuracy: float
    display_state_accuracy: float
    citation_coverage: float
    warning_coverage: float
    ingestion_quality_flag_coverage: float
    deterministic_calculation_reproducibility: float
    unsupported_claim_rate: float
    required_field_count: int


class LookupSnapshotFieldDiffJson(TypedDict):
    field_key: str
    reason: str
    expected_value: JsonScalar
    observed_value: JsonScalar
    expected_display_state: str | None
    observed_display_state: str | None


class LookupSnapshotEvalDiffsJson(TypedDict):
    case_id: str
    lookup_snapshot_id: str
    field_diffs: list[LookupSnapshotFieldDiffJson]
    missing_warnings: list[str]
    missing_quality_flags: list[str]
    missing_calculations: list[str]


def golden_case_to_json(case: LookupSnapshotGoldenCase) -> LookupSnapshotGoldenCaseJson:
    return {
        "case_id": case.case_id,
        "jurisdiction": case.jurisdiction,
        "expected_fields": [_expected_field_to_json(field) for field in case.expected_fields],
        "expected_warnings": list(case.expected_warnings),
        "expected_quality_flags": list(case.expected_quality_flags),
        "required_calculations": list(case.required_calculations),
    }


def metrics_to_json(metrics: LookupSnapshotEvalMetrics) -> LookupSnapshotEvalMetricsJson:
    return {
        "field_value_accuracy": metrics.field_value_accuracy,
        "display_state_accuracy": metrics.display_state_accuracy,
        "citation_coverage": metrics.citation_coverage,
        "warning_coverage": metrics.warning_coverage,
        "ingestion_quality_flag_coverage": metrics.ingestion_quality_flag_coverage,
        "deterministic_calculation_reproducibility": (
            metrics.deterministic_calculation_reproducibility
        ),
        "unsupported_claim_rate": metrics.unsupported_claim_rate,
        "required_field_count": metrics.required_field_count,
    }


def diffs_to_json(result: LookupSnapshotEvalResult) -> LookupSnapshotEvalDiffsJson:
    return {
        "case_id": result.case.case_id,
        "lookup_snapshot_id": result.lookup_snapshot_id,
        "field_diffs": [_field_diff_to_json(diff) for diff in result.diffs],
        "missing_warnings": list(result.missing_warnings),
        "missing_quality_flags": list(result.missing_quality_flags),
        "missing_calculations": list(result.missing_calculations),
    }


def _expected_field_to_json(field: ExpectedLookupField) -> ExpectedLookupFieldJson:
    return {
        "key": field.key,
        "value": field.value,
        "display_state": _display_state_value(field.display_state),
        "requires_evidence": field.requires_evidence,
        "freshness": _freshness_value(field.freshness),
    }


def _field_diff_to_json(diff: LookupSnapshotFieldDiff) -> LookupSnapshotFieldDiffJson:
    return {
        "field_key": diff.field_key,
        "reason": diff.reason,
        "expected_value": diff.expected_value,
        "observed_value": diff.observed_value,
        "expected_display_state": diff.expected_display_state,
        "observed_display_state": diff.observed_display_state,
    }


def _display_state_value(display_state: DisplayState | None) -> str | None:
    if display_state is None:
        return None
    return display_state.value


def _freshness_value(freshness: FreshnessStatus | None) -> str | None:
    if freshness is None:
        return None
    return freshness.value
