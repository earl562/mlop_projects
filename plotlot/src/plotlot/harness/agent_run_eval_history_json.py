from __future__ import annotations

from datetime import datetime

from plotlot.harness.agent_run_eval_history import (
    AgentRunImprovementSummary,
    StoredAgentRunEvalRecord,
)
from plotlot.harness.agent_run_improvement_log import (
    agent_run_improvement_log_entries_to_json,
)
from plotlot.pipeline.lookup_snapshot_json import JsonValue


def agent_run_eval_record_to_json(
    record: StoredAgentRunEvalRecord,
) -> dict[str, JsonValue]:
    return {
        "run_id": record.run_id,
        "lookup_snapshot_id": record.lookup_snapshot_id,
        "eval_run_id": record.eval_run_id,
        "eval_case_result_id": record.eval_case_result_id,
        "gold_set_case_id": record.gold_set_case_id,
        "status": record.status,
        "created_at": _datetime_to_json(record.created_at),
        "completed_at": _datetime_to_json(record.completed_at),
        "metrics": record.metrics,
        "diffs": record.diffs,
        "evidence_metrics": record.evidence_metrics,
        "trajectory_metrics": record.trajectory_metrics,
    }


def agent_run_improvement_summary_to_json(
    summary: AgentRunImprovementSummary,
) -> dict[str, JsonValue]:
    previous_json = None
    if summary.previous is not None:
        previous_json = agent_run_eval_record_to_json(summary.previous)
    return {
        "current": agent_run_eval_record_to_json(summary.current),
        "previous": previous_json,
        "baseline_status": "available" if summary.previous is not None else "missing",
        "improvement_status": summary.improvement_status,
        "release_blocked": summary.release_blocked,
        "deltas": _deltas_to_json(summary.deltas),
        "improved_metric_keys": list(summary.improved_metric_keys),
        "regressed_metric_keys": list(summary.regressed_metric_keys),
        "improvement_log": agent_run_improvement_log_entries_to_json(summary.improvement_log),
    }


def _deltas_to_json(deltas: dict[str, float]) -> dict[str, JsonValue]:
    return {key: value for key, value in deltas.items()}


def _datetime_to_json(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()
