from __future__ import annotations

import pytest

from plotlot.domain.types import ToolContext
from plotlot.harness import FullHarnessMCPAdapter
from plotlot.harness.contracts import (
    PlotLotEvent,
    PlotLotEventSource,
    PlotLotEventStatus,
    PlotLotEventType,
    RunId,
    SourceMode,
    ToolCallId,
)
from plotlot.harness.full_harness_mcp import FullHarnessMCPToolCallRequest
from plotlot.harness.tool_router import HarnessToolCallRequest, HarnessToolCallResult
from plotlot.land_use.models import PolicyDecision


def _context() -> ToolContext:
    return ToolContext(
        workspace_id="ws_fixture",
        actor_user_id="mcp_fixture",
        run_id="run_fixture_mcp",
        live_network_allowed=False,
    )


def test_full_harness_mcp_adapter_lists_shared_tools_and_resources() -> None:
    adapter = FullHarnessMCPAdapter()

    tools = adapter.list_tools()
    resources = adapter.list_resources()

    tool_names = {str(tool["name"]) for tool in tools}
    resource_uris = {resource.uri for resource in resources}
    assert "search_municode" in tool_names
    assert "search_south_florida_gis" in tool_names
    assert "capture_public_listing_comps" in tool_names
    assert "plotlot://harness/tools" in resource_uris
    assert "plotlot://harness/skills" in resource_uris
    assert "plotlot://source-catalog/south-florida-gis" in resource_uris
    assert "plotlot://training/sources" in resource_uris


def test_full_harness_mcp_adapter_calls_router_with_policy_events() -> None:
    adapter = FullHarnessMCPAdapter()

    result = adapter.call_tool(
        FullHarnessMCPToolCallRequest(
            tool_name="search_municode",
            arguments={"jurisdiction": "miami", "query": "parking"},
            context=_context(),
            source_mode=SourceMode.FIXTURE,
        )
    )

    assert result.ok is True
    assert result.status == "completed"
    assert result.source_mode == SourceMode.FIXTURE
    assert result.payload["results"][0]["section_id"] == "municode_miami_parking_fixture"
    assert [event.type for event in result.events] == [
        "tool.requested",
        "tool.policy_checked",
        "tool.started",
        "tool.completed",
    ]


def test_full_harness_mcp_adapter_keeps_approval_policy_boundary() -> None:
    adapter = FullHarnessMCPAdapter()

    result = adapter.call_tool(
        FullHarnessMCPToolCallRequest(
            tool_name="export_report",
            arguments={"report_id": "report_fixture"},
            context=_context(),
            source_mode=SourceMode.FIXTURE,
        )
    )

    assert result.ok is False
    assert result.status == "approval_required"
    assert result.policy_decision.approval_required is True
    assert result.events[-1].type == "tool.approval_required"


def test_full_harness_mcp_adapter_surfaces_failed_tool_calls_with_error_metadata() -> None:
    adapter = FullHarnessMCPAdapter()

    result = adapter.call_tool(
        FullHarnessMCPToolCallRequest(
            tool_name="get_municode_section",
            arguments={"section_id": "municode_missing_fixture"},
            context=_context(),
            source_mode=SourceMode.FIXTURE,
        )
    )

    assert result.ok is False
    assert result.status == "failed"
    assert result.source_mode == SourceMode.FIXTURE
    assert result.payload == {}
    assert result.error is not None
    assert result.error.code == "tool_call_failed"
    assert "municode_missing_fixture" in result.error.message
    assert [event.type for event in result.events] == [
        "tool.requested",
        "tool.policy_checked",
        "tool.started",
        "tool.failed",
    ]


def test_full_harness_mcp_adapter_reads_core_catalog_resources() -> None:
    adapter = FullHarnessMCPAdapter()

    tools = adapter.read_resource("plotlot://harness/tools")
    gis = adapter.read_resource("plotlot://source-catalog/south-florida-gis")
    training = adapter.read_resource("plotlot://training/sources")

    assert "tools" in tools
    assert "sources" in gis
    assert "videos" in training
    assert tools["transport"] == "mcp"
    assert gis["source_mode"] == "fixture"
    assert training["source_mode"] == "fixture"


class _AsyncRouterStub:
    async def call(self, request: HarnessToolCallRequest) -> HarnessToolCallResult:
        return HarnessToolCallResult(
            ok=True,
            tool_call_id=ToolCallId("tool_call_async_stub"),
            tool_name=request.tool_name,
            run_id=RunId(request.context.run_id),
            args=request.args,
            status="completed",
            policy_decision=PolicyDecision(
                allowed=True,
                approval_required=False,
                reason="fixture",
            ),
            payload={"results": [{"section_id": "async_fixture"}]},
            events=[
                PlotLotEvent(
                    event_id="event_async_stub",
                    run_id=RunId(request.context.run_id),
                    sequence=1,
                    type=PlotLotEventType.TOOL_COMPLETED,
                    source=PlotLotEventSource.TOOL,
                    status=PlotLotEventStatus.COMPLETED,
                    payload={"tool_name": request.tool_name},
                )
            ],
            source_mode=request.source_mode,
        )


def _async_request() -> FullHarnessMCPToolCallRequest:
    return FullHarnessMCPToolCallRequest(
        tool_name="search_municode",
        arguments={"jurisdiction": "miami", "query": "parking"},
        context=_context(),
        source_mode=SourceMode.FIXTURE,
    )


@pytest.mark.asyncio
async def test_full_harness_mcp_adapter_awaits_async_router_calls() -> None:
    adapter = FullHarnessMCPAdapter(router=_AsyncRouterStub())

    result = await adapter.call_tool_async(_async_request())

    assert result.ok is True
    assert result.status == "completed"
    assert result.payload["results"][0]["section_id"] == "async_fixture"


def test_full_harness_mcp_adapter_blocks_for_async_router_calls_from_sync_callers() -> None:
    adapter = FullHarnessMCPAdapter(router=_AsyncRouterStub())

    result = adapter.call_tool(_async_request())

    assert result.ok is True
    assert result.status == "completed"
    assert result.payload["results"][0]["section_id"] == "async_fixture"
