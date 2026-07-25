"""Agent harness runtime boundary.

This package holds the orchestration layer that ties together:

- typed tool contracts (`plotlot.land_use.models.ToolContract`)
- policy decisions (`plotlot.land_use.policy.ToolPolicy`)
- context brokering
- audit/event emission

The intent is to keep domain evidence modeling in `plotlot.land_use/*` and keep
transport adapters (REST/chat/MCP) thin wrappers over the same harness runtime.
"""

from plotlot.harness.context import ContextBroker, ContextPacket
from plotlot.harness.events import HarnessEvent
from plotlot.harness.full_harness_mcp import FullHarnessMCPAdapter, FullHarnessMCPToolCallRequest
from plotlot.harness.mcp_adapter import MCPAdapter
from plotlot.harness.policy import HarnessPolicyEngine, HarnessPolicyRequest
from plotlot.harness.runtime import HarnessRuntime, ToolCallResult
from plotlot.harness.tool_registry import get_tool_contract, list_tool_contracts

__all__ = [
    "ContextBroker",
    "ContextPacket",
    "HarnessPolicyEngine",
    "HarnessPolicyRequest",
    "HarnessEvent",
    "HarnessRuntime",
    "FullHarnessMCPAdapter",
    "FullHarnessMCPToolCallRequest",
    "MCPAdapter",
    "ToolCallResult",
    "get_tool_contract",
    "list_tool_contracts",
]
