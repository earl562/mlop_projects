from __future__ import annotations

import pytest
from pydantic import ValidationError

from plotlot.harness.contracts import EvidenceId, MemoryType, ProjectId, RunId, SiteId, WorkspaceId
from plotlot.harness.memory_store import (
    LocalMemoryStore,
    MemoryListFilter,
    MemoryNotFoundError,
    MemoryUpdateRequest,
    MemoryWriteRequest,
)


def test_memory_store_writes_lists_and_updates_project_memory(tmp_path) -> None:
    store = LocalMemoryStore(tmp_path / "memory.json")

    memory = store.write_memory(
        MemoryWriteRequest(
            workspace_id=WorkspaceId("ws_fixture"),
            project_id=ProjectId("project_fixture"),
            site_id=SiteId("site_fixture"),
            memory_type=MemoryType.SITE_ASSUMPTION,
            content="Use 850 sf average unit size until official plans are provided.",
            source_run_id=RunId("run_fixture_001"),
            evidence_ids=[EvidenceId("ev_fixture_001")],
            metadata={"author": "analyst"},
        )
    )
    listed = store.list_memory(MemoryListFilter(workspace_id=WorkspaceId("ws_fixture")))
    updated = store.update_memory(
        memory.memory_id,
        MemoryUpdateRequest(content="Use 900 sf average unit size from sponsor update."),
    )

    assert memory.metadata["is_evidence"] is False
    assert memory.source_run_id == "run_fixture_001"
    assert memory.evidence_ids == ["ev_fixture_001"]
    assert listed == [memory]
    assert updated.content == "Use 900 sf average unit size from sponsor update."
    assert updated.created_at == memory.created_at
    assert updated.updated_at >= memory.updated_at
    assert store.get_memory(memory.memory_id) == updated


def test_memory_store_filters_by_project_site_and_type(tmp_path) -> None:
    store = LocalMemoryStore(tmp_path / "memory.json")
    first = store.write_memory(
        MemoryWriteRequest(
            workspace_id=WorkspaceId("ws_fixture"),
            project_id=ProjectId("project_fixture"),
            site_id=SiteId("site_fixture"),
            memory_type=MemoryType.OPEN_QUESTION,
            content="Confirm whether the alley vacation affects buildable width.",
        )
    )
    store.write_memory(
        MemoryWriteRequest(
            workspace_id=WorkspaceId("ws_fixture"),
            project_id=ProjectId("other_project"),
            site_id=SiteId("other_site"),
            memory_type=MemoryType.REPORT_PREFERENCE,
            content="Keep lender summaries to one page.",
        )
    )

    filtered = store.list_memory(
        MemoryListFilter(
            workspace_id=WorkspaceId("ws_fixture"),
            project_id=ProjectId("project_fixture"),
            site_id=SiteId("site_fixture"),
            memory_type=MemoryType.OPEN_QUESTION,
        )
    )

    assert filtered == [first]


def test_memory_store_rejects_blank_content_and_missing_ids(tmp_path) -> None:
    store = LocalMemoryStore(tmp_path / "memory.json")

    with pytest.raises(ValidationError):
        store.write_memory(
            MemoryWriteRequest(
                workspace_id=WorkspaceId(""),
                memory_type=MemoryType.PRIOR_DECISION,
                content="",
            )
        )


def test_memory_store_raises_typed_error_for_missing_memory(tmp_path) -> None:
    store = LocalMemoryStore(tmp_path / "memory.json")

    with pytest.raises(MemoryNotFoundError):
        store.get_memory("mem_missing")
