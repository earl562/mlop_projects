from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from plotlot.ingestion.acp_models import IngestProgress


class FakeSession:
    def __init__(self) -> None:
        self.added = []
        self.committed = False
        self.rolled_back = False

    async def get(self, model, key):  # noqa: ANN001
        return None

    def add(self, obj):  # noqa: ANN001
        self.added.append(obj)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_ingest_municipality_tool_passes_workspace_context_to_acp_runtime():
    from plotlot.harness.ingestion_tool import handle_ingest_municipality
    from plotlot.land_use.models import ToolContext

    captured = []

    async def _fake_run(req):
        captured.append(req)
        yield IngestProgress(stage="complete", message="Done", chunks_done=7, complete=True)

    # Given: a governed tool context with workspace/project/run lineage.
    context = ToolContext(
        workspace_id="ws_tool_ingest",
        actor_user_id="anonymous",
        run_id="run_tool_ingest",
        tool_run_id="tool_run_ingest",
        project_id="project_tool_ingest",
        site_id="site_tool_ingest",
        analysis_id="analysis_tool_ingest",
        analysis_run_id="analysis_run_tool_ingest",
        risk_budget_cents=100,
        live_network_allowed=True,
    )

    with patch("plotlot.harness.ingestion_tool.run_on_demand_ingestion", new=_fake_run):
        # When: the runtime handler executes ingestion.
        result = await handle_ingest_municipality(
            {"municipality": "Fremont", "state": "CA", "county": "Alameda"},
            context,
        )

    # Then: ACP receives the context required for evidence-kernel source rows.
    assert result["status"] == "success"
    assert result["chunks_stored"] == 7
    assert result["evidence_ids"] == []
    request = captured[0]
    assert request.workspace_id == "ws_tool_ingest"
    assert request.project_id == "project_tool_ingest"
    assert request.site_id == "site_tool_ingest"
    assert request.analysis_id == "analysis_tool_ingest"
    assert request.analysis_run_id == "analysis_run_tool_ingest"
    assert request.tool_run_id == "tool_run_ingest"


@pytest.mark.asyncio
async def test_ingest_municipality_tool_returns_ingestion_evidence_ids():
    from plotlot.harness.ingestion_tool import handle_ingest_municipality
    from plotlot.land_use.models import ToolContext

    async def _fake_run(req):  # noqa: ARG001
        yield IngestProgress(
            stage="complete",
            message="Done",
            chunks_done=2,
            complete=True,
            evidence_ids=("ev_ing_alpha", "ev_ing_beta"),
            quality_flags=("missing_effective_date",),
            source_record_count=1,
        )

    # Given: ACP returns source evidence IDs from a successful ingestion run.
    context = ToolContext(
        workspace_id="ws_tool_ingest",
        actor_user_id="anonymous",
        run_id="run_tool_ingest",
        tool_run_id="tool_run_ingest",
        project_id="project_tool_ingest",
        risk_budget_cents=100,
        live_network_allowed=True,
    )

    with patch("plotlot.harness.ingestion_tool.run_on_demand_ingestion", new=_fake_run):
        # When: the governed ingestion tool handles the ACP progress stream.
        result = await handle_ingest_municipality(
            {"municipality": "Fremont", "state": "CA"},
            context,
        )

    # Then: downstream reports/traces can cite the actual ingestion evidence rows.
    assert result["status"] == "success"
    assert result["evidence_ids"] == ["ev_ing_alpha", "ev_ing_beta"]
    assert result["quality_flags"] == ["missing_effective_date"]
    assert result["source_record_count"] == 1
    assert result["progress"][-1]["evidence_ids"] == ["ev_ing_alpha", "ev_ing_beta"]
    assert result["progress"][-1]["quality_flags"] == ["missing_effective_date"]


@pytest.mark.asyncio
async def test_tools_call_ingest_municipality_runs_through_rest_surface(client):
    fake_session = FakeSession()
    captured = []

    async def _fake_run(req):
        captured.append(req)
        yield IngestProgress(stage="resolving", message="Finding source")
        yield IngestProgress(
            stage="complete",
            message="Done",
            chunks_done=3,
            complete=True,
            quality_flags=("missing_effective_date",),
            source_record_count=1,
        )

    with (
        patch("plotlot.api.tools.get_session", new=AsyncMock(return_value=fake_session)),
        patch("plotlot.harness.ingestion_tool.run_on_demand_ingestion", new=_fake_run),
    ):
        # Given: a REST tool call with live-network permission and enough risk budget.
        response = await client.post(
            "/api/v1/tools/call",
            json={
                "tool_name": "ingest_municipality",
                "arguments": {"municipality": "Fremont", "state": "CA", "county": "Alameda"},
                "workspace_id": "ws_rest_ingest",
                "project_id": "project_rest_ingest",
                "site_id": "site_rest_ingest",
                "analysis_id": "analysis_rest_ingest",
                "analysis_run_id": "analysis_run_rest_ingest",
                "risk_budget_cents": 100,
                "live_network_allowed": True,
                "run_id": "run_rest_ingest",
            },
        )

    # When/Then: the API surface returns the governed ingestion result.
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["result"]["status"] == "success"
    assert payload["result"]["chunks_stored"] == 3
    assert payload["result"]["evidence_ids"] == []
    assert payload["result"]["quality_flags"] == ["missing_effective_date"]
    assert payload["result"]["source_record_count"] == 1
    assert payload["result"]["progress"][0]["stage"] == "resolving"
    request = captured[0]
    assert request.workspace_id == "ws_rest_ingest"
    assert request.project_id == "project_rest_ingest"
    assert request.site_id == "site_rest_ingest"
    assert request.analysis_id == "analysis_rest_ingest"
    assert request.analysis_run_id == "analysis_run_rest_ingest"
    assert request.tool_run_id == payload["tool_run_id"]


@pytest.mark.asyncio
async def test_list_tools_includes_governed_ingestion_contract(client):
    # Given: the REST tool catalog endpoint.
    response = await client.get("/api/v1/tools")

    # When/Then: ingestion is discoverable with live-source governance metadata.
    assert response.status_code == 200
    tools = {tool["name"]: tool for tool in response.json()}
    contract = tools["ingest_municipality"]
    assert contract["risk_class"] == "expensive_read"
    assert contract["budget_cents"] == 75
    assert "municipality" in contract["input_schema"]["required"]
    assert "state" in contract["input_schema"]["required"]
    assert "evidence_ids" in contract["output_schema"]["properties"]
    assert "quality_flags" in contract["output_schema"]["properties"]
    assert "source_record_count" in contract["output_schema"]["properties"]
