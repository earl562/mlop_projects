from __future__ import annotations

from dataclasses import dataclass

from plotlot.core.lookup_snapshot import LookupSnapshot
from plotlot.pipeline.lookup_snapshot_eval import (
    EvalStatus,
    LookupSnapshotEvalResult,
    LookupSnapshotGoldenCase,
    score_lookup_snapshot,
)


@dataclass(frozen=True, slots=True)
class LookupSnapshotEvalBatchCase:
    snapshot: LookupSnapshot
    case: LookupSnapshotGoldenCase


@dataclass(frozen=True, slots=True)
class LookupSnapshotEvalBatchMetrics:
    pass_rate: float
    case_count: int
    passed_count: int
    failed_count: int
    field_value_accuracy: float
    display_state_accuracy: float
    citation_coverage: float
    warning_coverage: float
    deterministic_calculation_reproducibility: float
    unsupported_claim_rate: float
    ingestion_quality_flag_coverage: float = 1.0


@dataclass(frozen=True, slots=True)
class LookupSnapshotEvalBatchMetricDeltas:
    pass_rate: float
    field_value_accuracy: float
    display_state_accuracy: float
    citation_coverage: float
    warning_coverage: float
    deterministic_calculation_reproducibility: float
    unsupported_claim_rate: float
    ingestion_quality_flag_coverage: float = 0.0


@dataclass(frozen=True, slots=True)
class LookupSnapshotEvalBatchGateFailure:
    metric: str
    reason: str
    current: float
    baseline: float


@dataclass(frozen=True, slots=True)
class LookupSnapshotEvalBatch:
    suite: str
    cases: tuple[LookupSnapshotEvalBatchCase, ...]
    baseline: LookupSnapshotEvalBatchMetrics | None = None


@dataclass(frozen=True, slots=True)
class LookupSnapshotEvalBatchResult:
    suite: str
    status: EvalStatus
    metrics: LookupSnapshotEvalBatchMetrics
    metric_deltas: LookupSnapshotEvalBatchMetricDeltas | None
    gate_failures: tuple[LookupSnapshotEvalBatchGateFailure, ...]
    baseline: LookupSnapshotEvalBatchMetrics | None
    case_results: tuple[LookupSnapshotEvalResult, ...]


class EmptyLookupSnapshotEvalBatchError(ValueError):
    def __init__(self, suite: str) -> None:
        super().__init__(f"lookup snapshot eval batch {suite!r} has no cases")


def run_lookup_snapshot_eval_batch(
    batch: LookupSnapshotEvalBatch,
) -> LookupSnapshotEvalBatchResult:
    if not batch.cases:
        raise EmptyLookupSnapshotEvalBatchError(batch.suite)

    case_results = tuple(
        score_lookup_snapshot(batch_case.snapshot, batch_case.case) for batch_case in batch.cases
    )
    metrics = _batch_metrics(case_results)
    metric_deltas = _metric_deltas(metrics, batch.baseline)
    gate_failures = _gate_failures(metrics, batch.baseline)
    status = _batch_status(case_results, gate_failures)
    return LookupSnapshotEvalBatchResult(
        suite=batch.suite,
        status=status,
        metrics=metrics,
        metric_deltas=metric_deltas,
        gate_failures=gate_failures,
        baseline=batch.baseline,
        case_results=case_results,
    )


def _batch_metrics(
    case_results: tuple[LookupSnapshotEvalResult, ...],
) -> LookupSnapshotEvalBatchMetrics:
    passed_count = sum(1 for result in case_results if result.status == "passed")
    failed_count = len(case_results) - passed_count
    return LookupSnapshotEvalBatchMetrics(
        pass_rate=passed_count / len(case_results),
        case_count=len(case_results),
        passed_count=passed_count,
        failed_count=failed_count,
        field_value_accuracy=_mean(
            tuple(result.metrics.field_value_accuracy for result in case_results)
        ),
        display_state_accuracy=_mean(
            tuple(result.metrics.display_state_accuracy for result in case_results)
        ),
        citation_coverage=_mean(tuple(result.metrics.citation_coverage for result in case_results)),
        warning_coverage=_mean(tuple(result.metrics.warning_coverage for result in case_results)),
        ingestion_quality_flag_coverage=_mean(
            tuple(result.metrics.ingestion_quality_flag_coverage for result in case_results)
        ),
        deterministic_calculation_reproducibility=_mean(
            tuple(
                result.metrics.deterministic_calculation_reproducibility for result in case_results
            )
        ),
        unsupported_claim_rate=_mean(
            tuple(result.metrics.unsupported_claim_rate for result in case_results)
        ),
    )


def _batch_status(
    case_results: tuple[LookupSnapshotEvalResult, ...],
    gate_failures: tuple[LookupSnapshotEvalBatchGateFailure, ...],
) -> EvalStatus:
    if any(result.status == "failed" for result in case_results):
        return "failed"
    if gate_failures:
        return "failed"
    return "passed"


def _metric_deltas(
    current: LookupSnapshotEvalBatchMetrics,
    baseline: LookupSnapshotEvalBatchMetrics | None,
) -> LookupSnapshotEvalBatchMetricDeltas | None:
    if baseline is None:
        return None
    return LookupSnapshotEvalBatchMetricDeltas(
        pass_rate=current.pass_rate - baseline.pass_rate,
        field_value_accuracy=current.field_value_accuracy - baseline.field_value_accuracy,
        display_state_accuracy=current.display_state_accuracy - baseline.display_state_accuracy,
        citation_coverage=current.citation_coverage - baseline.citation_coverage,
        warning_coverage=current.warning_coverage - baseline.warning_coverage,
        ingestion_quality_flag_coverage=(
            current.ingestion_quality_flag_coverage - baseline.ingestion_quality_flag_coverage
        ),
        deterministic_calculation_reproducibility=(
            current.deterministic_calculation_reproducibility
            - baseline.deterministic_calculation_reproducibility
        ),
        unsupported_claim_rate=current.unsupported_claim_rate - baseline.unsupported_claim_rate,
    )


def _gate_failures(
    current: LookupSnapshotEvalBatchMetrics,
    baseline: LookupSnapshotEvalBatchMetrics | None,
) -> tuple[LookupSnapshotEvalBatchGateFailure, ...]:
    if baseline is None:
        return ()
    failures: list[LookupSnapshotEvalBatchGateFailure] = []
    for metric, current_value, baseline_value in _higher_is_better_metrics(current, baseline):
        if current_value + 1e-12 < baseline_value:
            failures.append(
                LookupSnapshotEvalBatchGateFailure(
                    metric=metric,
                    reason="regressed",
                    current=current_value,
                    baseline=baseline_value,
                )
            )
    if current.unsupported_claim_rate > baseline.unsupported_claim_rate + 1e-12:
        failures.append(
            LookupSnapshotEvalBatchGateFailure(
                metric="unsupported_claim_rate",
                reason="regressed",
                current=current.unsupported_claim_rate,
                baseline=baseline.unsupported_claim_rate,
            )
        )
    return tuple(failures)


def _higher_is_better_metrics(
    current: LookupSnapshotEvalBatchMetrics,
    baseline: LookupSnapshotEvalBatchMetrics,
) -> tuple[tuple[str, float, float], ...]:
    return (
        ("pass_rate", current.pass_rate, baseline.pass_rate),
        ("field_value_accuracy", current.field_value_accuracy, baseline.field_value_accuracy),
        (
            "display_state_accuracy",
            current.display_state_accuracy,
            baseline.display_state_accuracy,
        ),
        ("citation_coverage", current.citation_coverage, baseline.citation_coverage),
        ("warning_coverage", current.warning_coverage, baseline.warning_coverage),
        (
            "ingestion_quality_flag_coverage",
            current.ingestion_quality_flag_coverage,
            baseline.ingestion_quality_flag_coverage,
        ),
        (
            "deterministic_calculation_reproducibility",
            current.deterministic_calculation_reproducibility,
            baseline.deterministic_calculation_reproducibility,
        ),
    )


def _mean(values: tuple[float, ...]) -> float:
    return sum(values) / len(values)
