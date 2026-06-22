"""Harness runtime boundary.

This is intentionally minimal: it exists to ensure every tool call is routed
through policy authorization and produces a structured result that transport
adapters (REST/chat/MCP) can render.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast
import uuid

from plotlot.harness.events import EventKind, HarnessEvent
from plotlot.harness.policy import HarnessPolicyEngine
from plotlot.harness.tool_registry import tool_exists
from plotlot.land_use.models import PolicyDecision, ToolContext

ToolHandler = Callable[[dict[str, Any], ToolContext], Awaitable[dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class ToolCallResult:
    tool_name: str
    decision: PolicyDecision
    status: str
    result: dict[str, Any] | None = None
    message: str | None = None


class HarnessRuntime:
    """Orchestrates governed tool execution."""

    def __init__(
        self,
        *,
        policy: HarnessPolicyEngine | None = None,
        handlers: dict[str, ToolHandler] | None = None,
        event_sink: Callable[[HarnessEvent], None] | None = None,
    ) -> None:
        self._policy = policy or HarnessPolicyEngine()
        self._handlers = handlers or {}
        self._event_sink = event_sink

    def _emit(
        self,
        *,
        kind: str,
        payload: dict[str, Any],
        buffer: list[HarnessEvent] | None,
    ) -> None:
        event = HarnessEvent(kind=cast(EventKind, kind), id=str(uuid.uuid4()), payload=payload)
        if buffer is not None:
            buffer.append(event)
        if self._event_sink is not None:
            try:
                self._event_sink(event)
            except Exception:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK
                # Never let event emission break tool execution.
                return

    def register(self, tool_name: str, handler: ToolHandler) -> None:
        self._handlers[tool_name] = handler

    def has_handler(self, tool_name: str) -> bool:
        return tool_name in self._handlers

    async def call_tool(
        self,
        *,
        tool_name: str,
        tool_args: dict[str, Any],
        context: ToolContext,
        approval_id: str | None = None,
        events: list[HarnessEvent] | None = None,
    ) -> ToolCallResult:
        arg_keys = sorted(tool_args.keys())
        self._emit(
            kind="tool_call",
            payload={"tool_name": tool_name, "arg_keys": arg_keys, "run_id": context.run_id},
            buffer=events,
        )
        if not tool_exists(tool_name):
            result = ToolCallResult(
                tool_name=tool_name,
                decision=PolicyDecision(allowed=False, reason="unknown tool"),
                status="unknown_tool",
                message=f"Unknown tool: {tool_name}",
            )
            self._emit(
                kind="tool_result",
                payload={
                    "tool_name": tool_name,
                    "status": result.status,
                    "message": result.message,
                },
                buffer=events,
            )
            return result

        handler = self._handlers.get(tool_name)
        if handler is None:
            result = ToolCallResult(
                tool_name=tool_name,
                decision=PolicyDecision(
                    allowed=False, reason="tool is not implemented in this runtime"
                ),
                status="unavailable",
                message=f"No handler registered for {tool_name}",
            )
            self._emit(
                kind="tool_result",
                payload={
                    "tool_name": tool_name,
                    "status": result.status,
                    "message": result.message,
                },
                buffer=events,
            )
            return result

        decision = self._policy.authorize(
            tool_name=tool_name, context=context, approval_id=approval_id
        )
        if decision.approval_required:
            result = ToolCallResult(
                tool_name=tool_name,
                decision=decision,
                status="pending_approval",
                message=decision.reason,
            )
            self._emit(
                kind="approval_required",
                payload={
                    "tool_name": tool_name,
                    "approval_id": decision.approval_id,
                    "reason": decision.reason,
                },
                buffer=events,
            )
            self._emit(
                kind="tool_result",
                payload={
                    "tool_name": tool_name,
                    "status": result.status,
                    "message": result.message,
                },
                buffer=events,
            )
            return result
        if not decision.allowed:
            result = ToolCallResult(
                tool_name=tool_name,
                decision=decision,
                status="blocked",
                message=decision.reason,
            )
            self._emit(
                kind="tool_result",
                payload={
                    "tool_name": tool_name,
                    "status": result.status,
                    "message": result.message,
                },
                buffer=events,
            )
            return result

        try:
            handler_result = await handler(tool_args, context)
        except Exception as exc:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK
            out = ToolCallResult(
                tool_name=tool_name,
                decision=decision,
                status="error",
                message=f"{type(exc).__name__}: {exc}",
            )
            self._emit(
                kind="tool_result",
                payload={
                    "tool_name": tool_name,
                    "status": out.status,
                    "message": out.message,
                },
                buffer=events,
            )
            return out
        result_status = str(handler_result.get("status") or "success")
        if result_status == "blocked":
            out = ToolCallResult(
                tool_name=tool_name,
                decision=decision,
                status="blocked",
                result=handler_result,
                message=str(handler_result.get("message") or "Tool handler blocked execution."),
            )
            self._emit(
                kind="tool_result",
                payload={
                    "tool_name": tool_name,
                    "status": out.status,
                    "message": out.message,
                },
                buffer=events,
            )
            return out
        out = ToolCallResult(
            tool_name=tool_name,
            decision=decision,
            status="ok",
            result=handler_result,
        )
        self._emit(
            kind="tool_result",
            payload={"tool_name": tool_name, "status": out.status},
            buffer=events,
        )
        return out
