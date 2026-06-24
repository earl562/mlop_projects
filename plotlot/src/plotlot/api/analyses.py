"""Durable Analysis + AnalysisRun lifecycle API.

This is the minimal CRUD surface to make the harness spine real:

- Analyses represent a durable intent (skill + scope).
- AnalysisRuns represent one execution attempt.

Tool calls (REST tools/chat/MCP) can attach `analysis_id` / `analysis_run_id` to
ensure evidence, approvals, and artifacts are replayable.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from plotlot.api.tool_artifact_persistence import ToolArtifactContext, persist_tool_artifacts
from plotlot.core.types import AnalysisRunStatus
from plotlot.pipeline.skills.registry import HandlerResult, get_handler
from plotlot.storage.db import get_session
from plotlot.storage.models import Analysis, AnalysisRun, AssumptionSet, Project, Site, Workspace


router = APIRouter(prefix="/api/v1", tags=["analysis_lifecycle"])


class AnalysisCreateRequest(BaseModel):
    workspace_id: str = Field(..., min_length=1, max_length=36)
    project_id: str = Field(..., min_length=1, max_length=36)
    site_id: str | None = Field(default=None, max_length=36)
    name: str = Field(..., min_length=1, max_length=200)
    skill_name: str = Field(..., min_length=1, max_length=120)
    metadata_json: dict = Field(default_factory=dict)


class AnalysisRunCreateRequest(BaseModel):
    input_json: dict = Field(default_factory=dict)


@router.get("/analyses")
async def list_analyses(
    workspace_id: str,
    project_id: str | None = None,
    site_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    session = await get_session()
    try:
        q = select(Analysis).where(Analysis.workspace_id == workspace_id)
        if project_id:
            q = q.where(Analysis.project_id == project_id)
        if site_id:
            q = q.where(Analysis.site_id == site_id)
        if status:
            q = q.where(Analysis.status == status)

        q = q.order_by(Analysis.created_at.asc()).limit(limit).offset(offset)
        result = await session.execute(q)
        rows = result.scalars().all()
        return [
            {
                "id": a.id,
                "workspace_id": a.workspace_id,
                "project_id": a.project_id,
                "site_id": a.site_id,
                "name": a.name,
                "skill_name": a.skill_name,
                "status": a.status,
                "metadata_json": a.metadata_json,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "updated_at": a.updated_at.isoformat() if a.updated_at else None,
            }
            for a in rows
        ]
    finally:
        await session.close()


@router.post("/analyses")
async def create_analysis(body: AnalysisCreateRequest):
    session = await get_session()
    try:
        ws = await session.get(Workspace, body.workspace_id)
        if ws is None:
            raise HTTPException(status_code=404, detail="Workspace not found")

        project = await session.get(Project, body.project_id)
        if project is None or project.workspace_id != body.workspace_id:
            raise HTTPException(status_code=404, detail="Project not found")

        if body.site_id:
            site = await session.get(Site, body.site_id)
            if site is None or site.project_id != body.project_id:
                raise HTTPException(status_code=404, detail="Site not found")

        analysis = Analysis(
            id=str(uuid4()),
            workspace_id=body.workspace_id,
            project_id=body.project_id,
            site_id=body.site_id,
            name=body.name,
            skill_name=body.skill_name,
            status="active",
            metadata_json=body.metadata_json or {},
        )
        session.add(analysis)
        await session.flush()
        await session.commit()
        return {
            "id": analysis.id,
            "workspace_id": analysis.workspace_id,
            "project_id": analysis.project_id,
            "site_id": analysis.site_id,
            "name": analysis.name,
            "skill_name": analysis.skill_name,
            "status": analysis.status,
            "metadata_json": analysis.metadata_json,
        }
    finally:
        await session.close()


@router.get("/analyses/{analysis_id}")
async def get_analysis(analysis_id: str):
    session = await get_session()
    try:
        analysis = await session.get(Analysis, analysis_id)
        if analysis is None:
            raise HTTPException(status_code=404, detail="Analysis not found")
        return {
            "id": analysis.id,
            "workspace_id": analysis.workspace_id,
            "project_id": analysis.project_id,
            "site_id": analysis.site_id,
            "name": analysis.name,
            "skill_name": analysis.skill_name,
            "status": analysis.status,
            "metadata_json": analysis.metadata_json,
            "created_at": analysis.created_at.isoformat() if analysis.created_at else None,
            "updated_at": analysis.updated_at.isoformat() if analysis.updated_at else None,
        }
    finally:
        await session.close()


@router.post("/analyses/{analysis_id}/runs")
async def create_analysis_run(analysis_id: str, body: AnalysisRunCreateRequest):
    session = await get_session()
    try:
        analysis = await session.get(Analysis, analysis_id)
        if analysis is None:
            raise HTTPException(status_code=404, detail="Analysis not found")

        run = AnalysisRun(
            id=str(uuid4()),
            workspace_id=analysis.workspace_id,
            project_id=analysis.project_id,
            site_id=analysis.site_id,
            analysis_id=analysis.id,
            skill_name=analysis.skill_name,
            status=AnalysisRunStatus.PENDING,
            input_json=body.input_json or {},
            output_json={},
        )
        session.add(run)
        await session.flush()
        await session.commit()
        return {
            "id": run.id,
            "analysis_id": run.analysis_id,
            "workspace_id": run.workspace_id,
            "project_id": run.project_id,
            "site_id": run.site_id,
            "skill_name": run.skill_name,
            "status": run.status,
            "input_json": run.input_json,
            "output_json": run.output_json,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        }
    finally:
        await session.close()


@router.get("/analysis-runs")
async def list_analysis_runs(
    workspace_id: str,
    project_id: str | None = None,
    site_id: str | None = None,
    analysis_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    session = await get_session()
    try:
        q = select(AnalysisRun).where(AnalysisRun.workspace_id == workspace_id)
        if project_id:
            q = q.where(AnalysisRun.project_id == project_id)
        if site_id:
            q = q.where(AnalysisRun.site_id == site_id)
        if analysis_id:
            q = q.where(AnalysisRun.analysis_id == analysis_id)
        if status:
            q = q.where(AnalysisRun.status == status)

        q = q.order_by(AnalysisRun.created_at.desc()).limit(limit).offset(offset)
        result = await session.execute(q)
        rows = result.scalars().all()
        return [
            {
                "id": r.id,
                "workspace_id": r.workspace_id,
                "project_id": r.project_id,
                "site_id": r.site_id,
                "analysis_id": r.analysis_id,
                "skill_name": r.skill_name,
                "status": r.status,
                "error_message": r.error_message,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            }
            for r in rows
        ]
    finally:
        await session.close()


@router.get("/analysis-runs/{analysis_run_id}")
async def get_analysis_run(analysis_run_id: str):
    session = await get_session()
    try:
        row = await session.get(AnalysisRun, analysis_run_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Analysis run not found")
        return {
            "id": row.id,
            "workspace_id": row.workspace_id,
            "project_id": row.project_id,
            "site_id": row.site_id,
            "analysis_id": row.analysis_id,
            "skill_name": row.skill_name,
            "status": row.status,
            "input_json": row.input_json,
            "output_json": row.output_json,
            "error_message": row.error_message,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        }
    finally:
        await session.close()


def _run_response(run: AnalysisRun) -> dict:
    """Serialize an AnalysisRun to a response dict.

    Must be called BEFORE session.commit() — commit() expires attributes
    which triggers a lazy-load that fails in async context (MissingGreenlet).
    """
    return {
        "id": run.id,
        "workspace_id": run.workspace_id,
        "project_id": run.project_id,
        "site_id": run.site_id,
        "analysis_id": run.analysis_id,
        "skill_name": run.skill_name,
        "status": run.status,
        "input_json": run.input_json,
        "output_json": run.output_json,
        "error_message": run.error_message,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


@router.post("/analysis-runs/{run_id}/execute")
async def execute_analysis_run(run_id: str):
    """Execute a pending analysis run by dispatching to its registered skill handler."""
    session = await get_session()
    try:
        run = await session.get(AnalysisRun, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Analysis run not found")
        if run.status != AnalysisRunStatus.PENDING:
            raise HTTPException(status_code=409, detail="Run is not pending")

        # Transition to running
        setattr(run, "status", AnalysisRunStatus.RUNNING)
        setattr(run, "started_at", datetime.now(timezone.utc))
        await session.commit()
        await session.refresh(run)

        # Load AssumptionSet for this analysis (if applicable)
        assumption_set = None
        if run.analysis_id:
            stmt = select(AssumptionSet).where(AssumptionSet.analysis_id == run.analysis_id)
            result = await session.execute(stmt)
            assumption_set = result.scalar_one_or_none()

        # Evidence-binding policy check
        if assumption_set is not None:
            from plotlot.pipeline.skills.evidence_policy import check_evidence_binding

            policy_result = check_evidence_binding(assumption_set)
            if policy_result.blocked:
                setattr(run, "status", AnalysisRunStatus.FAILED)
                setattr(run, "error_message", policy_result.message)
                setattr(run, "completed_at", datetime.now(timezone.utc))
                response = _run_response(run)
                await session.commit()
                return response

        # Dispatch to skill handler
        try:
            handler = get_handler(getattr(run, "skill_name"))
            inputs = (
                getattr(assumption_set, "inputs_json", {})
                if assumption_set
                else getattr(run, "input_json", {})
            )
            handler_result: HandlerResult = await handler(inputs)
        except KeyError:
            setattr(run, "status", AnalysisRunStatus.FAILED)
            setattr(run, "error_message", f"Unknown skill: {run.skill_name}")
            setattr(run, "completed_at", datetime.now(timezone.utc))
            response = _run_response(run)
            await session.commit()
            return response
        except Exception as e:
            setattr(run, "status", AnalysisRunStatus.FAILED)
            setattr(run, "error_message", str(e))
            setattr(run, "completed_at", datetime.now(timezone.utc))
            response = _run_response(run)
            await session.commit()
            return response

        # Success — persist output and artifacts
        setattr(run, "output_json", handler_result.output_json)
        setattr(run, "status", AnalysisRunStatus.COMPLETED)
        setattr(run, "completed_at", datetime.now(timezone.utc))

        result_payload = {
            "artifacts": {
                "report": {
                    "status": "generated",
                    "report_json": handler_result.output_json,
                    "evidence_ids": handler_result.evidence_ids,
                }
            }
        }
        context = ToolArtifactContext(
            workspace_id=getattr(run, "workspace_id"),
            project_id=getattr(run, "project_id"),
            site_id=getattr(run, "site_id"),
            analysis_run_id=getattr(run, "id"),
        )
        response = _run_response(run)
        await persist_tool_artifacts(session, result_payload, context)
        await session.commit()
        return response
    finally:
        await session.close()
