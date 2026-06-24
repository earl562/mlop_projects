from __future__ import annotations

from plotlot.pipeline.lookup_snapshot_eval import (
    LookupSnapshotEvalMetrics,
    LookupSnapshotEvalResult,
)
from plotlot.pipeline.lookup_snapshot_eval_batch import (
    LookupSnapshotEvalBatchGateFailure,
    LookupSnapshotEvalBatchMetricDeltas,
    LookupSnapshotEvalBatchMetrics,
    LookupSnapshotEvalBatchResult,
)
from plotlot.pipeline.lookup_snapshot_improvement_log import (
    improvement_log_from_batch_result,
)
from plotlot.pipeline.lookup_snapshot_json import JsonValue


def lookup_eval_batch_tool_response(
    result: LookupSnapshotEvalBatchResult,
) -> dict[str, JsonValue]:
    return {
        "suite": result.suite,
        "status": result.status,
        "metrics": _batch_metrics(result.metrics),
        "baseline": _nullable_batch_metrics(result.baseline),
        "metric_deltas": _metric_deltas(result.metric_deltas),
        "gate_failures": _gate_failures(result.gate_failures),
        "improvement_log": _improvement_log(result),
        "case_results": _case_results(result.case_results),
    }


def _case_results(results: tuple[LookupSnapshotEvalResult, ...]) -> list[JsonValue]:
    return [
        {
            "lookup_snapshot_id": result.lookup_snapshot_id,
            "case_id": result.case.case_id,
            "status": result.status,
            "metrics": _eval_metrics(result.metrics),
            "diffs": {
                "case_id": result.case.case_id,
                "lookup_snapshot_id": result.lookup_snapshot_id,
                "field_diffs": [
                    {
                        "field_key": diff.field_key,
                        "reason": diff.reason,
                        "expected_value": diff.expected_value,
                        "observed_value": diff.observed_value,
                        "expected_display_state": diff.expected_display_state,
                        "observed_display_state": diff.observed_display_state,
                    }
                    for diff in result.diffs
                ],
                "missing_warnings": list(result.missing_warnings),
                "missing_quality_flags": list(result.missing_quality_flags),
                "missing_calculations": list(result.missing_calculations),
            },
        }
        for result in results
    ]


def _eval_metrics(metrics: LookupSnapshotEvalMetrics) -> dict[str, JsonValue]:
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


def _batch_metrics(metrics: LookupSnapshotEvalBatchMetrics) -> dict[str, JsonValue]:
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


def _nullable_batch_metrics(
    metrics: LookupSnapshotEvalBatchMetrics | None,
) -> dict[str, JsonValue] | None:
    if metrics is None:
        return None
    return _batch_metrics(metrics)


def _metric_deltas(
    deltas: LookupSnapshotEvalBatchMetricDeltas | None,
) -> dict[str, JsonValue] | None:
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


def _gate_failures(
    failures: tuple[LookupSnapshotEvalBatchGateFailure, ...],
) -> list[JsonValue]:
    return [
        {
            "metric": failure.metric,
            "reason": failure.reason,
            "current": failure.current,
            "baseline": failure.baseline,
        }
        for failure in failures
    ]


def _improvement_log(result: LookupSnapshotEvalBatchResult) -> list[JsonValue]:
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
        for entry in improvement_log_from_batch_result(result)
    ]
