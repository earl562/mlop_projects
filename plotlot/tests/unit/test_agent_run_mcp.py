from __future__ import annotations

from uuid import uuid4

import pytest

from plotlot.harness.agent_run_store import clear_agent_run_store
from plotlot.pipeline.lookup_snapshot import build_lookup_snapshot
from plotlot.pipeline.lookup_snapshot_store import clear_lookup_snapshot_store, save_lookup_snapshot
from tests.unit.lookup_snapshot_repository_fixtures import report


@pytest.mark.asyncio
async def test_mcp_start_agent_run_from_recorded_lookup_snapshot(client) -> None:
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

    # And: the MCP tool list exposes the agent-run entrypoint.
    tools_response = await client.get("/api/v1/mcp/tools/list")
    assert tools_response.status_code == 200
    tools = {tool["name"]: tool for tool in tools_response.json()}
    tool_names = set(tools)
    assert "start_agent_run" in tool_names
    assert "evidence_ids" in tools["start_agent_run"]["output_schema"]["properties"]
    assert "evidence_packets" in tools["start_agent_run"]["output_schema"]["properties"]

    # When: a client starts the agent run through the MCP tool surface.
    response = await client.post(
        "/api/v1/mcp/tools/call",
        json={
            "name": "start_agent_run",
            "arguments": {
                "lookup_snapshot_id": str(snapshot.lookup_snapshot_id),
                "objective": "Find verified by-right development capacity.",
            },
            "context": {
                "workspace_id": "ws_mcp_agent",
                "actor_user_id": "anonymous",
                "run_id": run_id,
                "project_id": "project_mcp_agent",
                "risk_budget_cents": 0,
                "live_network_allowed": False,
                "approved_approval_ids": [],
            },
        },
    )

    # Then: the MCP response is replayable and evidence-backed.
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert set(body["evidence_ids"]) == expected_evidence_ids
    result = body["result"]
    assert result["status"] == "success"
    assert set(result["evidence_ids"]) == expected_evidence_ids
    run = result["run"]
    assert run["run_id"] == run_id
    assert run["lookup_snapshot_id"] == str(snapshot.lookup_snapshot_id)
    assert run["status"] == "requires_review"
    assert run["ready_for_synthesis"] is False
    assert set(run["evidence_ids"]) == expected_evidence_ids
    assert {assignment["lane"] for assignment in run["assignments"]} == {
        "parcel_analyst",
        "zoning_code_analyst",
        "gis_layer_analyst",
        "entitlement_risk_analyst",
        "underwriting_analyst",
        "evidence_reviewer",
        "report_document_analyst",
        "lead_developer_consultant",
    }
    assert run["trace_steps"][0]["kind"] == "run_started"
    assert run["trace_steps"][-1]["kind"] == "run_completed"

    stored_response = await client.get(f"/api/v1/agent-runs/{run_id}?workspace_id=ws_mcp_agent")
    assert stored_response.status_code == 200
    stored_run = stored_response.json()
    assert stored_run["run_id"] == run["run_id"]
    assert stored_run["lookup_snapshot_id"] == run["lookup_snapshot_id"]
    assert stored_run["trace_steps"] == run["trace_steps"]


@pytest.mark.asyncio
async def test_mcp_get_agent_run_trace_returns_replay_package(client) -> None:
    # Given: an MCP-started run has recorded evidence, artifacts, and an eval checkpoint.
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
    context = {
        "workspace_id": "ws_mcp_trace",
        "actor_user_id": "anonymous",
        "run_id": run_id,
        "project_id": "project_mcp_trace",
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
                "objective": "Replay verified by-right development capacity.",
            },
            "context": context,
        },
    )
    eval_response = await client.post(
        f"/api/v1/agent-runs/{run_id}/evals?workspace_id=ws_mcp_trace"
    )

    # And: the MCP tool list exposes the replay trace reader.
    tools_response = await client.get("/api/v1/mcp/tools/list")
    assert tools_response.status_code == 200
    tools = {tool["name"]: tool for tool in tools_response.json()}
    tool_names = set(tools)
    assert "get_agent_run_trace" in tool_names
    assert "evidence_ids" in tools["get_agent_run_trace"]["output_schema"]["properties"]
    assert "evidence_packets" in tools["get_agent_run_trace"]["output_schema"]["properties"]

    # When: a client requests the replay package through the MCP tool surface.
    response = await client.post(
        "/api/v1/mcp/tools/call",
        json={
            "name": "get_agent_run_trace",
            "arguments": {"run_id": run_id},
            "context": context | {"run_id": "run_mcp_trace_reader"},
        },
    )

    # Then: MCP returns the same replay-ready trace package shape as REST.
    assert eval_response.status_code == 200
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert set(body["evidence_ids"]) == expected_evidence_ids
    result = body["result"]
    assert result["status"] == "success"
    assert set(result["evidence_ids"]) == expected_evidence_ids
    trace = result["trace"]
    assert trace["run_id"] == run_id
    assert trace["lookup_snapshot_id"] == str(snapshot.lookup_snapshot_id)
    assert trace["replay_ready"] is True
    assert trace["missing_replay_requirements"] == []
    assert set(trace["evidence_ids"]) == expected_evidence_ids
    assert {packet["evidence_id"] for packet in trace["evidence_packets"]} == expected_evidence_ids
    assert result["evidence_packets"] == trace["evidence_packets"]
    assert {packet["source_authority"] for packet in trace["evidence_packets"]} == {
        "official_assessor",
        "official_zoning_ordinance",
    }
    assert all(packet["quality_score"] == 0.0 for packet in trace["evidence_packets"])
    assert all(
        "missing_source_url" in packet["quality_flags"] for packet in trace["evidence_packets"]
    )
    assert all(
        "missing_effective_date" in packet["quality_flags"] for packet in trace["evidence_packets"]
    )
    assert trace["artifact"]["status"] == "draft"
    assert trace["latest_eval"]["status"] == "passed"
    assert "trace_replayability" in trace["latest_eval"]["metric_keys"]
    assert trace["improvement"]["release_blocked"] is False
