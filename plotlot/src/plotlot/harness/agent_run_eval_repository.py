from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.ext.asyncio import AsyncSession

from plotlot.harness.agent_run_eval import (
    AGENT_RUN_EVAL_MODEL_PROFILE,
    AGENT_RUN_EVAL_SUITE,
    AgentRunEvalResult,
)
from plotlot.harness.agent_run_eval_json import diffs_to_json, metrics_to_json
from plotlot.pipeline.lookup_snapshot_json import JsonValue
from plotlot.storage.models import EvalCaseResult, EvalRun, GoldSetCase


@dataclass(frozen=True, slots=True)
class StoredAgentRunEval:
    gold_set_case_id: str
    eval_run_id: str
    eval_case_result_id: str


@dataclass(frozen=True, slots=True)
class _EvalWriteIds:
    gold_set_case_id: str
    eval_run_id: str
    eval_case_result_id: str


@dataclass(frozen=True, slots=True)
class _EvalWriteContext:
    result: AgentRunEvalResult
    ids: _EvalWriteIds
    now: datetime


async def persist_agent_run_eval_result(
    session: AsyncSession,
    result: AgentRunEvalResult,
) -> StoredAgentRunEval:
    ids = _eval_write_ids(result)
    context = _EvalWriteContext(result=result, ids=ids, now=datetime.now(UTC))
    await _upsert_gold_case(session, context)
    await _upsert_eval_run(session, context)
    await _upsert_case_result(session, context)
    await session.commit()
    return StoredAgentRunEval(
        gold_set_case_id=ids.gold_set_case_id,
        eval_run_id=ids.eval_run_id,
        eval_case_result_id=ids.eval_case_result_id,
    )


async def _upsert_gold_case(
    session: AsyncSession,
    context: _EvalWriteContext,
) -> None:
    row = await session.get(GoldSetCase, context.ids.gold_set_case_id)
    expected_json = _expected_json(context.result)
    if row is None:
        session.add(
            GoldSetCase(
                id=context.ids.gold_set_case_id,
                suite=AGENT_RUN_EVAL_SUITE,
                case_id=_case_id(context.result),
                jurisdiction="agent-run",
                address=None,
                expected_json=expected_json,
                source_urls=[],
                tags=["agent_run", "lookup_correctness"],
                created_at=context.now,
                updated_at=context.now,
            )
        )
    else:
        setattr(row, "expected_json", expected_json)
        setattr(row, "tags", ["agent_run", "lookup_correctness"])
        setattr(row, "updated_at", context.now)
    await session.flush()


async def _upsert_eval_run(
    session: AsyncSession,
    context: _EvalWriteContext,
) -> None:
    row = await session.get(EvalRun, context.ids.eval_run_id)
    metrics_json = metrics_to_json(context.result.metrics)
    if row is None:
        session.add(
            EvalRun(
                id=context.ids.eval_run_id,
                suite=AGENT_RUN_EVAL_SUITE,
                git_sha=None,
                model_profile=AGENT_RUN_EVAL_MODEL_PROFILE,
                status=context.result.status,
                metrics_json=metrics_json,
                created_at=context.now,
                completed_at=context.now,
            )
        )
    else:
        setattr(row, "status", context.result.status)
        setattr(row, "metrics_json", metrics_json)
        setattr(row, "completed_at", context.now)
    await session.flush()


async def _upsert_case_result(
    session: AsyncSession,
    context: _EvalWriteContext,
) -> None:
    evidence_metrics_json: dict[str, JsonValue] = {
        "evidence_coverage": context.result.metrics.evidence_coverage,
        "source_quality_traceability": context.result.metrics.source_quality_traceability,
        "artifact_citation_coverage": context.result.metrics.artifact_citation_coverage,
        "opportunity_hypothesis_completeness": (
            context.result.metrics.opportunity_hypothesis_completeness
        ),
        "assumption_label_coverage": context.result.metrics.assumption_label_coverage,
        "unsupported_claim_rate": context.result.metrics.unsupported_claim_rate,
    }
    trajectory_metrics_json: dict[str, JsonValue] = {
        "trace_replayability": context.result.metrics.trace_replayability,
        "calculation_lineage_traceability": (
            context.result.metrics.calculation_lineage_traceability
        ),
        "specialist_lane_coverage": context.result.metrics.specialist_lane_coverage,
        "escalation_visibility": context.result.metrics.escalation_visibility,
        "ready_for_synthesis_gate": context.result.metrics.ready_for_synthesis_gate,
    }
    row = await session.get(EvalCaseResult, context.ids.eval_case_result_id)
    if row is None:
        session.add(
            EvalCaseResult(
                id=context.ids.eval_case_result_id,
                eval_run_id=context.ids.eval_run_id,
                gold_set_case_id=context.ids.gold_set_case_id,
                status=context.result.status,
                diffs_json=diffs_to_json(context.result),
                evidence_metrics_json=evidence_metrics_json,
                trajectory_metrics_json=trajectory_metrics_json,
            )
        )
    else:
        setattr(row, "status", context.result.status)
        setattr(row, "diffs_json", diffs_to_json(context.result))
        setattr(row, "evidence_metrics_json", evidence_metrics_json)
        setattr(row, "trajectory_metrics_json", trajectory_metrics_json)
    await session.flush()


def _eval_write_ids(result: AgentRunEvalResult) -> _EvalWriteIds:
    eval_run_id = _eval_run_id(result)
    return _EvalWriteIds(
        gold_set_case_id=_gold_case_id(result),
        eval_run_id=eval_run_id,
        eval_case_result_id=_case_result_id(eval_run_id, result),
    )


def _expected_json(result: AgentRunEvalResult) -> dict[str, JsonValue]:
    return {
        "run_id": result.run_id,
        "lookup_snapshot_id": result.lookup_snapshot_id,
        "missing_required_lanes": list(result.missing_required_lanes),
        "missing_trace_requirements": list(result.missing_trace_requirements),
        "missing_evidence_packet_ids": list(result.missing_evidence_packet_ids),
        "incomplete_evidence_packet_ids": list(result.incomplete_evidence_packet_ids),
        "missing_calculation_outputs": list(result.missing_calculation_outputs),
        "unsupported_claim_keys": list(result.unsupported_claim_keys),
        "incomplete_opportunity_keys": list(result.incomplete_opportunity_keys),
        "missing_assumption_keys": list(result.missing_assumption_keys),
    }


def _case_id(result: AgentRunEvalResult) -> str:
    return f"agent-run:{result.run_id}"


def _gold_case_id(result: AgentRunEvalResult) -> str:
    return str(uuid5(NAMESPACE_URL, f"plotlot:{AGENT_RUN_EVAL_SUITE}:case:{_case_id(result)}"))


def _eval_run_id(result: AgentRunEvalResult) -> str:
    return str(uuid5(NAMESPACE_URL, f"plotlot:{AGENT_RUN_EVAL_SUITE}:run:{result.run_id}"))


def _case_result_id(eval_run_id: str, result: AgentRunEvalResult) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            f"plotlot:{AGENT_RUN_EVAL_SUITE}:result:{eval_run_id}:{_case_id(result)}",
        )
    )
