"""The governed MCP server must expose the harness faithfully and never bypass it.

The original `plotlot.mcp.server` calls domain functions directly, so an MCP
client got no policy gate, budget, approval, or audit. These tests lock the
replacement to the harness contract.
"""

import os
from unittest.mock import patch

import pytest

from plotlot.harness.default_runtime import get_default_runtime
from plotlot.harness.tool_registry import list_tool_contracts
from plotlot.mcp import harness_server


@pytest.mark.asyncio
async def test_exposes_every_tool_that_has_a_handler():
    server = harness_server.build_server()
    exposed = {t.name for t in await server.list_tools()}
    expected = {c.name for c in list_tool_contracts() if get_default_runtime().has_handler(c.name)}

    assert exposed == expected
    assert "analyze_property" in exposed
    assert "calculate" in exposed


@pytest.mark.asyncio
async def test_tools_carry_their_real_input_schema_and_risk_class():
    server = harness_server.build_server()
    tools = {t.name: t for t in await server.list_tools()}

    calc = tools["calculate"]
    assert "expression" in calc.parameters.get("properties", {})
    # Risk class is surfaced so the client model can reason about consequences.
    assert "read_only" in calc.description

    screen = tools["screen_properties"]
    assert "expensive_read" in screen.description


@pytest.mark.asyncio
async def test_read_only_call_executes_through_the_runtime():
    """calculate is pure and READ_ONLY — proves the full governed path end to end."""
    handler = harness_server._make_handler("calculate")
    out = await handler(expression="519000-450000")

    assert out["status"] == "ok"
    assert out["result"]["result"] == 69000
    assert "read-only" in out["policy_reason"]


@pytest.mark.asyncio
async def test_external_write_is_gated_not_executed():
    """An MCP client must not be able to perform an external write unapproved."""
    handler = harness_server._make_handler("create_document")
    with patch.dict(os.environ, {"PLOTLOT_MCP_LIVE_NETWORK": "1"}, clear=False):
        out = await handler(title="T", content="C")

    assert out["status"] == "pending_approval"
    assert out["approval_id"]
    assert "human must approve" in out["next_step"].lower()


@pytest.mark.asyncio
async def test_zero_budget_blocks_expensive_read():
    handler = harness_server._make_handler("screen_properties")
    with patch.dict(
        os.environ,
        {"PLOTLOT_MCP_BUDGET_CENTS": "0", "PLOTLOT_MCP_LIVE_NETWORK": "0"},
        clear=False,
    ):
        out = await handler(addresses=["x"])

    assert out["status"] in {"blocked", "pending_approval"}


def test_context_reads_governance_from_environment():
    with patch.dict(
        os.environ,
        {
            "PLOTLOT_MCP_WORKSPACE": "ws-test",
            "PLOTLOT_MCP_ACTOR": "actor-test",
            "PLOTLOT_MCP_BUDGET_CENTS": "42",
            "PLOTLOT_MCP_LIVE_NETWORK": "0",
            "PLOTLOT_MCP_APPROVALS": "apr_1, apr_2",
        },
        clear=False,
    ):
        ctx = harness_server._build_context()

    assert ctx.workspace_id == "ws-test"
    assert ctx.actor_user_id == "actor-test"
    assert ctx.risk_budget_cents == 42
    assert ctx.live_network_allowed is False
    assert ctx.approved_approval_ids == {"apr_1", "apr_2"}


def test_bad_budget_value_falls_back_to_default():
    with patch.dict(os.environ, {"PLOTLOT_MCP_BUDGET_CENTS": "not-a-number"}, clear=False):
        assert harness_server._build_context().risk_budget_cents == 1000


def test_handlers_are_bound_per_tool_not_to_the_loop_variable():
    a = harness_server._make_handler("calculate")
    b = harness_server._make_handler("geocode_address")
    assert a is not b
