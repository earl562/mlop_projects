from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from plotlot.core.types import (
    ConstraintResult,
    DensityAnalysis,
    PropertyRecord,
    Setbacks,
    SourceRef,
    ZoningReport,
)
from plotlot.harness.default_runtime import get_default_runtime
from plotlot.harness.mcp_adapter import MCPAdapter
from plotlot.land_use.models import ToolContext
from plotlot.mcp.server import mcp, run_lookup_golden_eval_batch
from plotlot.pipeline.lookup_snapshot import build_lookup_snapshot
from plotlot.pipeline.lookup_snapshot_json import JsonValue
from plotlot.pipeline.lookup_snapshot_store import clear_lookup_snapshot_store, save_lookup_snapshot


@pytest.mark.asyncio
async def test_lookup_golden_eval_batch_tool_matches_http_mcp_and_fastmcp(
    client,
) -> None:
    # Given: a recorded lookup snapshot has a matching canonical golden fixture.
    clear_lookup_snapshot_store()
    snapshot = build_lookup_snapshot(_miami_gardens_report())
    save_lookup_snapshot(snapshot)
    arguments = {
        "suite": "lookup_correctness",
        "snapshots": [
            {
                "snapshot_id": str(snapshot.lookup_snapshot_id),
                "address": "171 NE 209th Ter, Miami, FL 33179",
            }
        ],
        "use_latest_baseline": False,
    }

    # When: each public tool surface runs the canonical golden eval batch.
    with patch(
        "plotlot.pipeline.lookup_snapshot_golden_eval_runner._persist_lookup_snapshot_eval_batch",
        new_callable=AsyncMock,
    ) as persist_batch:
        tools_response = await client.get("/api/v1/mcp/tools/list")
        http_response = await client.post(
            "/api/v1/mcp/tools/call",
            json={
                "name": "run_lookup_golden_eval_batch",
                "arguments": arguments,
                "context": _tool_context_json("run_http_lookup_golden_eval"),
            },
        )
        adapter_result = await MCPAdapter(get_default_runtime()).call_tool(
            name="run_lookup_golden_eval_batch",
            arguments=arguments,
            context=_tool_context("run_adapter_lookup_golden_eval"),
        )
        fastmcp_result = await run_lookup_golden_eval_batch(
            snapshot_id=str(snapshot.lookup_snapshot_id),
            address="171 NE 209th Ter, Miami, FL 33179",
            suite="lookup_correctness",
            use_latest_baseline=False,
        )
        fastmcp_tools = await mcp.list_tools()

    # Then: the tool is registered everywhere and returns the deterministic eval payload.
    assert tools_response.status_code == 200
    assert "run_lookup_golden_eval_batch" in {tool["name"] for tool in tools_response.json()}
    assert "run_lookup_golden_eval_batch" in {tool.name for tool in fastmcp_tools}

    assert http_response.status_code == 200
    http_body = http_response.json()
    assert http_body["status"] == "ok"
    assert http_body["result"]["status"] == "passed"
    assert http_body["result"]["metrics"]["pass_rate"] == 1.0
    assert http_body["result"]["case_results"][0]["case_id"].startswith("golden-data-171-ne-209th")

    assert adapter_result.status == "ok"
    assert adapter_result.result is not None
    assert adapter_result.result["status"] == "passed"
    assert adapter_result.result["metrics"]["pass_rate"] == 1.0

    assert fastmcp_result["status"] == "passed"
    assert fastmcp_result["metrics"]["pass_rate"] == 1.0
    persist_batch.assert_awaited()
    assert persist_batch.await_count == 3


@pytest.mark.asyncio
async def test_lookup_golden_eval_batch_tool_blocks_without_matching_fixture() -> None:
    # Given: a recorded snapshot exists but the requested address is not a golden case.
    clear_lookup_snapshot_store()
    snapshot = build_lookup_snapshot(_miami_gardens_report())
    save_lookup_snapshot(snapshot)

    # When: the agent asks the tool to run against unsupported golden evidence.
    with patch(
        "plotlot.pipeline.lookup_snapshot_golden_eval_runner._persist_lookup_snapshot_eval_batch",
        new_callable=AsyncMock,
    ) as persist_batch:
        result = await MCPAdapter(get_default_runtime()).call_tool(
            name="run_lookup_golden_eval_batch",
            arguments={
                "suite": "lookup_correctness",
                "snapshots": [
                    {
                        "snapshot_id": str(snapshot.lookup_snapshot_id),
                        "address": "1 Missing Golden Case Way, Miami, FL 33179",
                    }
                ],
                "use_latest_baseline": False,
            },
            context=_tool_context("run_missing_lookup_golden_eval"),
        )

    # Then: the missing fixture blocks eval creation instead of producing synthetic truth.
    assert result.status == "blocked"
    assert result.result is not None
    assert result.result["status"] == "blocked"
    assert result.result["message"] == (
        "Lookup golden case not found: 1 Missing Golden Case Way, Miami, FL 33179"
    )
    persist_batch.assert_not_awaited()


@pytest.mark.asyncio
async def test_lookup_golden_eval_batch_tool_blocks_without_recorded_snapshot() -> None:
    # Given: no lookup snapshot is recorded for a canonical golden fixture.
    clear_lookup_snapshot_store()

    # When: the agent asks the tool to score a missing snapshot.
    with patch(
        "plotlot.pipeline.lookup_snapshot_golden_eval_runner._persist_lookup_snapshot_eval_batch",
        new_callable=AsyncMock,
    ) as persist_batch:
        result = await MCPAdapter(get_default_runtime()).call_tool(
            name="run_lookup_golden_eval_batch",
            arguments={
                "suite": "lookup_correctness",
                "snapshots": [
                    {
                        "snapshot_id": "missing-lookup-snapshot",
                        "address": "171 NE 209th Ter, Miami, FL 33179",
                    }
                ],
                "use_latest_baseline": False,
            },
            context=_tool_context("run_missing_lookup_snapshot_eval"),
        )

    # Then: the tool blocks before creating a synthetic eval result.
    assert result.status == "blocked"
    assert result.result is not None
    assert result.result["status"] == "blocked"
    assert result.result["message"] == "Lookup snapshot not found: missing-lookup-snapshot"
    persist_batch.assert_not_awaited()


def _tool_context(run_id: str) -> ToolContext:
    return ToolContext(
        workspace_id="ws_lookup_golden_eval",
        actor_user_id="anonymous",
        run_id=run_id,
        project_id="project_lookup_golden_eval",
        risk_budget_cents=0,
    )


def _tool_context_json(run_id: str) -> dict[str, JsonValue]:
    return {
        "workspace_id": "ws_lookup_golden_eval",
        "actor_user_id": "anonymous",
        "run_id": run_id,
        "project_id": "project_lookup_golden_eval",
        "risk_budget_cents": 0,
        "live_network_allowed": False,
        "approved_approval_ids": [],
    }


def _miami_gardens_report() -> ZoningReport:
    return ZoningReport(
        address="171 NE 209th Ter, Miami, FL 33179",
        formatted_address="171 NE 209th Ter, Miami, FL 33179",
        municipality="Miami Gardens",
        county="Miami-Dade",
        zoning_district="R-1",
        max_height="35 ft",
        setbacks=Setbacks(front="25 ft", side="7.5 ft", rear="25 ft"),
        parking_requirements="2 spaces per unit",
        property_record=PropertyRecord(
            folio="3421130010010",
            address="171 NE 209TH TER",
            municipality="Miami Gardens",
            county="Miami-Dade",
            zoning_code="R-1",
            lot_size_sqft=7500.0,
        ),
        source_refs=[
            SourceRef(
                section="Sec. 34-342",
                section_title="Single-family residential district",
                chunk_text_preview="R-1 district permits one dwelling unit with 35-foot height limits.",
                score=0.95,
            )
        ],
        density_analysis=DensityAnalysis(
            max_units=1,
            governing_constraint="density",
            constraints=[
                ConstraintResult(
                    name="density",
                    max_units=1,
                    raw_value=1.0,
                    formula="R-1 single-family district permits one unit",
                    is_governing=True,
                )
            ],
            lot_size_sqft=7500.0,
            confidence="high",
        ),
        confidence="high",
    )
