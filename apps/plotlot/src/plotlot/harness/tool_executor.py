"""Governed tool execution boundary."""

from __future__ import annotations

from collections.abc import Callable, Awaitable
from typing import Any

from plotlot.harness.contracts import ToolResult
from plotlot.harness.governance import GovernanceMiddleware

ToolHandler = Callable[..., Awaitable[ToolResult]]


class ToolExecutor:
    """Executes registered tool handlers after governance checks."""

    def __init__(self, governance: GovernanceMiddleware | None = None) -> None:
        self.governance = governance or GovernanceMiddleware()
        self._tools: dict[str, ToolHandler] = {}

    def register(self, name: str, handler: ToolHandler) -> None:
        self._tools[name] = handler

    async def invoke(self, name: str, **kwargs: Any) -> ToolResult:
        decision = self.governance.decide(name)
        if not decision.allowed:
            return ToolResult(
                status=decision.status.value,
                data={"message": decision.reason},
                confidence="high",
            )

        handler = self._tools.get(name)
        if handler is None:
            return ToolResult(
                status="error",
                data={"message": f"Tool '{name}' is not registered."},
                confidence="high",
            )

        return await handler(**kwargs)
