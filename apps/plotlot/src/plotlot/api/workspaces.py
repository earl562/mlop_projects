"""Workspace/project/site/evidence routes for the harness shell."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from plotlot.evidence import EvidenceService
from plotlot.storage.db import get_session
from plotlot.storage.models import EvidenceItem, Project, Report, Site, Workspace

router = APIRouter(prefix="/api/v1", tags=["workspaces"])


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or f"workspace-{uuid.uuid4().hex[:8]}"


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str | None = Field(default=None, max_length=255)


class WorkspaceResponse(BaseModel):
    id: str
    name: str
    slug: str
    created_at: datetime | None = None


class ProjectCreate(BaseModel):
    workspace_id: str
    name: str = Field(min_length=1, max_length=255)
    project_type: str = "site_feasibility"
    criteria: dict[str, Any] = Field(default_factory=dict)


class ProjectResponse(BaseModel):
    id: str
    workspace_id: str
    name: str
    project_type: str
    status: str
    criteria: dict[str, Any]
    created_at: datetime | None = None


class SiteCreate(BaseModel):
    project_id: str
    label: str = Field(min_length=1, max_length=255)
    address: str | None = None
    parcel_id: str | None = None
    lat: float | None = None
    lng: float | None = None
    site_type: str = "candidate"


class SiteResponse(BaseModel):
    id: str
    project_id: str
    label: str
    address: str | None = None
    parcel_id: str | None = None
    lat: float | None = None
    lng: float | None = None
    score: float | None = None
    site_type: str
    created_at: datetime | None = None


class EvidenceCreate(BaseModel):
    workspace_id: str | None = None
    project_id: str | None = None
    site_id: str | None = None
    analysis_run_id: str | None = None
    claim_key: str
    value: dict[str, Any] = Field(default_factory=dict)
    source_type: str
    source_url: str | None = None
    source_title: str | None = None
    tool_name: str = "manual"
    confidence: str = "medium"


class EvidenceResponse(BaseModel):
    id: str
    workspace_id: str | None = None
    project_id: str | None = None
    site_id: str | None = None
    analysis_run_id: str | None = None
    claim_key: str
    value: dict[str, Any]
    source_type: str
    source_url: str | None = None
    source_title: str | None = None
    tool_name: str
    confidence: str
    created_at: datetime | None = None


def _workspace_response(workspace: Workspace) -> WorkspaceResponse:
    return WorkspaceResponse(
        id=cast(str, workspace.id),
        name=cast(str, workspace.name),
        slug=cast(str, workspace.slug),
        created_at=cast(datetime | None, workspace.created_at),
    )


def _project_response(project: Project) -> ProjectResponse:
    criteria = cast(dict[str, Any] | None, project.criteria_json) or {}
    return ProjectResponse(
        id=cast(str, project.id),
        workspace_id=cast(str, project.workspace_id),
        name=cast(str, project.name),
        project_type=cast(str, project.project_type),
        status=cast(str, project.status),
        criteria=criteria,
        created_at=cast(datetime | None, project.created_at),
    )


def _site_response(site: Site) -> SiteResponse:
    return SiteResponse(
        id=cast(str, site.id),
        project_id=cast(str, site.project_id),
        label=cast(str, site.label),
        address=cast(str | None, site.address),
        parcel_id=cast(str | None, site.parcel_id),
        lat=cast(float | None, site.lat),
        lng=cast(float | None, site.lng),
        score=cast(float | None, site.score),
        site_type=cast(str, site.site_type),
        created_at=cast(datetime | None, site.created_at),
    )


def _evidence_response(item: EvidenceItem) -> EvidenceResponse:
    value = cast(dict[str, Any] | None, item.value_json) or {}
    return EvidenceResponse(
        id=cast(str, item.id),
        workspace_id=cast(str | None, item.workspace_id),
        project_id=cast(str | None, item.project_id),
        site_id=cast(str | None, item.site_id),
        analysis_run_id=cast(str | None, item.analysis_run_id),
        claim_key=cast(str, item.claim_key),
        value=value,
        source_type=cast(str, item.source_type),
        source_url=cast(str | None, item.source_url),
        source_title=cast(str | None, item.source_title),
        tool_name=cast(str, item.tool_name),
        confidence=cast(str, item.confidence),
        created_at=cast(datetime | None, item.created_at),
    )


@router.post("/workspaces", response_model=WorkspaceResponse)
async def create_workspace(
    payload: WorkspaceCreate,
    session: AsyncSession = Depends(get_session),
) -> WorkspaceResponse:
    slug = payload.slug or _slugify(payload.name)
    workspace = Workspace(id=str(uuid.uuid4()), name=payload.name, slug=slug)
    session.add(workspace)
    await session.commit()
    await session.refresh(workspace)
    return _workspace_response(workspace)


@router.get("/workspaces", response_model=list[WorkspaceResponse])
async def list_workspaces(session: AsyncSession = Depends(get_session)) -> list[WorkspaceResponse]:
    result = await session.execute(select(Workspace).order_by(Workspace.created_at.desc()))
    return [_workspace_response(workspace) for workspace in result.scalars().all()]


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: str,
    session: AsyncSession = Depends(get_session),
) -> WorkspaceResponse:
    workspace = await session.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return _workspace_response(workspace)


@router.post("/projects", response_model=ProjectResponse)
async def create_project(
    payload: ProjectCreate,
    session: AsyncSession = Depends(get_session),
) -> ProjectResponse:
    if await session.get(Workspace, payload.workspace_id) is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    project = Project(
        id=str(uuid.uuid4()),
        workspace_id=payload.workspace_id,
        name=payload.name,
        project_type=payload.project_type,
        criteria_json=payload.criteria,
    )
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return _project_response(project)


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    session: AsyncSession = Depends(get_session),
) -> ProjectResponse:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return _project_response(project)


@router.get("/workspaces/{workspace_id}/projects", response_model=list[ProjectResponse])
async def list_projects(
    workspace_id: str,
    session: AsyncSession = Depends(get_session),
) -> list[ProjectResponse]:
    result = await session.execute(
        select(Project)
        .where(Project.workspace_id == workspace_id)
        .order_by(Project.created_at.desc())
    )
    return [_project_response(project) for project in result.scalars().all()]


@router.post("/sites", response_model=SiteResponse)
async def create_site(
    payload: SiteCreate, session: AsyncSession = Depends(get_session)
) -> SiteResponse:
    if await session.get(Project, payload.project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")

    site = Site(
        id=str(uuid.uuid4()),
        project_id=payload.project_id,
        label=payload.label,
        address=payload.address,
        parcel_id=payload.parcel_id,
        lat=payload.lat,
        lng=payload.lng,
        site_type=payload.site_type,
    )
    session.add(site)
    await session.commit()
    await session.refresh(site)
    return _site_response(site)


@router.get("/projects/{project_id}/sites", response_model=list[SiteResponse])
async def list_sites(
    project_id: str,
    session: AsyncSession = Depends(get_session),
) -> list[SiteResponse]:
    result = await session.execute(
        select(Site).where(Site.project_id == project_id).order_by(Site.created_at.desc())
    )
    return [_site_response(site) for site in result.scalars().all()]


@router.post("/evidence", response_model=EvidenceResponse)
async def create_evidence(
    payload: EvidenceCreate,
    session: AsyncSession = Depends(get_session),
) -> EvidenceResponse:
    item = await EvidenceService(session).create(
        workspace_id=payload.workspace_id,
        project_id=payload.project_id,
        site_id=payload.site_id,
        analysis_run_id=payload.analysis_run_id,
        claim_key=payload.claim_key,
        value=payload.value,
        source_type=payload.source_type,
        source_url=payload.source_url,
        source_title=payload.source_title,
        tool_name=payload.tool_name,
        confidence=payload.confidence,
    )
    return _evidence_response(item)


@router.get("/projects/{project_id}/evidence", response_model=list[EvidenceResponse])
async def list_project_evidence(
    project_id: str,
    session: AsyncSession = Depends(get_session),
) -> list[EvidenceResponse]:
    items = await EvidenceService(session).list_for_project(project_id)
    return [_evidence_response(item) for item in items]


@router.get("/projects/{project_id}/reports")
async def list_project_reports(
    project_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    result = await session.execute(
        select(Report).where(Report.project_id == project_id).order_by(Report.created_at.desc())
    )
    return {
        "reports": [
            {
                "id": report.id,
                "workspace_id": report.workspace_id,
                "project_id": report.project_id,
                "site_id": report.site_id,
                "report_type": report.report_type,
                "title": report.title,
                "created_at": report.created_at,
            }
            for report in result.scalars().all()
        ]
    }
