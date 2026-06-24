from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from plotlot.api.agent_run_models import (
    AgentRunResponse,
    AgentRunStartRequest,
    agent_run_response,
)
from plotlot.core.lookup_snapshot import LookupSnapshot, RunId
from plotlot.harness.agent_run_lookup import load_agent_run_lookup_snapshot
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
from plotlot.harness import (
    AgentRunRecord,
    AgentRunRequest,
    AgentRunRuntime,
    ContextBuildRequest,
)
from plotlot.harness.agent_run_repository import (
    AgentRunIdConflictError,
    AgentRunPersistenceInput,
    load_agent_run_response,
    persist_agent_run,
)
from plotlot.harness.agent_run_store import get_stored_agent_run, save_agent_run
from plotlot.harness.agent_run_summary import (
    AgentRunSummaryArtifact,
    build_agent_run_summary_artifact,
    build_agent_run_summary_from_response,
)
from plotlot.harness.agent_run_trace import (
    AgentRunReplayTraceInput,
    AgentRunReplayTraceResponse,
    build_agent_run_replay_trace,
)
from plotlot.pipeline.lookup_snapshot_json import JsonValue
from plotlot.storage.db import get_session

router = APIRouter(prefix="/agent-runs", tags=["agent-runs"])


@router.post("", response_model=AgentRunResponse)
async def start_agent_run(request: AgentRunStartRequest) -> AgentRunResponse:
    try:
        snapshot = await _get_lookup_snapshot_domain(request.lookup_snapshot_id)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="Lookup snapshot retrieval failed",
        ) from exc
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Lookup snapshot not found")

    run_id = RunId(request.run_id or str(uuid4()))
    record = AgentRunRuntime().start_run(
        AgentRunRequest(
            run_id=run_id,
            context_request=ContextBuildRequest(
                workspace_id=request.workspace_id,
                project_id=request.project_id,
                site_id=request.site_id,
                objective=request.objective,
                lookup_snapshot=snapshot,
                open_questions=request.open_questions,
                warnings=request.warnings,
            ),
        )
    )
    response = agent_run_response(record, request.lookup_snapshot_id)
    try:
        await _persist_agent_run(record, request.lookup_snapshot_id, response)
    except AgentRunIdConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="Agent run persistence failed",
        ) from exc
    save_agent_run(record, request.lookup_snapshot_id)
    return response


@router.get("/{run_id}", response_model=AgentRunResponse)
async def get_agent_run(run_id: str, workspace_id: str) -> AgentRunResponse:
    stored = get_stored_agent_run(run_id, workspace_id)
    if stored is not None:
        return agent_run_response(stored.record, stored.lookup_snapshot_id)
    try:
        persisted = await _load_agent_run_response(run_id, workspace_id)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Agent run retrieval failed") from exc
    if persisted is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return persisted


@router.get("/{run_id}/summary-artifact", response_model=AgentRunSummaryArtifact)
async def get_agent_run_summary_artifact(
    run_id: str,
    workspace_id: str,
) -> AgentRunSummaryArtifact:
    response = await get_agent_run(run_id, workspace_id)
    try:
        persisted_artifact = await _load_agent_run_summary_artifact(run_id)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Agent run artifact retrieval failed") from exc
    if persisted_artifact is not None:
        return persisted_artifact

    stored = get_stored_agent_run(run_id, workspace_id)
    if stored is not None:
        return build_agent_run_summary_artifact(stored)
    return build_agent_run_summary_from_response(response)


@router.get("/{run_id}/trace", response_model=AgentRunReplayTraceResponse)
async def get_agent_run_trace(run_id: str, workspace_id: str) -> AgentRunReplayTraceResponse:
    response = await get_agent_run(run_id, workspace_id)
    artifact = await get_agent_run_summary_artifact(run_id, workspace_id)
    try:
        latest_eval = await _load_latest_agent_run_eval(run_id)
        improvement_summary = await _load_agent_run_improvement_summary(run_id)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Agent run eval retrieval failed") from exc
    return build_agent_run_replay_trace(
        AgentRunReplayTraceInput(
            response=response,
            artifact=artifact,
            latest_eval=latest_eval,
            improvement_summary=improvement_summary,
        )
    )


@router.post("/{run_id}/evals")
async def evaluate_agent_run(run_id: str, workspace_id: str) -> dict[str, JsonValue]:
    response = await get_agent_run(run_id, workspace_id)
    artifact = await get_agent_run_summary_artifact(run_id, workspace_id)
    result = score_agent_run(response, artifact)
    try:
        stored = await _persist_agent_run_eval(result)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Agent run eval persistence failed") from exc
    return response_to_json(result, stored.eval_run_id, stored.eval_case_result_id)


@router.get("/{run_id}/evals/latest")
async def get_latest_agent_run_eval(run_id: str, workspace_id: str) -> dict[str, JsonValue]:
    await get_agent_run(run_id, workspace_id)
    try:
        record = await _load_latest_agent_run_eval(run_id)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Agent run eval retrieval failed") from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Agent run eval not found")
    return agent_run_eval_record_to_json(record)


@router.get("/{run_id}/improvement-summary")
async def get_agent_run_improvement_summary(
    run_id: str,
    workspace_id: str,
) -> dict[str, JsonValue]:
    await get_agent_run(run_id, workspace_id)
    try:
        summary = await _load_agent_run_improvement_summary(run_id)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Agent run eval retrieval failed") from exc
    if summary is None:
        raise HTTPException(status_code=404, detail="Agent run eval not found")
    return agent_run_improvement_summary_to_json(summary)


async def _get_lookup_snapshot_domain(snapshot_id: str) -> LookupSnapshot | None:
    return await load_agent_run_lookup_snapshot(snapshot_id)


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


async def _load_agent_run_response(
    run_id: str,
    workspace_id: str,
) -> AgentRunResponse | None:
    session = await get_session()
    try:
        return await load_agent_run_response(session, run_id, workspace_id)
    finally:
        await session.close()


async def _load_agent_run_summary_artifact(run_id: str) -> AgentRunSummaryArtifact | None:
    session = await get_session()
    try:
        return await load_agent_run_summary_artifact(session, run_id)
    finally:
        await session.close()


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
