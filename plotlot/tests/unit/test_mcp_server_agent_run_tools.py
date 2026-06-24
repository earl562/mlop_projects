from __future__ import annotations

from uuid import uuid4

import pytest

from plotlot.harness.agent_run_store import clear_agent_run_store
from plotlot.mcp.server import get_agent_run_trace, mcp, start_agent_run
from plotlot.pipeline.lookup_snapshot import build_lookup_snapshot
from plotlot.pipeline.lookup_snapshot_store import clear_lookup_snapshot_store, save_lookup_snapshot
from tests.unit.lookup_snapshot_repository_fixtures import report


async def test_fastmcp_agent_run_tools_are_registered() -> None:
    # Given: the standalone MCP server is loaded.
    tools = await mcp.list_tools()

    # When: clients inspect the public FastMCP tool surface.
    names = {tool.name for tool in tools}

    # Then: agent-run creation and replay traces are available outside REST.
    assert "start_agent_run" in names
    assert "get_agent_run_trace" in names


@pytest.mark.asyncio
async def test_fastmcp_start_agent_run_returns_replayable_trace() -> None:
    # Given: a recorded lookup snapshot exists in the evidence kernel.
    clear_agent_run_store()
    clear_lookup_snapshot_store()
    snapshot = build_lookup_snapshot(report(with_density_analysis=True))
    save_lookup_snapshot(snapshot)
    expected_evidence_ids = {
        str(evidence_id) for field in snapshot.fields for evidence_id in field.evidence_ids
    } | {
        str(evidence_id)
        for calculation in snapshot.calculations
        for evidence_id in calculation.input_evidence_ids
    }
    run_id = f"run_{uuid4().hex}"

    # When: a standalone MCP client starts and replays an agent run.
    start_result = await start_agent_run(
        lookup_snapshot_id=str(snapshot.lookup_snapshot_id),
        objective="Find verified by-right development capacity.",
        run_id=run_id,
    )
    trace_result = await get_agent_run_trace(run_id=run_id)

    # Then: both responses use the governed handler shape and recorded evidence.
    assert start_result["status"] == "success"
    assert set(start_result["evidence_ids"]) == expected_evidence_ids
    run = start_result["run"]
    assert run["run_id"] == run_id
    assert run["lookup_snapshot_id"] == str(snapshot.lookup_snapshot_id)
    assert set(run["evidence_ids"]) == expected_evidence_ids
    assert {packet["evidence_id"] for packet in start_result["evidence_packets"]} == (
        expected_evidence_ids
    )

    assert trace_result["status"] == "success"
    trace = trace_result["trace"]
    assert trace["run_id"] == run_id
    assert trace["lookup_snapshot_id"] == str(snapshot.lookup_snapshot_id)
    assert set(trace_result["evidence_ids"]) == expected_evidence_ids
    assert set(trace["evidence_ids"]) == expected_evidence_ids
    assert {packet["evidence_id"] for packet in trace["evidence_packets"]} == expected_evidence_ids
    assert trace_result["evidence_packets"] == trace["evidence_packets"]
    assert all(packet["source_authority"] for packet in trace_result["evidence_packets"])
    assert trace["artifact"]["status"] == "draft"
