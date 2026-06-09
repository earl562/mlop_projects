"""Phase 8: External protocols — MCP server + Agent Protocol server.

Per MCP Tool Descriptions (Paper 19): tool contracts as the interface.
Per Deep Agents v0.5: Agent Protocol for async sub-agent serving.
Per ANP (Paper 71): external agent integration.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MCPTool:
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)

    def to_mcp(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "inputSchema": self.input_schema}


class MCPServer:
    """Serve harness tools as MCP (Model Context Protocol) endpoints."""

    def __init__(self, tools: list[dict[str, Any]], execute_tool: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]):
        self._tools: dict[str, dict[str, Any]] = {t.get("name", ""): t for t in tools}
        self._execute = execute_tool
        self._mcp_tools: list[MCPTool] = [MCPTool(name=t.get("name", ""), description=t.get("description", ""), input_schema=t.get("parameters") or t.get("input_schema") or {}) for t in tools]

    def list_tools(self) -> list[dict[str, Any]]:
        return [t.to_mcp() for t in self._mcp_tools]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name not in self._tools:
            return {"content": [{"type": "text", "text": f"Unknown tool: {name}"}], "isError": True}
        result = await self._execute(name, arguments)
        return {"content": [{"type": "text", "text": json.dumps(result)}]}

    async def handle_request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        try:
            if method == "initialize":
                return {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "plotlot-harness", "version": "2.0.0"}}
            elif method == "tools/list":
                return {"tools": self.list_tools()}
            elif method == "tools/call":
                return await self.call_tool(params.get("name", ""), params.get("arguments", {}))
            else:
                return {"error": {"code": -32601, "message": f"Method not found: {method}"}}
        except Exception as e:
            return {"error": {"code": -32000, "message": str(e)}}


class AgentProtocolServer:
    """Serve agents via the Agent Protocol for async sub-agent execution."""

    def __init__(self, call_model: Callable[[list[dict[str, Any]]], Awaitable[str]]):
        self._call_model = call_model
        self._threads: dict[str, list[dict[str, Any]]] = {}

    def create_thread(self) -> str:
        tid = str(uuid.uuid4())[:8]
        self._threads[tid] = []
        return tid

    async def run_thread(self, thread_id: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
        if thread_id not in self._threads:
            self._threads[thread_id] = []
        self._threads[thread_id].extend(messages)
        response = await self._call_model(self._threads[thread_id])
        self._threads[thread_id].append({"role": "assistant", "content": response})
        return {"thread_id": thread_id, "response": response, "message_count": len(self._threads[thread_id])}

    def get_thread(self, thread_id: str) -> list[dict[str, Any]]:
        return self._threads.get(thread_id, [])
