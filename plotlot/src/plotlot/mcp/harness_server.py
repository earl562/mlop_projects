from __future__ import annotations

import fastmcp
from pydantic import Field, TypeAdapter

from plotlot.domain.types import ToolContext
from plotlot.harness.contracts import JsonObject, RunId, SourceMode
from plotlot.harness.contracts.base import HarnessContract
from plotlot.harness.full_harness_mcp import FullHarnessMCPAdapter, FullHarnessMCPToolCallRequest

JSON_OBJECT_ADAPTER = TypeAdapter(JsonObject)

mcp = fastmcp.FastMCP(
    name="plotlot-harness",
    instructions=(
        "PlotLot full harness MCP surface. Route all tool calls through the full-harness "
        "adapter; never bypass policy, evidence, source catalogs, ledgers, or verification."
    ),
    version="0.1.0",
)


class HarnessMCPToolInput(HarnessContract):
    tool_name: str = Field(min_length=1)
    arguments: JsonObject = Field(default_factory=dict)
    workspace_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    actor_user_id: str = Field(default="mcp", min_length=1)
    source_mode: SourceMode = SourceMode.FIXTURE
    risk_budget_cents: int = Field(default=0, ge=0)
    live_network_allowed: bool = False
    approval_id: str | None = None


def list_harness_tools_payload() -> JsonObject:
    return JSON_OBJECT_ADAPTER.validate_python(
        {"transport": "mcp", "tools": FullHarnessMCPAdapter().list_tools()}
    )


def list_harness_resources_payload(run_id: str | None = None) -> JsonObject:
    resources = FullHarnessMCPAdapter().list_resources(RunId(run_id) if run_id else None)
    return JSON_OBJECT_ADAPTER.validate_python(
        {
            "transport": "mcp",
            "resources": [
                JSON_OBJECT_ADAPTER.validate_json(resource.model_dump_json())
                for resource in resources
            ],
        }
    )


def read_harness_resource_payload(uri: str) -> JsonObject:
    return FullHarnessMCPAdapter().read_resource(uri)


async def call_harness_tool_payload_async(
    input_data: HarnessMCPToolInput,
    *,
    adapter: FullHarnessMCPAdapter | None = None,
) -> JsonObject:
    mcp_adapter = adapter or FullHarnessMCPAdapter()
    result = await mcp_adapter.call_tool_async(
        FullHarnessMCPToolCallRequest(
            tool_name=input_data.tool_name,
            arguments=input_data.arguments,
            context=ToolContext(
                workspace_id=input_data.workspace_id,
                actor_user_id=input_data.actor_user_id,
                run_id=input_data.run_id,
                risk_budget_cents=input_data.risk_budget_cents,
                live_network_allowed=input_data.live_network_allowed,
            ),
            source_mode=input_data.source_mode,
            approval_id=input_data.approval_id,
        )
    )
    return JSON_OBJECT_ADAPTER.validate_json(result.model_dump_json())


def call_harness_tool_payload(
    input_data: HarnessMCPToolInput,
    *,
    adapter: FullHarnessMCPAdapter | None = None,
) -> JsonObject:
    mcp_adapter = adapter or FullHarnessMCPAdapter()
    result = mcp_adapter.call_tool(
        FullHarnessMCPToolCallRequest(
            tool_name=input_data.tool_name,
            arguments=input_data.arguments,
            context=ToolContext(
                workspace_id=input_data.workspace_id,
                actor_user_id=input_data.actor_user_id,
                run_id=input_data.run_id,
                risk_budget_cents=input_data.risk_budget_cents,
                live_network_allowed=input_data.live_network_allowed,
            ),
            source_mode=input_data.source_mode,
            approval_id=input_data.approval_id,
        )
    )
    return JSON_OBJECT_ADAPTER.validate_json(result.model_dump_json())


@mcp.tool
def list_harness_tools() -> JsonObject:
    return list_harness_tools_payload()


@mcp.tool
def list_harness_resources(run_id: str | None = None) -> JsonObject:
    return list_harness_resources_payload(run_id)


@mcp.tool
def read_harness_resource(uri: str) -> JsonObject:
    return read_harness_resource_payload(uri)


@mcp.tool
async def call_harness_tool(input_data: HarnessMCPToolInput) -> JsonObject:
    return await call_harness_tool_payload_async(input_data)


def run() -> None:
    mcp.run()
