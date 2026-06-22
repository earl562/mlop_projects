"""Minimal MCP adapter over the harness runtime.

This is not a full MCP server process; it is an adapter that provides the two
core semantics needed by MCP clients:

- tools/list
- tools/call

It ensures MCP never bypasses PlotLot policy.
"""

from __future__ import annotations

from typing import Any

from plotlot.harness.events import HarnessEvent
from plotlot.harness.runtime import HarnessRuntime, ToolCallResult
from plotlot.harness.tool_registry import list_tool_contracts
from plotlot.land_use.models import ToolContext


class MCPAdapter:
    def __init__(self, runtime: HarnessRuntime) -> None:
        self._runtime = runtime

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            tool.model_dump()
            for tool in list_tool_contracts()
            if self._runtime.has_handler(tool.name)
        ]

    async def call_tool(
        self,
        *,
        name: str,
        arguments: dict[str, Any],
        context: ToolContext,
        approval_id: str | None = None,
        events: list[HarnessEvent] | None = None,
    ) -> ToolCallResult:
        return await self._runtime.call_tool(
            tool_name=name,
            tool_args=arguments,
            context=context,
            approval_id=approval_id,
            events=events,
        )
