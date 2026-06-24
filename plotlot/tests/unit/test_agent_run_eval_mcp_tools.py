from __future__ import annotations

from uuid import uuid4

import pytest

from plotlot.harness.agent_run_store import clear_agent_run_store
from plotlot.mcp.server import (
    evaluate_agent_run,
    get_agent_run_improvement_summary,
    get_latest_agent_run_eval,
    mcp,
    start_agent_run,
)
from plotlot.pipeline.lookup_snapshot import build_lookup_snapshot
from plotlot.pipeline.lookup_snapshot_store import clear_lookup_snapshot_store, save_lookup_snapshot
from tests.unit.lookup_snapshot_repository_fixtures import report


@pytest.mark.asyncio
async def test_mcp_agent_run_eval_tools_score_and_return_improvement_summary(client) -> None:
    # Given: an MCP-started agent run is backed by a recorded lookup snapshot.
    clear_agent_run_store()
    clear_lookup_snapshot_store()
    snapshot = build_lookup_snapshot(report(with_density_analysis=True))
    save_lookup_snapshot(snapshot)
    run_id = f"run_{uuid4().hex}"
    context = {
        "workspace_id": "ws_mcp_eval",
        "actor_user_id": "anonymous",
        "run_id": run_id,
        "project_id": "project_mcp_eval",
        "risk_budget_cents": 0,
        "live_network_allowed": False,
        "approved_approval_ids": [],
    }
    await client.post(
        "/api/v1/mcp/tools/call",
        json={
            "name": "start_agent_run",
            "arguments": {
                "lookup_snapshot_id": str(snapshot.lookup_snapshot_id),
                "objective": "Evaluate verified by-right development capacity.",
            },
            "context": context,
        },
    )

    # When: the REST MCP adapter scores the run and reads the eval checkpoints.
    tools_response = await client.get("/api/v1/mcp/tools/list")
    eval_response = await client.post(
        "/api/v1/mcp/tools/call",
        json={
            "name": "evaluate_agent_run",
            "arguments": {"run_id": run_id},
            "context": context | {"run_id": "run_mcp_eval_reader"},
        },
    )
    latest_response = await client.post(
        "/api/v1/mcp/tools/call",
        json={
            "name": "get_latest_agent_run_eval",
            "arguments": {"run_id": run_id},
            "context": context | {"run_id": "run_mcp_eval_latest_reader"},
        },
    )
    improvement_response = await client.post(
        "/api/v1/mcp/tools/call",
        json={
            "name": "get_agent_run_improvement_summary",
            "arguments": {"run_id": run_id},
            "context": context | {"run_id": "run_mcp_eval_improvement_reader"},
        },
    )

    # Then: the tools are listed and return the same persisted eval spine.
    assert tools_response.status_code == 200
    tool_names = {tool["name"] for tool in tools_response.json()}
    assert {
        "evaluate_agent_run",
        "get_latest_agent_run_eval",
        "get_agent_run_improvement_summary",
    }.issubset(tool_names)
    assert eval_response.status_code == 200
    eval_result = eval_response.json()["result"]
    assert eval_result["status"] == "success"
    assert eval_result["eval"]["status"] == "passed"
    assert eval_result["eval"]["run_id"] == run_id
    assert eval_result["eval"]["metrics"]["source_quality_traceability"] == 1.0
    assert eval_result["eval"]["metrics"]["calculation_lineage_traceability"] == 1.0

    assert latest_response.status_code == 200
    latest_result = latest_response.json()["result"]
    assert latest_result["status"] == "success"
    assert latest_result["eval"]["eval_run_id"] == eval_result["eval"]["eval_run_id"]
    assert latest_result["eval"]["evidence_metrics"]["source_quality_traceability"] == 1.0
    assert latest_result["eval"]["trajectory_metrics"]["calculation_lineage_traceability"] == 1.0

    assert improvement_response.status_code == 200
    improvement_result = improvement_response.json()["result"]
    assert improvement_result["status"] == "success"
    assert improvement_result["improvement"]["current"]["run_id"] == run_id
    assert improvement_result["improvement"]["release_blocked"] is False
    improvement_log = improvement_result["improvement"]["improvement_log"]
    assert isinstance(improvement_log, list)
    if improvement_log:
        assert improvement_log[0]["changed_rule"].startswith("eval_metric:")


@pytest.mark.asyncio
async def test_fastmcp_agent_run_eval_tools_are_registered_and_callable() -> None:
    # Given: a standalone FastMCP run exists from recorded lookup evidence.
    clear_agent_run_store()
    clear_lookup_snapshot_store()
    snapshot = build_lookup_snapshot(report(with_density_analysis=True))
    save_lookup_snapshot(snapshot)
    run_id = f"run_{uuid4().hex}"
    await start_agent_run(
        lookup_snapshot_id=str(snapshot.lookup_snapshot_id),
        objective="Score a standalone replayable run.",
        run_id=run_id,
    )

    # When: FastMCP clients list and call the eval tools.
    tools = await mcp.list_tools()
    eval_result = await evaluate_agent_run(run_id=run_id)
    latest_result = await get_latest_agent_run_eval(run_id=run_id)
    improvement_result = await get_agent_run_improvement_summary(run_id=run_id)

    # Then: the standalone surface exposes and returns eval/improvement records.
    names = {tool.name for tool in tools}
    assert {
        "evaluate_agent_run",
        "get_latest_agent_run_eval",
        "get_agent_run_improvement_summary",
    }.issubset(names)
    assert eval_result["status"] == "success"
    assert eval_result["eval"]["status"] == "passed"
    assert latest_result["eval"]["eval_run_id"] == eval_result["eval"]["eval_run_id"]
    assert improvement_result["improvement"]["release_blocked"] is False
