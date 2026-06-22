from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.exc import SQLAlchemyError

from plotlot.harness.agent_run_artifact_repository import load_agent_run_summary_artifact
from plotlot.harness.agent_run_eval_history import (
    AgentRunImprovementSummary,
    StoredAgentRunEvalRecord,
    load_agent_run_improvement_summary,
    load_latest_agent_run_eval,
)
from plotlot.harness.agent_run_repository import load_agent_run_response
from plotlot.harness.agent_run_responses import (
    AgentRunResponse,
    agent_run_evidence_packets_json,
    agent_run_response,
)
from plotlot.harness.agent_run_store import get_stored_agent_run
from plotlot.harness.agent_run_summary import (
    AgentRunSummaryArtifact,
    build_agent_run_summary_artifact,
    build_agent_run_summary_from_response,
)
from plotlot.harness.agent_run_trace import (
    AgentRunReplayTraceInput,
    build_agent_run_replay_trace,
)
from plotlot.land_use.models import ToolContext
from plotlot.pipeline.lookup_snapshot_json import JsonValue
from plotlot.storage.db import get_session


class GetAgentRunTraceToolArgs(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str = Field(min_length=1)


async def handle_get_agent_run_trace(
    args: Mapping[str, JsonValue],
    context: ToolContext,
) -> dict[str, JsonValue]:
    try:
        parsed = GetAgentRunTraceToolArgs.model_validate(args)
    except ValidationError as exc:
        return {"status": "error", "message": str(exc), "evidence": []}

    try:
        response = await _load_agent_run(parsed.run_id, context.workspace_id)
        if response is None:
            return {"status": "not_found", "message": "Agent run not found", "evidence": []}
        artifact = await _load_agent_run_artifact(parsed.run_id, response)
        latest_eval = await _load_agent_run_latest_eval(parsed.run_id)
        improvement_summary = await _load_agent_run_improvement(parsed.run_id)
    except SQLAlchemyError:
        return {"status": "error", "message": "Agent run trace retrieval failed", "evidence": []}

    trace = build_agent_run_replay_trace(
        AgentRunReplayTraceInput(
            response=response,
            artifact=artifact,
            latest_eval=latest_eval,
            improvement_summary=improvement_summary,
        )
    )
    return {
        "status": "success",
        "trace": trace.model_dump(mode="json"),
        "evidence_ids": list(trace.evidence_ids),
        "evidence": [],
        "evidence_packets": agent_run_evidence_packets_json(response),
    }


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


async def _load_agent_run_latest_eval(run_id: str) -> StoredAgentRunEvalRecord | None:
    session = await get_session()
    try:
        return await load_latest_agent_run_eval(session, run_id)
    finally:
        await session.close()


async def _load_agent_run_improvement(run_id: str) -> AgentRunImprovementSummary | None:
    session = await get_session()
    try:
        return await load_agent_run_improvement_summary(session, run_id)
    finally:
        await session.close()
