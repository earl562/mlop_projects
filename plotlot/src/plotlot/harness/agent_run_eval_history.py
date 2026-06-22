from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from plotlot.harness.agent_run_eval import (
    AGENT_RUN_EVAL_MODEL_PROFILE,
    AGENT_RUN_EVAL_SUITE,
)
from plotlot.harness.agent_run_improvement_log import (
    AgentRunImprovementLogEntry,
    AgentRunImprovementLogInput,
    agent_run_improvement_log_from_metrics,
    agent_run_metric_deltas,
    improved_agent_run_metric_keys,
    regressed_agent_run_metric_keys,
)
from plotlot.pipeline.lookup_snapshot_json import JsonValue
from plotlot.storage.models import EvalCaseResult, EvalRun

AgentRunImprovementStatus = Literal["improved", "regressed", "flat", "no_baseline"]

AGENT_RUN_EVAL_HISTORY_LIMIT_MAX: Final = 50


@dataclass(frozen=True, slots=True)
class StoredAgentRunEvalRecord:
    run_id: str
    lookup_snapshot_id: str
    eval_run_id: str
    eval_case_result_id: str
    gold_set_case_id: str
    status: str
    created_at: datetime | None
    completed_at: datetime | None
    metrics: dict[str, JsonValue]
    diffs: dict[str, JsonValue]
    evidence_metrics: dict[str, JsonValue]
    trajectory_metrics: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class AgentRunImprovementSummary:
    current: StoredAgentRunEvalRecord
    previous: StoredAgentRunEvalRecord | None
    deltas: dict[str, float]
    improved_metric_keys: tuple[str, ...]
    regressed_metric_keys: tuple[str, ...]
    improvement_status: AgentRunImprovementStatus
    release_blocked: bool
    improvement_log: tuple[AgentRunImprovementLogEntry, ...]


async def load_agent_run_eval_history(
    session: AsyncSession,
    run_id: str,
    *,
    limit: int = 20,
) -> tuple[StoredAgentRunEvalRecord, ...]:
    records = await _load_agent_run_eval_records(session, limit=AGENT_RUN_EVAL_HISTORY_LIMIT_MAX)
    matching_records = [record for record in records if record.run_id == run_id]
    return tuple(matching_records[: _clamped_limit(limit)])


async def load_latest_agent_run_eval(
    session: AsyncSession,
    run_id: str,
) -> StoredAgentRunEvalRecord | None:
    history = await load_agent_run_eval_history(session, run_id, limit=1)
    if not history:
        return None
    return history[0]


async def load_agent_run_improvement_summary(
    session: AsyncSession,
    run_id: str,
) -> AgentRunImprovementSummary | None:
    current = await load_latest_agent_run_eval(session, run_id)
    if current is None:
        return None
    previous = await _load_previous_agent_run_eval_baseline(session, current.eval_run_id)
    previous_metrics = previous.metrics if previous is not None else None
    deltas = agent_run_metric_deltas(current.metrics, previous_metrics)
    improved_metric_keys = improved_agent_run_metric_keys(deltas)
    regressed_metric_keys = regressed_agent_run_metric_keys(deltas)
    return AgentRunImprovementSummary(
        current=current,
        previous=previous,
        deltas=deltas,
        improved_metric_keys=improved_metric_keys,
        regressed_metric_keys=regressed_metric_keys,
        improvement_status=_improvement_status(
            previous,
            improved_metric_keys,
            regressed_metric_keys,
        ),
        release_blocked=current.status != "passed" or bool(regressed_metric_keys),
        improvement_log=agent_run_improvement_log_from_metrics(
            AgentRunImprovementLogInput(
                researched_input=current.run_id,
                affected_golden_cases=(current.gold_set_case_id,),
                current_status=current.status,
                current_metrics=current.metrics,
                previous_metrics=previous_metrics,
            )
        ),
    )


async def _load_previous_agent_run_eval_baseline(
    session: AsyncSession,
    current_eval_run_id: str,
) -> StoredAgentRunEvalRecord | None:
    records = await _load_agent_run_eval_records(session, limit=AGENT_RUN_EVAL_HISTORY_LIMIT_MAX)
    for record in records:
        if record.eval_run_id != current_eval_run_id:
            return record
    return None


async def _load_agent_run_eval_records(
    session: AsyncSession,
    *,
    limit: int,
) -> tuple[StoredAgentRunEvalRecord, ...]:
    result = await session.execute(
        select(EvalRun, EvalCaseResult)
        .join(EvalCaseResult, EvalCaseResult.eval_run_id == EvalRun.id)
        .where(
            EvalRun.suite == AGENT_RUN_EVAL_SUITE,
            EvalRun.model_profile == AGENT_RUN_EVAL_MODEL_PROFILE,
            EvalRun.completed_at.is_not(None),
        )
        .order_by(EvalRun.completed_at.desc(), EvalRun.created_at.desc())
        .limit(_clamped_limit(limit))
    )
    records: list[StoredAgentRunEvalRecord] = []
    for eval_run, case_result in result.tuples().all():
        record = _record_from_rows(eval_run, case_result)
        if record is not None:
            records.append(record)
    return tuple(records)


def _record_from_rows(
    eval_run: EvalRun,
    case_result: EvalCaseResult,
) -> StoredAgentRunEvalRecord | None:
    metrics = _json_object(getattr(eval_run, "metrics_json"))
    diffs = _json_object(getattr(case_result, "diffs_json"))
    evidence_metrics = _json_object(getattr(case_result, "evidence_metrics_json"))
    trajectory_metrics = _json_object(getattr(case_result, "trajectory_metrics_json"))
    run_id = _json_str(diffs, "run_id")
    lookup_snapshot_id = _json_str(diffs, "lookup_snapshot_id")
    eval_run_id = _str_attr(eval_run, "id")
    eval_case_result_id = _str_attr(case_result, "id")
    gold_set_case_id = _str_attr(case_result, "gold_set_case_id")
    status = _str_attr(eval_run, "status")
    if (
        metrics is None
        or diffs is None
        or evidence_metrics is None
        or trajectory_metrics is None
        or run_id is None
        or lookup_snapshot_id is None
        or eval_run_id is None
        or eval_case_result_id is None
        or gold_set_case_id is None
        or status is None
    ):
        return None
    return StoredAgentRunEvalRecord(
        run_id=run_id,
        lookup_snapshot_id=lookup_snapshot_id,
        eval_run_id=eval_run_id,
        eval_case_result_id=eval_case_result_id,
        gold_set_case_id=gold_set_case_id,
        status=status,
        created_at=_datetime_attr(eval_run, "created_at"),
        completed_at=_datetime_attr(eval_run, "completed_at"),
        metrics=metrics,
        diffs=diffs,
        evidence_metrics=evidence_metrics,
        trajectory_metrics=trajectory_metrics,
    )


def _improvement_status(
    previous: StoredAgentRunEvalRecord | None,
    improved_metric_keys: tuple[str, ...],
    regressed_metric_keys: tuple[str, ...],
) -> AgentRunImprovementStatus:
    if previous is None:
        return "no_baseline"
    if regressed_metric_keys:
        return "regressed"
    if improved_metric_keys:
        return "improved"
    return "flat"


def _json_object(value: JsonValue) -> dict[str, JsonValue] | None:
    if not isinstance(value, dict):
        return None
    return {key: item for key, item in value.items() if isinstance(key, str)}


def _json_str(payload: dict[str, JsonValue] | None, key: str) -> str | None:
    if payload is None:
        return None
    value = payload.get(key)
    if isinstance(value, str) and value:
        return value
    return None


def _str_attr(row: EvalRun | EvalCaseResult, name: str) -> str | None:
    value = getattr(row, name)
    if isinstance(value, str):
        return value
    return None


def _datetime_attr(row: EvalRun | EvalCaseResult, name: str) -> datetime | None:
    value = getattr(row, name)
    if isinstance(value, datetime):
        return value
    return None


def _clamped_limit(limit: int) -> int:
    return max(1, min(limit, AGENT_RUN_EVAL_HISTORY_LIMIT_MAX))
