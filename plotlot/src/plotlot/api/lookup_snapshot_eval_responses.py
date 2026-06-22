from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import TypedDict

from plotlot.pipeline.lookup_snapshot_eval_batch import LookupSnapshotEvalBatchResult
from plotlot.pipeline.lookup_snapshot_eval_batch_history import (
    BATCH_HISTORY_METRIC_KEYS,
    LookupSnapshotEvalBatchHistoryRecord,
)
from plotlot.pipeline.lookup_snapshot_eval_batch_json import (
    LookupSnapshotEvalBatchGateFailureJson,
    LookupSnapshotEvalBatchMetricDeltasJson,
    LookupSnapshotEvalBatchMetricsJson,
    batch_metrics_to_json,
    batch_result_to_json,
)
from plotlot.pipeline.lookup_snapshot_eval_json import (
    LookupSnapshotEvalDiffsJson,
    LookupSnapshotEvalMetricsJson,
    diffs_to_json,
    metrics_to_json,
)
from plotlot.pipeline.lookup_snapshot_improvement_log import (
    LookupSnapshotImprovementLogEntryJson,
)
from plotlot.pipeline.lookup_snapshot_json import JsonValue


class LookupSnapshotEvalBatchCaseResultJson(TypedDict):
    lookup_snapshot_id: str
    case_id: str
    status: str
    metrics: LookupSnapshotEvalMetricsJson
    diffs: LookupSnapshotEvalDiffsJson


class LookupSnapshotEvalBatchResponseJson(TypedDict):
    suite: str
    status: str
    metrics: LookupSnapshotEvalBatchMetricsJson
    baseline: LookupSnapshotEvalBatchMetricsJson | None
    metric_deltas: LookupSnapshotEvalBatchMetricDeltasJson | None
    gate_failures: list[LookupSnapshotEvalBatchGateFailureJson]
    improvement_log: list[LookupSnapshotImprovementLogEntryJson]
    case_results: list[LookupSnapshotEvalBatchCaseResultJson]


class LookupSnapshotEvalBatchHistoryRunJson(TypedDict):
    eval_run_id: str
    suite: str
    status: str
    created_at: str | None
    completed_at: str | None
    metrics: dict[str, JsonValue]
    baseline: JsonValue
    metric_deltas: JsonValue
    gate_failures: list[JsonValue]
    improvement_log: list[JsonValue]
    case_ids: list[JsonValue]
    lookup_snapshot_ids: list[JsonValue]


class LookupSnapshotEvalBatchHistoryResponseJson(TypedDict):
    runs: list[LookupSnapshotEvalBatchHistoryRunJson]


def batch_eval_response(
    result: LookupSnapshotEvalBatchResult,
) -> LookupSnapshotEvalBatchResponseJson:
    payload = batch_result_to_json(result)
    return {
        "suite": result.suite,
        "status": result.status,
        "metrics": batch_metrics_to_json(result.metrics),
        "baseline": payload["baseline"],
        "metric_deltas": payload["metric_deltas"],
        "gate_failures": payload["gate_failures"],
        "improvement_log": payload["improvement_log"],
        "case_results": [
            {
                "lookup_snapshot_id": case_result.lookup_snapshot_id,
                "case_id": case_result.case.case_id,
                "status": case_result.status,
                "metrics": metrics_to_json(case_result.metrics),
                "diffs": diffs_to_json(case_result),
            }
            for case_result in result.case_results
        ],
    }


def batch_eval_history_response(
    records: tuple[LookupSnapshotEvalBatchHistoryRecord, ...],
) -> LookupSnapshotEvalBatchHistoryResponseJson:
    return {"runs": [_history_run_response(record) for record in records]}


def _history_run_response(
    record: LookupSnapshotEvalBatchHistoryRecord,
) -> LookupSnapshotEvalBatchHistoryRunJson:
    payload = record.payload
    return {
        "eval_run_id": record.eval_run_id,
        "suite": record.suite,
        "status": record.status,
        "created_at": _timestamp(record.created_at),
        "completed_at": _timestamp(record.completed_at),
        "metrics": _metrics(payload),
        "baseline": payload.get("baseline"),
        "metric_deltas": payload.get("metric_deltas"),
        "gate_failures": _json_list(payload, "gate_failures"),
        "improvement_log": _json_list(payload, "improvement_log"),
        "case_ids": _json_list(payload, "case_ids"),
        "lookup_snapshot_ids": _json_list(payload, "lookup_snapshot_ids"),
    }


def _metrics(payload: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    return {key: payload[key] for key in BATCH_HISTORY_METRIC_KEYS if key in payload}


def _json_list(payload: Mapping[str, JsonValue], key: str) -> list[JsonValue]:
    value = payload.get(key)
    if isinstance(value, list):
        return value
    return []


def _timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()
