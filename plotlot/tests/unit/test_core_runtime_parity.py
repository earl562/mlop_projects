"""Contract tests for core decision-tool parity across runtime adapters."""

from __future__ import annotations

import pytest

from plotlot.harness.default_runtime import build_default_runtime
from plotlot.harness.mcp_adapter import MCPAdapter


CORE_DECISION_TOOLS = frozenset(
    {"analyze_property", "calculate", "analyze_upzoning", "screen_properties"}
)


def test_default_runtime_registers_core_decision_tools():
    runtime = build_default_runtime()

    missing = sorted(name for name in CORE_DECISION_TOOLS if not runtime.has_handler(name))

    assert missing == []


@pytest.mark.asyncio
async def test_rest_and_mcp_discover_all_core_decision_tools(client):
    response = await client.get("/api/v1/tools")
    assert response.status_code == 200

    rest_names = {item["name"] for item in response.json()}
    mcp_names = {item["name"] for item in MCPAdapter(build_default_runtime()).list_tools()}

    assert CORE_DECISION_TOOLS <= rest_names
    assert CORE_DECISION_TOOLS <= mcp_names
    assert rest_names == mcp_names
