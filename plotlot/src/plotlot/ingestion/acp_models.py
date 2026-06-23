from __future__ import annotations

from pydantic import BaseModel


class IngestRequest(BaseModel):
    municipality: str
    state: str
    county: str | None = None
    trigger: str = "search_miss"
    workspace_id: str | None = None
    project_id: str | None = None
    site_id: str | None = None
    analysis_id: str | None = None
    analysis_run_id: str | None = None
    tool_run_id: str | None = None


class IngestProgress(BaseModel):
    stage: str
    message: str
    chunks_done: int = 0
    chunks_total: int = 0
    complete: bool = False
    error: str | None = None
    evidence_ids: tuple[str, ...] = ()
    quality_flags: tuple[str, ...] = ()
    source_record_count: int = 0
