from __future__ import annotations

from plotlot.pipeline.lookup_snapshot_eval import (
    ExpectedLookupField,
    LookupSnapshotEvalMetrics,
    LookupSnapshotEvalResult,
    LookupSnapshotGoldenCase,
)
from plotlot.pipeline.lookup_snapshot_eval_batch import (
    LookupSnapshotEvalBatchGateFailure,
    LookupSnapshotEvalBatchMetricDeltas,
    LookupSnapshotEvalBatchMetrics,
    LookupSnapshotEvalBatchResult,
)
from plotlot.pipeline.lookup_snapshot_improvement_log import (
    LookupSnapshotImprovementLogEntry,
    improvement_log_entries_to_json,
    improvement_log_from_batch_result,
)


def test_improvement_log_records_baseline_delta_context() -> None:
    result = LookupSnapshotEvalBatchResult(
        suite="lookup_correctness",
        status="failed",
        metrics=_batch_metrics(
            pass_rate=0.5,
            citation_coverage=0.75,
            unsupported_claim_rate=0.0,
        ),
        metric_deltas=LookupSnapshotEvalBatchMetricDeltas(
            pass_rate=-0.5,
            field_value_accuracy=0.0,
            display_state_accuracy=0.0,
            citation_coverage=-0.25,
            warning_coverage=0.0,
            deterministic_calculation_reproducibility=0.0,
            unsupported_claim_rate=-0.1,
        ),
        gate_failures=(
            LookupSnapshotEvalBatchGateFailure(
                metric="pass_rate",
                reason="regressed",
                current=0.5,
                baseline=1.0,
            ),
        ),
        baseline=_batch_metrics(
            pass_rate=1.0,
            citation_coverage=1.0,
            unsupported_claim_rate=0.1,
        ),
        case_results=(_case_result("case-a"), _case_result("case-b")),
    )

    entries = improvement_log_from_batch_result(result)

    pass_rate = _entry(entries, "pass_rate")
    assert pass_rate.source == "lookup_snapshot_eval_batch"
    assert pass_rate.researched_input == "lookup_correctness"
    assert pass_rate.changed_rule == "eval_metric:pass_rate"
    assert pass_rate.direction == "regressed"
    assert pass_rate.reason == "baseline_delta"
    assert pass_rate.affected_golden_cases == ("case-a", "case-b")
    assert pass_rate.before_score == 1.0
    assert pass_rate.after_score == 0.5
    assert pass_rate.delta == -0.5
    assert pass_rate.gate_blocking is True
    assert pass_rate.unresolved_risk == "baseline_regression_requires_review"

    unsupported_claim_rate = _entry(entries, "unsupported_claim_rate")
    assert unsupported_claim_rate.direction == "improved"
    assert unsupported_claim_rate.gate_blocking is False
    assert unsupported_claim_rate.unresolved_risk is None

    payload = improvement_log_entries_to_json(entries)
    assert payload[0]["affected_golden_cases"] == ["case-a", "case-b"]


def _batch_metrics(
    *,
    pass_rate: float,
    citation_coverage: float,
    unsupported_claim_rate: float,
) -> LookupSnapshotEvalBatchMetrics:
    return LookupSnapshotEvalBatchMetrics(
        pass_rate=pass_rate,
        case_count=2,
        passed_count=1,
        failed_count=1,
        field_value_accuracy=1.0,
        display_state_accuracy=1.0,
        citation_coverage=citation_coverage,
        warning_coverage=1.0,
        deterministic_calculation_reproducibility=1.0,
        unsupported_claim_rate=unsupported_claim_rate,
    )


def _case_result(case_id: str) -> LookupSnapshotEvalResult:
    return LookupSnapshotEvalResult(
        lookup_snapshot_id=f"ls_{case_id}",
        case=LookupSnapshotGoldenCase(
            case_id=case_id,
            jurisdiction="Miramar, Broward County, FL",
            expected_fields=(ExpectedLookupField(key="parcel.apn", value="504210230010"),),
        ),
        status="passed",
        metrics=LookupSnapshotEvalMetrics(
            field_value_accuracy=1.0,
            display_state_accuracy=1.0,
            citation_coverage=1.0,
            warning_coverage=1.0,
            deterministic_calculation_reproducibility=1.0,
            unsupported_claim_rate=0.0,
            required_field_count=1,
        ),
        diffs=(),
        missing_warnings=(),
        missing_calculations=(),
    )


def _entry(
    entries: tuple[LookupSnapshotImprovementLogEntry, ...],
    metric: str,
) -> LookupSnapshotImprovementLogEntry:
    return next(entry for entry in entries if entry.metric == metric)
