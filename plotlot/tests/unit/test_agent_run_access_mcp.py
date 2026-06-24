from __future__ import annotations

from uuid import uuid4

import pytest

from plotlot.harness.agent_run_tool import handle_start_agent_run
from plotlot.harness.agent_run_trace_tool import handle_get_agent_run_trace
from plotlot.harness.agent_run_store import clear_agent_run_store
from plotlot.land_use.models import ToolContext
from plotlot.pipeline.lookup_snapshot import build_lookup_snapshot
from plotlot.pipeline.lookup_snapshot_store import clear_lookup_snapshot_store, save_lookup_snapshot
from tests.unit.lookup_snapshot_repository_fixtures import report


@pytest.mark.asyncio
async def test_mcp_agent_run_start_rejects_duplicate_run_ids() -> None:
    clear_agent_run_store()
    clear_lookup_snapshot_store()
    snapshot = build_lookup_snapshot(report(with_density_analysis=True))
    save_lookup_snapshot(snapshot)
    run_id = f"run_{uuid4().hex}"
    context = ToolContext(
        workspace_id="ws_mcp_access",
        actor_user_id="anonymous",
        run_id=run_id,
        project_id="project_mcp_access",
        risk_budget_cents=0,
        live_network_allowed=False,
        approved_approval_ids=set(),
    )

    args = {
        "lookup_snapshot_id": str(snapshot.lookup_snapshot_id),
        "objective": "Persist one replayable run per durable ID.",
    }
    first_response = await handle_start_agent_run(args, context)
    second_response = await handle_start_agent_run(args, context)

    assert first_response["status"] == "success"
    assert second_response["status"] == "conflict"
    assert second_response["message"] == f"Agent run {run_id} already exists"


@pytest.mark.asyncio
async def test_mcp_agent_run_trace_requires_matching_workspace_scope() -> None:
    clear_agent_run_store()
    clear_lookup_snapshot_store()
    snapshot = build_lookup_snapshot(report(with_density_analysis=True))
    save_lookup_snapshot(snapshot)
    run_id = f"run_{uuid4().hex}"
    owner_context = ToolContext(
        workspace_id="ws_mcp_owner",
        actor_user_id="anonymous",
        run_id=run_id,
        project_id="project_mcp_owner",
        risk_budget_cents=0,
        live_network_allowed=False,
        approved_approval_ids=set(),
    )
    reader_context = ToolContext(
        workspace_id="ws_mcp_other",
        actor_user_id="anonymous",
        run_id="run_mcp_scope_reader",
        project_id="project_mcp_other",
        risk_budget_cents=0,
        live_network_allowed=False,
        approved_approval_ids=set(),
    )

    start_response = await handle_start_agent_run(
        {
            "lookup_snapshot_id": str(snapshot.lookup_snapshot_id),
            "objective": "Protect replay traces behind workspace scope.",
        },
        owner_context,
    )
    trace_response = await handle_get_agent_run_trace(
        {"run_id": run_id},
        reader_context,
    )

    assert start_response["status"] == "success"
    assert trace_response["status"] == "not_found"
    assert trace_response["message"] == "Agent run not found"
