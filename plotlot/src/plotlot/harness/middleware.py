"""Agent middleware — composable hooks into the agent loop.

Middleware hooks into the agent execution cycle at each phase:
- before_agent: Once on invocation (load memory, connect resources)
- before_model: Before each model call (inject context, trim history, catch PII)
- wrap_model_call: Wraps the model API call (retry, caching, dynamic tools)
- wrap_tool_call: Wraps tool execution (inject context, intercept results, gate)
- after_model: After model responds, before tools execute (HITL, moderation)
- after_agent: Once on completion (save results, notify, clean up)

Middlewares are composable — a stack executes in registration order.
Each middleware returns the (possibly modified) state so the next one sees it.

References:
- LangChain: How Middleware Lets You Customize Your Agent Harness (March 2026)
- LangChain: How to Build a Custom Agent Harness (June 2026)
- Claude Code architecture: 7-mode permission, 5-layer compaction (arXiv 2604.14228)
- OpenDev v3: 6-phase ReAct loop, context-as-first-class-concern (arXiv 2603.05344)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable
from dataclasses import dataclass, field
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Agent state carried through the loop
# ---------------------------------------------------------------------------


@dataclass
class AgentState:
    """Mutable state passed through every middleware hook.

    Carries messages, tool results, loop metadata, and arbitrary extension
    data that middleware can read/write across hooks.
    """

    messages: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    custom: dict[str, Any] = field(default_factory=dict)

    # Loop tracking
    iteration: int = 0
    total_tokens: int = 0
    max_iterations: int = 100
    max_tokens: int = 200_000

    # Completion
    should_stop: bool = False
    stop_reason: str | None = None

    def add_message(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})

    def add_tool_call(self, name: str, args: dict[str, Any], call_id: str) -> None:
        self.tool_calls.append(
            {"name": name, "arguments": args, "call_id": call_id}
        )

    def add_tool_result(self, call_id: str, name: str, result: str) -> None:
        self.tool_results.append(
            {"call_id": call_id, "name": name, "result": result}
        )

    def estimate_tokens(self) -> int:
        """Rough token estimation — 4 chars ≈ 1 token."""
        total = 0
        for msg in self.messages:
            total += len(str(msg.get("content", ""))) // 4
        return total

    def context_usage_ratio(self) -> float:
        """Fraction of max tokens consumed."""
        return self.estimate_tokens() / max(self.max_tokens, 1)


# ---------------------------------------------------------------------------
# Middleware base
# ---------------------------------------------------------------------------


class AgentMiddleware(ABC):
    """Base class for composable agent middleware.

    Every hook is optional — override only the hooks you need.
    Return the state (or a modified copy) from each hook.
    """

    @property
    def name(self) -> str:
        return self.__class__.__name__

    async def before_agent(self, state: AgentState) -> AgentState:
        """Run once before agent invocation."""
        return state

    async def before_model(self, state: AgentState) -> AgentState:
        """Run before each model call."""
        return state

    async def wrap_model_call(
        self,
        state: AgentState,
        call_model: Callable[[AgentState], Awaitable[AgentState]],
    ) -> AgentState:
        """Wrap the model call. Default: just delegate."""
        return await call_model(state)

    async def wrap_tool_call(
        self,
        state: AgentState,
        tool_name: str,
        tool_args: dict[str, Any],
        execute_tool: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        """Wrap a single tool execution."""
        return await execute_tool(tool_name, tool_args)

    async def after_model(self, state: AgentState) -> AgentState:
        """Run after model responds, before tools execute."""
        return state

    async def after_agent(self, state: AgentState) -> AgentState:
        """Run once after agent completes."""
        return state


# ---------------------------------------------------------------------------
# Pipeline — composes middleware into a single callable
# ---------------------------------------------------------------------------


class MiddlewarePipeline:
    """Compose multiple middlewares into a single execution pipeline."""

    def __init__(self, middlewares: list[AgentMiddleware] | None = None) -> None:
        self._middlewares: list[AgentMiddleware] = middlewares or []

    def add(self, mw: AgentMiddleware) -> None:
        self._middlewares.append(mw)

    @property
    def middlewares(self) -> list[AgentMiddleware]:
        return list(self._middlewares)

    async def before_agent(self, state: AgentState) -> AgentState:
        for mw in self._middlewares:
            state = await mw.before_agent(state)
        return state

    async def before_model(self, state: AgentState) -> AgentState:
        for mw in self._middlewares:
            state = await mw.before_model(state)
        return state

    async def after_model(self, state: AgentState) -> AgentState:
        for mw in self._middlewares:
            state = await mw.after_model(state)
        return state

    async def after_agent(self, state: AgentState) -> AgentState:
        for mw in self._middlewares:
            state = await mw.after_agent(state)
        return state

    async def wrap_model_call(
        self,
        state: AgentState,
        call_model: Callable[[AgentState], Awaitable[AgentState]],
    ) -> AgentState:
        """Chain wrap_model_call from outermost to innermost."""
        # Build the call chain from last middleware to first
        wrapped = call_model
        for mw in reversed(self._middlewares):
            outer = wrapped  # capture current inner
            wrapped = lambda s, mw=mw, inner=outer: mw.wrap_model_call(s, inner)
        return await wrapped(state)

    async def wrap_tool_call(
        self,
        state: AgentState,
        tool_name: str,
        tool_args: dict[str, Any],
        execute_tool: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        """Chain tool execution through middleware."""
        # Return the result — middleware may modify tool_args or result
        for mw in self._middlewares:
            result = await mw.wrap_tool_call(
                state, tool_name, tool_args, execute_tool
            )
            return result
        return await execute_tool(tool_name, tool_args)
