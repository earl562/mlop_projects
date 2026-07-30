from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from plotlot.harness.fixture_runs import FixtureDealRunRequest, FixtureDealRunResult
from plotlot.storage.models import Analysis, AnalysisRun, Project, Site, Workspace


@dataclass(frozen=True, slots=True)
class HarnessAnalysisContext:
    workspace_id: str
    project_id: str
    site_id: str | None
    analysis_id: str | None


@dataclass(frozen=True, slots=True)
class HarnessAnalysisContextError(Exception):
    message: str

    def __str__(self) -> str:
        return self.message


async def validate_harness_analysis_context(
    session: AsyncSession,
    request: FixtureDealRunRequest,
) -> HarnessAnalysisContext | None:
    if request.workspace_id is None and request.project_id is None:
        return None
    if request.workspace_id is None or request.project_id is None:
        msg = "workspace_id and project_id are both required when linking a harness run."
        raise HarnessAnalysisContextError(msg)

    workspace = await session.get(Workspace, request.workspace_id)
    if workspace is None:
        msg = "Workspace not found"
        raise HarnessAnalysisContextError(msg)

    project = await session.get(Project, request.project_id)
    if project is None or project.workspace_id != request.workspace_id:
        msg = "Project not found"
        raise HarnessAnalysisContextError(msg)

    if request.site_id is not None:
        site = await session.get(Site, request.site_id)
        if site is None or site.project_id != request.project_id:
            msg = "Site not found"
            raise HarnessAnalysisContextError(msg)

    if request.analysis_id is not None:
        analysis = await session.get(Analysis, request.analysis_id)
        if analysis is None or analysis.project_id != request.project_id:
            msg = "Analysis not found"
            raise HarnessAnalysisContextError(msg)
        if analysis.workspace_id != request.workspace_id:
            msg = "Analysis not found"
            raise HarnessAnalysisContextError(msg)
        if request.site_id is not None and analysis.site_id not in {None, request.site_id}:
            msg = "Analysis does not belong to the provided site"
            raise HarnessAnalysisContextError(msg)

    return HarnessAnalysisContext(
        workspace_id=request.workspace_id,
        project_id=request.project_id,
        site_id=request.site_id,
        analysis_id=request.analysis_id,
    )


async def persist_analysis_run_link(
    session: AsyncSession,
    *,
    context: HarnessAnalysisContext | None,
    request: FixtureDealRunRequest,
    result: FixtureDealRunResult,
) -> FixtureDealRunResult:
    if context is None:
        return result

    now = datetime.now(timezone.utc)
    existing_run = await session.get(AnalysisRun, str(result.run_id))
    input_json = {
        "address": request.address,
        "analysis_type": request.analysis_type,
        "source_mode": request.source_mode.value,
        "assumptions": request.assumptions,
    }
    output_json = {
        "harness_run_id": str(result.run_id),
        "report_id": result.report_id,
        "verification_status": result.verification_status,
        "source_mode": result.source_mode.value,
        "preliminary": result.preliminary,
        "events_url": result.events_url,
        "pipeline_stages": [stage.model_dump(mode="json") for stage in result.pipeline_stages],
    }
    if existing_run is None:
        analysis_run = AnalysisRun(
            id=str(result.run_id),
            workspace_id=context.workspace_id,
            project_id=context.project_id,
            site_id=context.site_id,
            analysis_id=context.analysis_id,
            skill_name=result.analysis_type,
            status=result.status,
            input_json=input_json,
            output_json=output_json,
            started_at=now,
            completed_at=now,
        )
        session.add(analysis_run)
    else:
        mutable_run: Any = existing_run
        mutable_run.workspace_id = context.workspace_id
        mutable_run.project_id = context.project_id
        mutable_run.site_id = context.site_id
        mutable_run.analysis_id = context.analysis_id
        mutable_run.skill_name = result.analysis_type
        mutable_run.status = result.status
        mutable_run.input_json = input_json
        mutable_run.output_json = output_json
        mutable_run.started_at = mutable_run.started_at or now
        mutable_run.completed_at = now
        analysis_run = mutable_run
    await session.flush()
    await session.commit()
    return result.model_copy(
        update={
            "analysis_run_id": analysis_run.id,
            "workspace_id": context.workspace_id,
            "project_id": context.project_id,
            "site_id": context.site_id,
            "analysis_id": context.analysis_id,
        }
    )
