from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from plotlot.harness.contracts import (
    EvidenceId,
    JsonObject,
    MemoryId,
    MemoryType,
    ProjectId,
    RunId,
    SiteId,
    WorkspaceId,
)
from plotlot.harness.memory_store import (
    MemoryListFilter,
    MemoryNotFoundError,
    MemoryUpdateRequest,
    MemoryWriteRequest,
    default_memory_store,
)

router = APIRouter(prefix="/api/v1", tags=["harness-memory"])


class HarnessMemoryWriteBody(BaseModel):
    model_config = ConfigDict(frozen=True)

    workspace_id: str = Field(min_length=1)
    project_id: str | None = Field(default=None, min_length=1)
    site_id: str | None = Field(default=None, min_length=1)
    memory_type: MemoryType
    content: str = Field(min_length=1)
    source_run_id: str | None = Field(default=None, min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    metadata: JsonObject = Field(default_factory=dict)


class HarnessMemoryUpdateBody(BaseModel):
    model_config = ConfigDict(frozen=True)

    content: str | None = Field(default=None, min_length=1)
    metadata: JsonObject | None = None


@router.post("/harness/memory")
async def harness_memory_write(body: HarnessMemoryWriteBody) -> JsonObject:
    memory = default_memory_store().write_memory(
        MemoryWriteRequest(
            workspace_id=WorkspaceId(body.workspace_id),
            project_id=ProjectId(body.project_id) if body.project_id else None,
            site_id=SiteId(body.site_id) if body.site_id else None,
            memory_type=body.memory_type,
            content=body.content,
            source_run_id=RunId(body.source_run_id) if body.source_run_id else None,
            evidence_ids=[EvidenceId(value) for value in body.evidence_ids],
            metadata=body.metadata,
        )
    )
    return memory.model_dump(mode="json")


@router.get("/harness/memory")
async def harness_memory_list(request: Request) -> JsonObject:
    memory = default_memory_store().list_memory(_filters_from_request(request))
    return {"memory": [item.model_dump(mode="json") for item in memory]}


@router.get("/harness/memory/{memory_id}")
async def harness_memory_show(memory_id: str) -> JsonObject:
    try:
        memory = default_memory_store().get_memory(MemoryId(memory_id))
    except MemoryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return memory.model_dump(mode="json")


@router.patch("/harness/memory/{memory_id}")
async def harness_memory_update(memory_id: str, body: HarnessMemoryUpdateBody) -> JsonObject:
    try:
        memory = default_memory_store().update_memory(
            MemoryId(memory_id),
            MemoryUpdateRequest(content=body.content, metadata=body.metadata),
        )
    except MemoryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return memory.model_dump(mode="json")


def _filters_from_request(request: Request) -> MemoryListFilter:
    workspace_id = request.query_params.get("workspace_id")
    project_id = request.query_params.get("project_id")
    site_id = request.query_params.get("site_id")
    source_run_id = request.query_params.get("source_run_id")
    memory_type = request.query_params.get("memory_type")
    return MemoryListFilter(
        workspace_id=WorkspaceId(workspace_id) if workspace_id else None,
        project_id=ProjectId(project_id) if project_id else None,
        site_id=SiteId(site_id) if site_id else None,
        source_run_id=RunId(source_run_id) if source_run_id else None,
        memory_type=MemoryType(memory_type) if memory_type else None,
    )
