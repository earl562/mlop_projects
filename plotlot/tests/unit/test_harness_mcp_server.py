from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from plotlot.harness.contracts import JsonObject, SourceMode
from plotlot.harness.full_harness_mcp import FullHarnessMCPAdapter
from plotlot.mcp.harness_server import (
    HarnessMCPToolInput,
    call_harness_tool_payload,
    call_harness_tool_payload_async,
    list_harness_resources_payload,
    list_harness_tools_payload,
    read_harness_resource_payload,
)


def test_harness_mcp_server_lists_tools_and_resources() -> None:
    tools = list_harness_tools_payload()
    resources = list_harness_resources_payload()

    tool_names = {str(tool["name"]) for tool in tools["tools"]}
    resource_uris = {str(resource["uri"]) for resource in resources["resources"]}
    assert "search_municode" in tool_names
    assert "plotlot://harness/tools" in resource_uris


def test_harness_mcp_server_reads_training_resource() -> None:
    resource = read_harness_resource_payload("plotlot://training/sources")

    assert resource["transport"] == "mcp"
    assert resource["source_mode"] == SourceMode.FIXTURE.value
    assert resource["videos"]


def test_harness_mcp_server_calls_governed_tool() -> None:
    result = call_harness_tool_payload(
        HarnessMCPToolInput(
            tool_name="search_municode",
            arguments={"jurisdiction": "miami", "query": "parking"},
            workspace_id="ws_fixture",
            run_id="run_fixture_mcp_server",
        )
    )

    assert result["ok"] is True
    assert result["status"] == "completed"
    assert result["payload"]["results"][0]["section_id"] == "municode_miami_parking_fixture"
    assert result["events"][1]["type"] == "tool.policy_checked"


def test_harness_mcp_server_preserves_approval_boundary() -> None:
    result = call_harness_tool_payload(
        HarnessMCPToolInput(
            tool_name="export_report",
            arguments={"report_id": "report_fixture"},
            workspace_id="ws_fixture",
            run_id="run_fixture_mcp_server",
        )
    )

    assert result["ok"] is False
    assert result["status"] == "approval_required"
    assert result["policy_decision"]["approval_required"] is True


@pytest.mark.asyncio
async def test_harness_mcp_server_awaits_async_adapter_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = FullHarnessMCPAdapter()

    async def _call_tool_async(request) -> JsonObject:
        return await FullHarnessMCPAdapter().call_tool_async(request)

    monkeypatch.setattr(adapter, "call_tool_async", _call_tool_async)

    result = await call_harness_tool_payload_async(
        HarnessMCPToolInput(
            tool_name="search_municode",
            arguments={"jurisdiction": "miami", "query": "parking"},
            workspace_id="ws_fixture",
            run_id="run_fixture_mcp_server_async",
        ),
        adapter=adapter,
    )

    assert result["ok"] is True
    assert result["status"] == "completed"
    assert result["payload"]["results"][0]["section_id"] == "municode_miami_parking_fixture"


def test_default_plotlot_mcp_script_points_to_harness_server() -> None:
    pyproject_path = Path(__file__).parents[2] / "pyproject.toml"
    scripts = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))["project"]["scripts"]

    assert scripts["plotlot-mcp"] == "plotlot.mcp.harness_server:run"
    assert scripts["plotlot-harness-mcp"] == "plotlot.mcp.harness_server:run"
    assert scripts["plotlot-legacy-mcp"] == "plotlot.mcp.server:run"
