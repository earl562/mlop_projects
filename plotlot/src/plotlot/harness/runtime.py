"""Harness runtime boundary.

This is intentionally minimal: it exists to ensure every tool call is routed
through policy authorization and produces a structured result that transport
adapters (REST/chat/MCP) can render.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast
import uuid

from plotlot.harness.events import EventKind, HarnessEvent
from plotlot.harness.policy import HarnessPolicyEngine
from plotlot.harness.tool_registry import get_tool_contract, tool_exists
from plotlot.land_use.models import PolicyDecision, ToolContext
from plotlot.security.context import reset_tenant, set_tenant

ToolHandler = Callable[[dict[str, Any], ToolContext], Awaitable[dict[str, Any]]]

# How many runs' spend to remember. The ledger is in-process and advisory, so it
# only needs to outlive an active run; without a bound it would grow for the life
# of the process.
_MAX_TRACKED_RUNS = 1024


@dataclass(frozen=True)
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
        # Cumulative cents spent per run_id. `ToolContext.risk_budget_cents` is a
        # per-call ceiling supplied by the caller; on its own it authorises an
        # unbounded number of calls at or below that ceiling. See `_charge`.
        #
        # LIMITATION: this ledger is per-process. Under multiple web workers a run
        # routed across workers gets one budget per worker, so treat it as a bound
        # on runaway loops rather than a hard financial cap. Durable enforcement
        # belongs next to the persisted tool_run rows (`harness/run_persistence.py`)
        # and is not attempted here.
        self._run_spend: OrderedDict[str, int] = OrderedDict()

    def spent_cents(self, run_id: str) -> int:
        """Cents already charged against ``run_id`` in this process."""
        return self._run_spend.get(run_id, 0)

    def _charge(self, run_id: str, cents: int) -> None:
        """Record spend for ``run_id``, evicting the oldest run when full.

        Charged *before* the handler is awaited, for two reasons: a call that fails
        partway may still have cost money at the provider, and charging after the
        await would let concurrent calls in one run both read a stale total and
        each pass a budget check the pair of them exceeds.
        """
        if cents <= 0:
            return
        self._run_spend[run_id] = self._run_spend.pop(run_id, 0) + cents
        while len(self._run_spend) > _MAX_TRACKED_RUNS:
            self._run_spend.popitem(last=False)

    def _budget_scoped_context(self, context: ToolContext) -> ToolContext:
        """Context with the run's remaining — not original — budget.

        The policy engine is deliberately stateless: it compares one tool's cost
        against `context.risk_budget_cents`. Nothing decremented that value, so a
        run with a 100c budget could call a 25c tool any number of times. Handing
        the policy the remaining balance turns that ceiling into a real cap without
        the policy needing to know a ledger exists.
        """
        spent = self._run_spend.get(context.run_id, 0)
        if not spent:
            return context
        remaining = max(0, context.risk_budget_cents - spent)
        return context.model_copy(update={"risk_budget_cents": remaining})

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
            except Exception:
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
        """Execute a governed tool call bound to its workspace's tenant scope.

        Tenant-scoped tables enforce row-level security against
        `app.tenant_id`, which the session listener reads from the tenant
        contextvar. Without it a handler's queries return nothing — silently,
        as empty results rather than errors. `ToolContext.workspace_id` is the
        tenant boundary for a tool call, so binding it here covers every
        transport (REST, CLI, MCP) in one place instead of each adapter
        remembering to do it.
        """
        token = set_tenant(context.workspace_id)
        try:
            return await self._call_tool(
                tool_name=tool_name,
                tool_args=tool_args,
                context=context,
                approval_id=approval_id,
                events=events,
            )
        finally:
            reset_tenant(token)

    async def _call_tool(
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
            tool_name=tool_name,
            context=self._budget_scoped_context(context),
            approval_id=approval_id,
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

        # Charge the run before executing. An explicit approval overrides the budget
        # *check*, but the money is spent either way, so the ledger records it
        # regardless of why the call was allowed.
        # Safe: `tool_exists` gated the same registry above.
        self._charge(context.run_id, get_tool_contract(tool_name).budget_cents)

        try:
            handler_result = await handler(tool_args, context)
        except Exception as exc:
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
