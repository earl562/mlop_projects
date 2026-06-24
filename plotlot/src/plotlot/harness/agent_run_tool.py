from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.exc import SQLAlchemyError

from plotlot.core.lookup_snapshot import RunId
from plotlot.harness.agent_run import AgentRunRecord, AgentRunRequest, AgentRunRuntime
from plotlot.harness.agent_run_lookup import load_agent_run_lookup_snapshot
from plotlot.harness.agent_run_repository import (
    AgentRunIdConflictError,
    AgentRunPersistenceInput,
    persist_agent_run,
)
from plotlot.harness.agent_run_responses import (
    AgentRunResponse,
    agent_run_evidence_packets_json,
    agent_run_response,
)
from plotlot.harness.agent_run_store import save_agent_run
from plotlot.harness.context import ContextBuildRequest
from plotlot.land_use.models import ToolContext
from plotlot.pipeline.lookup_snapshot_json import JsonValue
from plotlot.storage.db import get_session


class StartAgentRunToolArgs(BaseModel):
    model_config = ConfigDict(frozen=True)

    lookup_snapshot_id: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    open_questions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


async def handle_start_agent_run(
    args: Mapping[str, JsonValue],
    context: ToolContext,
) -> dict[str, JsonValue]:
    try:
        parsed = StartAgentRunToolArgs.model_validate(args)
    except ValidationError as exc:
        return {"status": "error", "message": str(exc), "evidence": []}

    try:
        snapshot = await load_agent_run_lookup_snapshot(parsed.lookup_snapshot_id)
    except SQLAlchemyError:
        return {
            "status": "error",
            "message": "Lookup snapshot retrieval failed",
            "evidence": [],
        }
    if snapshot is None:
        return {
            "status": "not_found",
            "message": "Lookup snapshot not found",
            "evidence": [],
        }

    record = AgentRunRuntime().start_run(
        AgentRunRequest(
            run_id=RunId(context.run_id),
            context_request=ContextBuildRequest(
                workspace_id=context.workspace_id,
                project_id=context.project_id,
                site_id=context.site_id,
                objective=parsed.objective,
                lookup_snapshot=snapshot,
                open_questions=parsed.open_questions,
                warnings=parsed.warnings,
            ),
        )
    )
    response = agent_run_response(record, parsed.lookup_snapshot_id)
    try:
        await _persist_agent_run(record, parsed.lookup_snapshot_id, response)
    except AgentRunIdConflictError:
        return {
            "status": "conflict",
            "message": f"Agent run {context.run_id} already exists",
            "evidence": [],
        }
    except SQLAlchemyError:
        return {
            "status": "error",
            "message": "Agent run persistence failed",
            "evidence": [],
        }
    save_agent_run(record, parsed.lookup_snapshot_id)
    return {
        "status": "success",
        "run": response.model_dump(mode="json"),
        "evidence_ids": list(response.evidence_ids),
        "evidence": [],
        "evidence_packets": agent_run_evidence_packets_json(response),
    }


async def _persist_agent_run(
    record: AgentRunRecord,
    lookup_snapshot_id: str,
    response: AgentRunResponse,
) -> None:
    session = await get_session()
    try:
        await persist_agent_run(
            session,
            AgentRunPersistenceInput(
                record=record,
                lookup_snapshot_id=lookup_snapshot_id,
                response=response,
            ),
        )
    finally:
        await session.close()
