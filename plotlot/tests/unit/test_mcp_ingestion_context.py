from __future__ import annotations

from dataclasses import dataclass

from plotlot.ingestion.acp_models import IngestProgress
from plotlot.mcp.ingestion import McpIngestInput, run_ingest_municipality


@dataclass(frozen=True, slots=True)
class _FakeMeta:
    workspace_id: str
    project_id: str
    site_id: str
    analysis_id: str
    analysis_run_id: str
    tool_run_id: str


@dataclass(frozen=True, slots=True)
class _FakeRequestContext:
    meta: _FakeMeta


@dataclass(frozen=True, slots=True)
class _FakeMcpContext:
    request_context: _FakeRequestContext


async def test_mcp_ingestion_passes_request_metadata_to_acp(monkeypatch):
    # Given: an MCP request with workspace/project metadata from the client.
    captured = []
    meta = _FakeMeta(
        workspace_id="workspace_mcp",
        project_id="project_mcp",
        site_id="site_mcp",
        analysis_id="analysis_mcp",
        analysis_run_id="analysis_run_mcp",
        tool_run_id="tool_run_mcp",
    )

    def _fake_context() -> _FakeMcpContext:
        return _FakeMcpContext(request_context=_FakeRequestContext(meta=meta))

    async def _fake_runner(req):
        captured.append(req)
        yield IngestProgress(
            stage="complete",
            message="Done",
            chunks_done=4,
            complete=True,
            evidence_ids=("ev_ing_mcp",),
            quality_flags=("missing_effective_date",),
            source_record_count=1,
        )

    monkeypatch.setattr("plotlot.mcp.ingestion.get_context", _fake_context)

    # When: the MCP ingestion helper runs.
    result = await run_ingest_municipality(
        McpIngestInput(municipality="Fremont", state="CA", county="Alameda"),
        runner=_fake_runner,
    )

    # Then: ACP receives the metadata needed to persist source-record evidence.
    assert result["success"] is True
    assert result["chunks_stored"] == 4
    assert result["evidence_ids"] == ["ev_ing_mcp"]
    assert result["quality_flags"] == ["missing_effective_date"]
    assert result["source_record_count"] == 1
    assert result["progress"][-1]["quality_flags"] == ["missing_effective_date"]
    request = captured[0]
    assert request.workspace_id == "workspace_mcp"
    assert request.project_id == "project_mcp"
    assert request.site_id == "site_mcp"
    assert request.analysis_id == "analysis_mcp"
    assert request.analysis_run_id == "analysis_run_mcp"
    assert request.tool_run_id == "tool_run_mcp"
