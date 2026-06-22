from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Final

from plotlot.pipeline.lookup_snapshot_eval_batch_history import (
    BATCH_HISTORY_METRIC_KEYS,
    LookupSnapshotEvalBatchHistoryRecord,
)
from plotlot.pipeline.lookup_snapshot_json import JsonValue

RELEASE_GATE_HISTORY_LIMIT: Final = 1


def lookup_snapshot_release_gate_response(
    suite: str,
    records: tuple[LookupSnapshotEvalBatchHistoryRecord, ...],
) -> dict[str, JsonValue]:
    if not records:
        return {
            "status": "success",
            "suite": suite,
            "decision": "blocked",
            "release_blocked": True,
            "reason": "no_completed_eval_run",
            "latest_run": None,
            "blockers": [
                {
                    "code": "missing_eval_history",
                    "message": "No completed lookup-correctness batch eval run is recorded.",
                }
            ],
            "evidence": [],
        }

    latest = records[0]
    blockers = _release_blockers(latest)
    release_blocked = bool(blockers)
    return {
        "status": "success",
        "suite": suite,
        "decision": "blocked" if release_blocked else "passed",
        "release_blocked": release_blocked,
        "reason": _release_reason(latest, blockers),
        "latest_run": lookup_snapshot_eval_run_to_json(latest),
        "blockers": blockers,
        "evidence": [],
    }


def lookup_snapshot_eval_run_to_json(
    record: LookupSnapshotEvalBatchHistoryRecord,
) -> dict[str, JsonValue]:
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


def _release_blockers(record: LookupSnapshotEvalBatchHistoryRecord) -> list[JsonValue]:
    blockers: list[JsonValue] = [
        _gate_failure_blocker(failure) for failure in _json_list(record.payload, "gate_failures")
    ]
    if record.status != "passed":
        blockers.append(
            {
                "code": "latest_eval_failed",
                "status": record.status,
                "message": "Latest lookup-correctness eval run did not pass.",
            }
        )
    return blockers


def _gate_failure_blocker(failure: JsonValue) -> dict[str, JsonValue]:
    payload = _json_object(failure)
    metric = _string_value(payload.get("metric"), "unknown_metric")
    blocker: dict[str, JsonValue] = {
        "code": "regression_gate_failed",
        "metric": metric,
        "message": f"Lookup-correctness regression gate failed for {metric}.",
    }
    for key in ("reason", "current", "baseline"):
        if key in payload:
            blocker[key] = payload[key]
    return blocker


def _release_reason(
    record: LookupSnapshotEvalBatchHistoryRecord,
    blockers: list[JsonValue],
) -> str:
    if record.status != "passed":
        return "latest_eval_failed"
    if blockers:
        return "regression_gate_failed"
    return "latest_eval_passed"


def _metrics(payload: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    return {key: payload[key] for key in BATCH_HISTORY_METRIC_KEYS if key in payload}


def _json_list(payload: Mapping[str, JsonValue], key: str) -> list[JsonValue]:
    value = payload.get(key)
    match value:
        case list():
            return value
        case _:
            return []


def _json_object(value: JsonValue) -> dict[str, JsonValue]:
    if isinstance(value, dict):
        return value
    return {}


def _string_value(value: JsonValue | None, default: str) -> str:
    if isinstance(value, str):
        return value
    return default


def _timestamp(value: datetime | None) -> str | None:
    if value is not None:
        return value.isoformat()
    return None
