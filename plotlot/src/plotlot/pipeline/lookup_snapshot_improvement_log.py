from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal, TypedDict

from plotlot.pipeline.lookup_snapshot_eval_batch import (
    LookupSnapshotEvalBatchMetrics,
    LookupSnapshotEvalBatchResult,
)

type ImprovementDirection = Literal["improved", "regressed", "flat"]

IMPROVEMENT_LOG_SOURCE: Final = "lookup_snapshot_eval_batch"
REGRESSION_RISK: Final = "baseline_regression_requires_review"
LOWER_IS_BETTER_METRICS: Final = frozenset({"unsupported_claim_rate"})
EPSILON: Final = 1e-12


class LookupSnapshotImprovementLogEntryJson(TypedDict):
    source: str
    researched_input: str
    changed_rule: str
    metric: str
    direction: ImprovementDirection
    reason: str
    affected_golden_cases: list[str]
    before_score: float
    after_score: float
    delta: float
    gate_blocking: bool
    unresolved_risk: str | None


@dataclass(frozen=True, slots=True)
class LookupSnapshotImprovementLogEntry:
    source: str
    researched_input: str
    changed_rule: str
    metric: str
    direction: ImprovementDirection
    reason: str
    affected_golden_cases: tuple[str, ...]
    before_score: float
    after_score: float
    delta: float
    gate_blocking: bool
    unresolved_risk: str | None


@dataclass(frozen=True, slots=True)
class _MetricMovement:
    metric: str
    current: float
    baseline: float
    delta: float


def improvement_log_from_batch_result(
    result: LookupSnapshotEvalBatchResult,
) -> tuple[LookupSnapshotImprovementLogEntry, ...]:
    if result.baseline is None or result.metric_deltas is None:
        return ()

    gate_metrics = frozenset(failure.metric for failure in result.gate_failures)
    affected_cases = tuple(case_result.case.case_id for case_result in result.case_results)
    return tuple(
        _log_entry(result.suite, affected_cases, gate_metrics, movement)
        for movement in _metric_movements(result.metrics, result.baseline)
    )


def improvement_log_entries_to_json(
    entries: tuple[LookupSnapshotImprovementLogEntry, ...],
) -> list[LookupSnapshotImprovementLogEntryJson]:
    return [
        {
            "source": entry.source,
            "researched_input": entry.researched_input,
            "changed_rule": entry.changed_rule,
            "metric": entry.metric,
            "direction": entry.direction,
            "reason": entry.reason,
            "affected_golden_cases": list(entry.affected_golden_cases),
            "before_score": entry.before_score,
            "after_score": entry.after_score,
            "delta": entry.delta,
            "gate_blocking": entry.gate_blocking,
            "unresolved_risk": entry.unresolved_risk,
        }
        for entry in entries
    ]


def _log_entry(
    suite: str,
    affected_cases: tuple[str, ...],
    gate_metrics: frozenset[str],
    movement: _MetricMovement,
) -> LookupSnapshotImprovementLogEntry:
    gate_blocking = movement.metric in gate_metrics
    return LookupSnapshotImprovementLogEntry(
        source=IMPROVEMENT_LOG_SOURCE,
        researched_input=suite,
        changed_rule=f"eval_metric:{movement.metric}",
        metric=movement.metric,
        direction=_direction(movement.metric, movement.delta),
        reason=_reason(movement.delta),
        affected_golden_cases=affected_cases,
        before_score=movement.baseline,
        after_score=movement.current,
        delta=movement.delta,
        gate_blocking=gate_blocking,
        unresolved_risk=REGRESSION_RISK if gate_blocking else None,
    )


def _metric_movements(
    current: LookupSnapshotEvalBatchMetrics,
    baseline: LookupSnapshotEvalBatchMetrics,
) -> tuple[_MetricMovement, ...]:
    return (
        _MetricMovement(
            "pass_rate",
            current.pass_rate,
            baseline.pass_rate,
            current.pass_rate - baseline.pass_rate,
        ),
        _MetricMovement(
            "field_value_accuracy",
            current.field_value_accuracy,
            baseline.field_value_accuracy,
            current.field_value_accuracy - baseline.field_value_accuracy,
        ),
        _MetricMovement(
            "display_state_accuracy",
            current.display_state_accuracy,
            baseline.display_state_accuracy,
            current.display_state_accuracy - baseline.display_state_accuracy,
        ),
        _MetricMovement(
            "citation_coverage",
            current.citation_coverage,
            baseline.citation_coverage,
            current.citation_coverage - baseline.citation_coverage,
        ),
        _MetricMovement(
            "warning_coverage",
            current.warning_coverage,
            baseline.warning_coverage,
            current.warning_coverage - baseline.warning_coverage,
        ),
        _MetricMovement(
            "ingestion_quality_flag_coverage",
            current.ingestion_quality_flag_coverage,
            baseline.ingestion_quality_flag_coverage,
            current.ingestion_quality_flag_coverage - baseline.ingestion_quality_flag_coverage,
        ),
        _MetricMovement(
            "deterministic_calculation_reproducibility",
            current.deterministic_calculation_reproducibility,
            baseline.deterministic_calculation_reproducibility,
            current.deterministic_calculation_reproducibility
            - baseline.deterministic_calculation_reproducibility,
        ),
        _MetricMovement(
            "unsupported_claim_rate",
            current.unsupported_claim_rate,
            baseline.unsupported_claim_rate,
            current.unsupported_claim_rate - baseline.unsupported_claim_rate,
        ),
    )


def _direction(metric: str, delta: float) -> ImprovementDirection:
    if abs(delta) <= EPSILON:
        return "flat"
    if metric in LOWER_IS_BETTER_METRICS:
        return "improved" if delta < 0 else "regressed"
    return "improved" if delta > 0 else "regressed"


def _reason(delta: float) -> str:
    if abs(delta) <= EPSILON:
        return "baseline_unchanged"
    return "baseline_delta"
