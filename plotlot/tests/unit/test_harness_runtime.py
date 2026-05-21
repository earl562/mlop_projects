"""Tests for the harness runtime boundary."""

import pytest

from plotlot.harness import HarnessRuntime
from plotlot.land_use import ToolContext


@pytest.mark.asyncio
async def test_harness_runtime_blocks_external_write_without_approval():
    async def handler(args, context):
        return {"ok": True}

    runtime = HarnessRuntime(handlers={"create_spreadsheet": handler})
    context = ToolContext(
        workspace_id="ws_1",
        actor_user_id="user_1",
        run_id="run_1",
        risk_budget_cents=0,
        live_network_allowed=True,
        approved_approval_ids=set(),
    )

    result = await runtime.call_tool(
        tool_name="create_spreadsheet",
        tool_args={"title": "t", "headers": [], "rows": []},
        context=context,
    )

    assert result.status == "pending_approval"
    assert result.decision.approval_required is True
    assert result.decision.approval_id is not None


@pytest.mark.asyncio
async def test_harness_runtime_calls_handler_when_allowed():
    async def handler(args, context):
        return {"ok": True, "args": args, "workspace_id": context.workspace_id}

    runtime = HarnessRuntime(handlers={"geocode_address": handler})
    context = ToolContext(
        workspace_id="ws_1",
        actor_user_id="user_1",
        run_id="run_1",
        risk_budget_cents=0,
        approved_approval_ids=set(),
    )

    result = await runtime.call_tool(
        tool_name="geocode_address", tool_args={"address": "x"}, context=context
    )

    assert result.status == "ok"
    assert result.result is not None
    assert result.result["workspace_id"] == "ws_1"
