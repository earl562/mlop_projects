from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from pydantic import Field, field_validator, model_validator

from plotlot.harness.contracts import (
    EvidenceId,
    JsonObject,
    MemoryId,
    MemoryItem,
    MemoryType,
    ProjectId,
    RunId,
    SiteId,
    WorkspaceId,
)
from plotlot.harness.contracts.base import HarnessContract, utc_now

MEMORY_STORE_PATH_ENV = "PLOTLOT_HARNESS_MEMORY_STORE_PATH"


@dataclass(frozen=True, slots=True)
class MemoryNotFoundError(Exception):
    memory_id: MemoryId

    def __str__(self) -> str:
        return f"Memory not found: {self.memory_id}"


class MemoryWriteRequest(HarnessContract):
    workspace_id: WorkspaceId = Field(min_length=1)
    project_id: ProjectId | None = Field(default=None, min_length=1)
    site_id: SiteId | None = Field(default=None, min_length=1)
    memory_type: MemoryType
    content: str = Field(min_length=1)
    source_run_id: RunId | None = Field(default=None, min_length=1)
    evidence_ids: list[EvidenceId] = Field(default_factory=list)
    metadata: JsonObject = Field(default_factory=dict)

    @field_validator("content")
    @classmethod
    def _content_must_have_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("memory content must contain text")
        return value


class MemoryUpdateRequest(HarnessContract):
    content: str | None = Field(default=None, min_length=1)
    metadata: JsonObject | None = None

    @field_validator("content")
    @classmethod
    def _content_must_have_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("memory content must contain text")
        return value

    @model_validator(mode="after")
    def _must_update_something(self) -> MemoryUpdateRequest:
        if self.content is None and self.metadata is None:
            raise ValueError("memory update must include content or metadata")
        return self


class MemoryListFilter(HarnessContract):
    workspace_id: WorkspaceId | None = Field(default=None, min_length=1)
    project_id: ProjectId | None = Field(default=None, min_length=1)
    site_id: SiteId | None = Field(default=None, min_length=1)
    source_run_id: RunId | None = Field(default=None, min_length=1)
    memory_type: MemoryType | None = None


class MemoryLedgerSnapshot(HarnessContract):
    memory: dict[str, MemoryItem] = Field(default_factory=dict)


class LocalMemoryStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def write_memory(self, request: MemoryWriteRequest) -> MemoryItem:
        now = utc_now()
        memory = MemoryItem(
            memory_id=MemoryId(f"mem_{uuid4().hex[:12]}"),
            workspace_id=request.workspace_id,
            project_id=request.project_id,
            site_id=request.site_id,
            memory_type=request.memory_type,
            content=request.content,
            source_run_id=request.source_run_id,
            evidence_ids=request.evidence_ids,
            metadata=_memory_metadata(request.metadata),
            created_at=now,
            updated_at=now,
        )
        return self._save(memory)

    def get_memory(self, memory_id: MemoryId) -> MemoryItem:
        snapshot = self._read_snapshot()
        memory = snapshot.memory.get(str(memory_id))
        if memory is None:
            raise MemoryNotFoundError(memory_id=memory_id)
        return memory

    def list_memory(self, filters: MemoryListFilter | None = None) -> list[MemoryItem]:
        active_filters = filters or MemoryListFilter()
        snapshot = self._read_snapshot()
        memory = sorted(
            snapshot.memory.values(), key=lambda item: (item.created_at, item.memory_id)
        )
        return [item for item in memory if _matches_filter(item, active_filters)]

    def update_memory(self, memory_id: MemoryId, request: MemoryUpdateRequest) -> MemoryItem:
        existing = self.get_memory(memory_id)
        metadata = (
            existing.metadata
            if request.metadata is None
            else _memory_metadata({**existing.metadata, **request.metadata})
        )
        content = existing.content if request.content is None else request.content
        return self._save(
            existing.model_copy(
                update={"content": content, "metadata": metadata, "updated_at": utc_now()}
            )
        )

    def _save(self, memory: MemoryItem) -> MemoryItem:
        snapshot = self._read_snapshot()
        items = dict(snapshot.memory)
        items[str(memory.memory_id)] = memory
        self._write_snapshot(MemoryLedgerSnapshot(memory=items))
        return memory

    def _read_snapshot(self) -> MemoryLedgerSnapshot:
        if not self._path.exists():
            return MemoryLedgerSnapshot()
        raw = self._path.read_text(encoding="utf-8")
        if not raw.strip():
            return MemoryLedgerSnapshot()
        return MemoryLedgerSnapshot.model_validate_json(raw)

    def _write_snapshot(self, snapshot: MemoryLedgerSnapshot) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")


def _memory_metadata(metadata: JsonObject) -> JsonObject:
    return {**metadata, "is_evidence": False, "source_of_truth": "project_memory"}


def _matches_filter(item: MemoryItem, filters: MemoryListFilter) -> bool:
    if filters.workspace_id is not None and item.workspace_id != filters.workspace_id:
        return False
    if filters.project_id is not None and item.project_id != filters.project_id:
        return False
    if filters.site_id is not None and item.site_id != filters.site_id:
        return False
    if filters.source_run_id is not None and item.source_run_id != filters.source_run_id:
        return False
    if filters.memory_type is not None and item.memory_type != filters.memory_type:
        return False
    return True


def default_memory_store_path() -> Path:
    configured = os.environ.get(MEMORY_STORE_PATH_ENV)
    if configured:
        return Path(configured).expanduser()
    state_home = os.environ.get("XDG_STATE_HOME")
    base = Path(state_home).expanduser() if state_home else Path.home() / ".local" / "state"
    return base / "plotlot" / "harness-memory.json"


def default_memory_store() -> LocalMemoryStore:
    return LocalMemoryStore(default_memory_store_path())
