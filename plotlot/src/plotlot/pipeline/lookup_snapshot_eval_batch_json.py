from __future__ import annotations

from collections.abc import Mapping
from typing import TypedDict

from plotlot.pipeline.lookup_snapshot_eval_batch import (
    LookupSnapshotEvalBatchGateFailure,
    LookupSnapshotEvalBatchMetricDeltas,
    LookupSnapshotEvalBatchMetrics,
    LookupSnapshotEvalBatchResult,
)
from plotlot.pipeline.lookup_snapshot_json import JsonValue
from plotlot.pipeline.lookup_snapshot_improvement_log import (
    LookupSnapshotImprovementLogEntryJson,
    improvement_log_entries_to_json,
    improvement_log_from_batch_result,
)


class LookupSnapshotEvalBatchMetricsJson(TypedDict):
    pass_rate: float
    case_count: int
    passed_count: int
    failed_count: int
    field_value_accuracy: float
    display_state_accuracy: float
    citation_coverage: float
    warning_coverage: float
    ingestion_quality_flag_coverage: float
    deterministic_calculation_reproducibility: float
    unsupported_claim_rate: float


class LookupSnapshotEvalBatchMetricDeltasJson(TypedDict):
    pass_rate: float
    field_value_accuracy: float
    display_state_accuracy: float
    citation_coverage: float
    warning_coverage: float
    ingestion_quality_flag_coverage: float
    deterministic_calculation_reproducibility: float
    unsupported_claim_rate: float


class LookupSnapshotEvalBatchGateFailureJson(TypedDict):
    metric: str
    reason: str
    current: float
    baseline: float


class LookupSnapshotEvalBatchResultJson(LookupSnapshotEvalBatchMetricsJson):
    suite: str
    status: str
    case_ids: list[str]
    lookup_snapshot_ids: list[str]
    baseline: LookupSnapshotEvalBatchMetricsJson | None
    metric_deltas: LookupSnapshotEvalBatchMetricDeltasJson | None
    gate_failures: list[LookupSnapshotEvalBatchGateFailureJson]
    improvement_log: list[LookupSnapshotImprovementLogEntryJson]


def batch_result_to_json(
    result: LookupSnapshotEvalBatchResult,
) -> LookupSnapshotEvalBatchResultJson:
    return {
        "suite": result.suite,
        "status": result.status,
        "case_ids": [case_result.case.case_id for case_result in result.case_results],
        "lookup_snapshot_ids": [
            case_result.lookup_snapshot_id for case_result in result.case_results
        ],
        "baseline": _metrics_to_json(result.baseline),
        "metric_deltas": _metric_deltas_to_json(result.metric_deltas),
        "gate_failures": [_gate_failure_to_json(failure) for failure in result.gate_failures],
        "improvement_log": improvement_log_entries_to_json(
            improvement_log_from_batch_result(result)
        ),
        **batch_metrics_to_json(result.metrics),
    }


def batch_metrics_from_json(
    payload: Mapping[str, JsonValue],
) -> LookupSnapshotEvalBatchMetrics | None:
    pass_rate = _float_metric(payload, "pass_rate")
    case_count = _int_metric(payload, "case_count")
    passed_count = _int_metric(payload, "passed_count")
    failed_count = _int_metric(payload, "failed_count")
    field_value_accuracy = _float_metric(payload, "field_value_accuracy")
    display_state_accuracy = _float_metric(payload, "display_state_accuracy")
    citation_coverage = _float_metric(payload, "citation_coverage")
    warning_coverage = _float_metric(payload, "warning_coverage")
    quality_flag_coverage = _float_metric(payload, "ingestion_quality_flag_coverage")
    calculation_reproducibility = _float_metric(
        payload,
        "deterministic_calculation_reproducibility",
    )
    unsupported_claim_rate = _float_metric(payload, "unsupported_claim_rate")

    if (
        pass_rate is None
        or case_count is None
        or passed_count is None
        or failed_count is None
        or field_value_accuracy is None
        or display_state_accuracy is None
        or citation_coverage is None
        or warning_coverage is None
        or calculation_reproducibility is None
        or unsupported_claim_rate is None
    ):
        return None

    if quality_flag_coverage is None:
        quality_flag_coverage = 1.0

    return LookupSnapshotEvalBatchMetrics(
        pass_rate=pass_rate,
        case_count=case_count,
        passed_count=passed_count,
        failed_count=failed_count,
        field_value_accuracy=field_value_accuracy,
        display_state_accuracy=display_state_accuracy,
        citation_coverage=citation_coverage,
        warning_coverage=warning_coverage,
        ingestion_quality_flag_coverage=quality_flag_coverage,
        deterministic_calculation_reproducibility=calculation_reproducibility,
        unsupported_claim_rate=unsupported_claim_rate,
    )


def batch_metrics_to_json(
    metrics: LookupSnapshotEvalBatchMetrics,
) -> LookupSnapshotEvalBatchMetricsJson:
    return {
        "pass_rate": metrics.pass_rate,
        "case_count": metrics.case_count,
        "passed_count": metrics.passed_count,
        "failed_count": metrics.failed_count,
        "field_value_accuracy": metrics.field_value_accuracy,
        "display_state_accuracy": metrics.display_state_accuracy,
        "citation_coverage": metrics.citation_coverage,
        "warning_coverage": metrics.warning_coverage,
        "ingestion_quality_flag_coverage": metrics.ingestion_quality_flag_coverage,
        "deterministic_calculation_reproducibility": (
            metrics.deterministic_calculation_reproducibility
        ),
        "unsupported_claim_rate": metrics.unsupported_claim_rate,
    }


def _metrics_to_json(
    metrics: LookupSnapshotEvalBatchMetrics | None,
) -> LookupSnapshotEvalBatchMetricsJson | None:
    if metrics is None:
        return None
    return batch_metrics_to_json(metrics)


def _metric_deltas_to_json(
    deltas: LookupSnapshotEvalBatchMetricDeltas | None,
) -> LookupSnapshotEvalBatchMetricDeltasJson | None:
    if deltas is None:
        return None
    return {
        "pass_rate": deltas.pass_rate,
        "field_value_accuracy": deltas.field_value_accuracy,
        "display_state_accuracy": deltas.display_state_accuracy,
        "citation_coverage": deltas.citation_coverage,
        "warning_coverage": deltas.warning_coverage,
        "ingestion_quality_flag_coverage": deltas.ingestion_quality_flag_coverage,
        "deterministic_calculation_reproducibility": (
            deltas.deterministic_calculation_reproducibility
        ),
        "unsupported_claim_rate": deltas.unsupported_claim_rate,
    }


def _gate_failure_to_json(
    failure: LookupSnapshotEvalBatchGateFailure,
) -> LookupSnapshotEvalBatchGateFailureJson:
    return {
        "metric": failure.metric,
        "reason": failure.reason,
        "current": failure.current,
        "baseline": failure.baseline,
    }


def _float_metric(payload: Mapping[str, JsonValue], key: str) -> float | None:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _int_metric(payload: Mapping[str, JsonValue], key: str) -> int | None:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value
