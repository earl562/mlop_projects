from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from plotlot.core.lookup_snapshot import (
    DisplayState,
    FieldScalar,
    FreshnessStatus,
    LookupField,
    LookupSnapshot,
)
from plotlot.pipeline.lookup_snapshot_json import JsonScalar

LOOKUP_CORRECTNESS_SUITE: Final = "lookup_correctness"
type EvalStatus = Literal["passed", "failed"]


class ExpectedLookupField(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str = Field(min_length=1)
    value: JsonScalar = None
    display_state: DisplayState | None = None
    requires_evidence: bool = True
    freshness: FreshnessStatus | None = None


class LookupSnapshotGoldenCase(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_id: str = Field(min_length=1)
    jurisdiction: str = Field(min_length=1)
    expected_fields: tuple[ExpectedLookupField, ...] = Field(min_length=1)
    expected_warnings: tuple[str, ...] = ()
    expected_quality_flags: tuple[str, ...] = ()
    required_calculations: tuple[str, ...] = ()
    source_urls: tuple[str, ...] = ()
    tags: tuple[str, ...] = (LOOKUP_CORRECTNESS_SUITE,)


@dataclass(frozen=True, slots=True)
class LookupSnapshotEvalMetrics:
    field_value_accuracy: float
    display_state_accuracy: float
    citation_coverage: float
    warning_coverage: float
    deterministic_calculation_reproducibility: float
    unsupported_claim_rate: float
    required_field_count: int
    ingestion_quality_flag_coverage: float = 1.0


@dataclass(frozen=True, slots=True)
class LookupSnapshotFieldDiff:
    field_key: str
    reason: str
    expected_value: JsonScalar
    observed_value: JsonScalar
    expected_display_state: str | None
    observed_display_state: str | None


@dataclass(frozen=True, slots=True)
class LookupSnapshotEvalResult:
    lookup_snapshot_id: str
    case: LookupSnapshotGoldenCase
    status: EvalStatus
    metrics: LookupSnapshotEvalMetrics
    diffs: tuple[LookupSnapshotFieldDiff, ...]
    missing_warnings: tuple[str, ...]
    missing_calculations: tuple[str, ...]
    missing_quality_flags: tuple[str, ...] = ()


def score_lookup_snapshot(
    snapshot: LookupSnapshot,
    case: LookupSnapshotGoldenCase,
) -> LookupSnapshotEvalResult:
    fields_by_key = {str(field.key): field for field in snapshot.fields}
    diffs: list[LookupSnapshotFieldDiff] = []
    value_matches = 0
    display_matches = 0
    evidence_matches = 0

    for expected in case.expected_fields:
        field = fields_by_key.get(expected.key)
        if field is None:
            diffs.append(_missing_field_diff(expected))
            continue
        if _field_has_required_evidence(field, expected):
            evidence_matches += 1
        else:
            diffs.append(_field_diff(field, expected, "missing_required_evidence"))
        if field.value == expected.value:
            value_matches += 1
        else:
            diffs.append(_field_diff(field, expected, "value_mismatch"))
        if expected.display_state is None or field.display_state == expected.display_state:
            display_matches += 1
        else:
            diffs.append(_field_diff(field, expected, "display_state_mismatch"))
        if expected.freshness is not None and field.freshness != expected.freshness:
            diffs.append(_field_diff(field, expected, "freshness_mismatch"))

    missing_warnings = _missing_warnings(snapshot, case)
    missing_quality_flags = _missing_quality_flags(snapshot, case)
    missing_calculations = _missing_calculations(snapshot, case)
    metrics = LookupSnapshotEvalMetrics(
        field_value_accuracy=_ratio(value_matches, len(case.expected_fields)),
        display_state_accuracy=_ratio(display_matches, len(case.expected_fields)),
        citation_coverage=_ratio(evidence_matches, _required_evidence_count(case)),
        warning_coverage=_ratio(
            len(case.expected_warnings) - len(missing_warnings),
            len(case.expected_warnings),
        ),
        ingestion_quality_flag_coverage=_ratio(
            len(case.expected_quality_flags) - len(missing_quality_flags),
            len(case.expected_quality_flags),
        ),
        deterministic_calculation_reproducibility=_calculation_reproducibility(snapshot),
        unsupported_claim_rate=_unsupported_claim_rate(snapshot),
        required_field_count=len(case.expected_fields),
    )
    status = _eval_status(
        metrics,
        diffs,
        missing_warnings,
        missing_quality_flags,
        missing_calculations,
    )
    return LookupSnapshotEvalResult(
        lookup_snapshot_id=str(snapshot.lookup_snapshot_id),
        case=case,
        status=status,
        metrics=metrics,
        diffs=tuple(diffs),
        missing_warnings=missing_warnings,
        missing_quality_flags=missing_quality_flags,
        missing_calculations=missing_calculations,
    )


def _field_has_required_evidence(
    field: LookupField,
    expected: ExpectedLookupField,
) -> bool:
    return not expected.requires_evidence or bool(field.evidence_ids)


def _field_diff(
    field: LookupField,
    expected: ExpectedLookupField,
    reason: str,
) -> LookupSnapshotFieldDiff:
    return LookupSnapshotFieldDiff(
        field_key=expected.key,
        reason=reason,
        expected_value=expected.value,
        observed_value=field.value,
        expected_display_state=_display_state_value(expected.display_state),
        observed_display_state=field.display_state.value,
    )


def _missing_field_diff(expected: ExpectedLookupField) -> LookupSnapshotFieldDiff:
    return LookupSnapshotFieldDiff(
        field_key=expected.key,
        reason="missing_field",
        expected_value=expected.value,
        observed_value=None,
        expected_display_state=_display_state_value(expected.display_state),
        observed_display_state=None,
    )


def _missing_warnings(
    snapshot: LookupSnapshot,
    case: LookupSnapshotGoldenCase,
) -> tuple[str, ...]:
    actual = set(snapshot.warnings)
    return tuple(warning for warning in case.expected_warnings if warning not in actual)


def _missing_quality_flags(
    snapshot: LookupSnapshot,
    case: LookupSnapshotGoldenCase,
) -> tuple[str, ...]:
    actual = _quality_flags(snapshot)
    return tuple(flag for flag in case.expected_quality_flags if flag not in actual)


def _quality_flags(snapshot: LookupSnapshot) -> set[str]:
    flags = set(snapshot.warnings)
    for field in snapshot.fields:
        flags.update(field.warnings)
    return flags


def _missing_calculations(
    snapshot: LookupSnapshot,
    case: LookupSnapshotGoldenCase,
) -> tuple[str, ...]:
    actual = {calculation.calculator_name for calculation in snapshot.calculations}
    return tuple(name for name in case.required_calculations if name not in actual)


def _calculation_reproducibility(snapshot: LookupSnapshot) -> float:
    return _ratio(
        sum(1 for calculation in snapshot.calculations if calculation.is_reproducible),
        len(snapshot.calculations),
    )


def _unsupported_claim_rate(snapshot: LookupSnapshot) -> float:
    claim_fields = tuple(field for field in snapshot.fields if _has_claim_value(field.value))
    unsupported = sum(
        1
        for field in claim_fields
        if field.display_state is DisplayState.VERIFIED and not field.evidence_ids
    )
    return _ratio(unsupported, len(claim_fields))


def _eval_status(
    metrics: LookupSnapshotEvalMetrics,
    diffs: list[LookupSnapshotFieldDiff],
    missing_warnings: tuple[str, ...],
    missing_quality_flags: tuple[str, ...],
    missing_calculations: tuple[str, ...],
) -> EvalStatus:
    if diffs or missing_warnings or missing_quality_flags or missing_calculations:
        return "failed"
    if metrics.unsupported_claim_rate > 0:
        return "failed"
    if metrics.deterministic_calculation_reproducibility < 1:
        return "failed"
    return "passed"


def _required_evidence_count(case: LookupSnapshotGoldenCase) -> int:
    return sum(1 for field in case.expected_fields if field.requires_evidence)


def _has_claim_value(value: FieldScalar) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 1.0
    return numerator / denominator


def _display_state_value(display_state: DisplayState | None) -> str | None:
    if display_state is None:
        return None
    return display_state.value
