from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.exc import SQLAlchemyError

from plotlot.harness.agent_run_artifact_repository import load_agent_run_summary_artifact
from plotlot.harness.agent_run_eval import AgentRunEvalResult, score_agent_run
from plotlot.harness.agent_run_eval_history import (
    AgentRunImprovementSummary,
    StoredAgentRunEvalRecord,
    load_agent_run_improvement_summary,
    load_latest_agent_run_eval,
)
from plotlot.harness.agent_run_eval_history_json import (
    agent_run_eval_record_to_json,
    agent_run_improvement_summary_to_json,
)
from plotlot.harness.agent_run_eval_json import response_to_json
from plotlot.harness.agent_run_eval_repository import (
    StoredAgentRunEval,
    persist_agent_run_eval_result,
)
from plotlot.harness.agent_run_repository import load_agent_run_response
from plotlot.harness.agent_run_responses import AgentRunResponse, agent_run_response
from plotlot.harness.agent_run_store import get_stored_agent_run
from plotlot.harness.agent_run_summary import (
    AgentRunSummaryArtifact,
    build_agent_run_summary_artifact,
    build_agent_run_summary_from_response,
)
from plotlot.land_use.models import ToolContext
from plotlot.pipeline.lookup_snapshot_json import JsonValue
from plotlot.storage.db import get_session


class AgentRunEvalToolArgs(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str = Field(min_length=1)


async def handle_evaluate_agent_run(
    args: Mapping[str, JsonValue],
    context: ToolContext,
) -> dict[str, JsonValue]:
    parsed = _parse_args(args)
    if isinstance(parsed, dict):
        return parsed

    try:
        response = await _load_agent_run(parsed.run_id, context.workspace_id)
        if response is None:
            return {"status": "not_found", "message": "Agent run not found", "evidence": []}
        artifact = await _load_agent_run_artifact(parsed.run_id, response)
        result = score_agent_run(response, artifact)
        stored = await _persist_agent_run_eval(result)
    except SQLAlchemyError:
        return {
            "status": "error",
            "message": "Agent run eval persistence failed",
            "evidence": [],
        }

    return {
        "status": "success",
        "eval": response_to_json(result, stored.eval_run_id, stored.eval_case_result_id),
        "evidence": [],
    }


async def handle_get_latest_agent_run_eval(
    args: Mapping[str, JsonValue],
    context: ToolContext,
) -> dict[str, JsonValue]:
    parsed = _parse_args(args)
    if isinstance(parsed, dict):
        return parsed

    try:
        if await _load_agent_run(parsed.run_id, context.workspace_id) is None:
            return {"status": "not_found", "message": "Agent run not found", "evidence": []}
        record = await _load_latest_agent_run_eval(parsed.run_id)
    except SQLAlchemyError:
        return {
            "status": "error",
            "message": "Agent run eval retrieval failed",
            "evidence": [],
        }
    if record is None:
        return {"status": "not_found", "message": "Agent run eval not found", "evidence": []}
    return {"status": "success", "eval": agent_run_eval_record_to_json(record), "evidence": []}


async def handle_get_agent_run_improvement_summary(
    args: Mapping[str, JsonValue],
    context: ToolContext,
) -> dict[str, JsonValue]:
    parsed = _parse_args(args)
    if isinstance(parsed, dict):
        return parsed

    try:
        if await _load_agent_run(parsed.run_id, context.workspace_id) is None:
            return {"status": "not_found", "message": "Agent run not found", "evidence": []}
        summary = await _load_agent_run_improvement_summary(parsed.run_id)
    except SQLAlchemyError:
        return {
            "status": "error",
            "message": "Agent run eval retrieval failed",
            "evidence": [],
        }
    if summary is None:
        return {"status": "not_found", "message": "Agent run eval not found", "evidence": []}
    return {
        "status": "success",
        "improvement": agent_run_improvement_summary_to_json(summary),
        "evidence": [],
    }


def _parse_args(args: Mapping[str, JsonValue]) -> AgentRunEvalToolArgs | dict[str, JsonValue]:
    try:
        return AgentRunEvalToolArgs.model_validate(args)
    except ValidationError as exc:
        return {"status": "error", "message": str(exc), "evidence": []}


async def _load_agent_run(run_id: str, workspace_id: str) -> AgentRunResponse | None:
    stored = get_stored_agent_run(run_id, workspace_id)
    if stored is not None:
        return agent_run_response(stored.record, stored.lookup_snapshot_id)
    session = await get_session()
    try:
        return await load_agent_run_response(session, run_id, workspace_id)
    finally:
        await session.close()


async def _load_agent_run_artifact(
    run_id: str,
    response: AgentRunResponse,
) -> AgentRunSummaryArtifact:
    session = await get_session()
    try:
        artifact = await load_agent_run_summary_artifact(session, run_id)
    finally:
        await session.close()
    if artifact is not None:
        return artifact
    stored = get_stored_agent_run(run_id)
    if stored is not None:
        return build_agent_run_summary_artifact(stored)
    return build_agent_run_summary_from_response(response)


async def _persist_agent_run_eval(result: AgentRunEvalResult) -> StoredAgentRunEval:
    session = await get_session()
    try:
        return await persist_agent_run_eval_result(session, result)
    finally:
        await session.close()


async def _load_latest_agent_run_eval(run_id: str) -> StoredAgentRunEvalRecord | None:
    session = await get_session()
    try:
        return await load_latest_agent_run_eval(session, run_id)
    finally:
        await session.close()


async def _load_agent_run_improvement_summary(
    run_id: str,
) -> AgentRunImprovementSummary | None:
    session = await get_session()
    try:
        return await load_agent_run_improvement_summary(session, run_id)
    finally:
        await session.close()
