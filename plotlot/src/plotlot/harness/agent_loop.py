"""Agent loop — create_agent-style ReAct loop with middleware.

Sits on top of the existing `HarnessRuntime` tool execution layer.
Adds: model calling, ReAct loop, middleware hooks, context management,
filesystem access, git checkpointing, and token tracking.

References:
- Anatomy of an Agent Harness (LangChain, March 2026)
- OpenDev v3: 6-phase extended ReAct loop (arXiv 2603.05344)
- Externalization paper: Agent = Model + Harness (arXiv 2604.08224)
- Meta-Harness: filesystem-based state persistence (arXiv 2603.28052)
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from plotlot.harness.middleware import (
    AgentMiddleware,
    AgentState,
    MiddlewarePipeline,
)


@dataclass
class AgentConfig:
    model: str = "claude-sonnet-4-6"
    system_prompt: str = "You are a helpful assistant."
    tools: list[dict[str, Any]] = field(default_factory=list)
    max_iterations: int = 100
    max_tokens: int = 200_000
    compact_at_ratio: float = 0.8
    middleware: list[AgentMiddleware] = field(default_factory=list)


class AgentLoop:
    """ReAct agent loop with composable middleware.

    Usage:
        agent = AgentLoop(
            config=AgentConfig(
                model="claude-sonnet-4-6",
                system_prompt="You are a land development analyst.",
                tools=[...],
                middleware=[TokenAwareMiddleware(), SummarizationMiddleware()],
            ),
            call_model=my_model_caller,
            execute_tool=my_tool_executor,
        )
        result = await agent.run("Analyze parcel 123 for multi-family feasibility.")
    """

    def __init__(
        self,
        *,
        config: AgentConfig,
        call_model: Callable[[AgentState, list[dict[str, Any]]], Awaitable[AgentState]],
        execute_tool: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]],
    ) -> None:
        self._config = config
        self._call_model = call_model
        self._execute_tool = execute_tool
        self._pipeline = MiddlewarePipeline(list(config.middleware))
        self._run_id: str | None = None
        self._git_snapshots: list[str] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self, user_message: str) -> AgentState:
        self._run_id = str(uuid.uuid4())[:8]
        state = await self._init_state(user_message)
        state = await self._pipeline.before_agent(state)
        await self._checkpoint_git("agent-start")

        while not state.should_stop and state.iteration < state.max_iterations:
            state.iteration += 1

            # Phase 0: context management
            state = await self._compact_if_needed(state)

            # Phase 1: pre-model hooks
            state = await self._pipeline.before_model(state)
            if state.should_stop:
                break

            # Phase 2: model call (through middleware wrapper)
            state = await self._pipeline.wrap_model_call(state, self._call_model_impl)
            if state.should_stop:
                break

            # Phase 3: post-model hooks
            state = await self._pipeline.after_model(state)
            if state.should_stop:
                break

            # Phase 4: tool execution
            state = await self._execute_tool_calls(state)

            if state.iteration >= state.max_iterations:
                state.should_stop = True
                state.stop_reason = "max_iterations"

        state = await self._pipeline.after_agent(state)
        await self._checkpoint_git("agent-end")
        return state

    def add_middleware(self, mw: AgentMiddleware) -> None:
        self._pipeline.add(mw)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _init_state(self, user_message: str) -> AgentState:
        state = AgentState(
            max_iterations=self._config.max_iterations,
            max_tokens=self._config.max_tokens,
        )
        state.add_message("system", self._config.system_prompt)
        state.add_message("user", user_message)
        state.metadata["run_id"] = self._run_id
        state.metadata["model"] = self._config.model
        state.metadata["start_time"] = str(asyncio.get_event_loop().time())
        return state

    async def _call_model_impl(self, state: AgentState) -> AgentState:
        """Delegate to the injected model caller."""
        return await self._call_model(state, self._config.tools)

    async def _compact_if_needed(self, state: AgentState) -> AgentState:
        """Check context usage and trigger compaction if needed."""
        ratio = state.context_usage_ratio()
        state.custom["context_usage_ratio"] = ratio
        if ratio >= self._config.compact_at_ratio:
            state.custom["compaction_triggered"] = True
        return state

    async def _execute_tool_calls(self, state: AgentState) -> AgentState:
        """Execute pending tool calls through the middleware pipeline."""
        for tc in state.tool_calls:
            tool_name = tc.get("name", "")
            tool_args = tc.get("arguments", {})

            result = await self._pipeline.wrap_tool_call(
                state, tool_name, tool_args, self._execute_tool
            )

            state.add_tool_result(
                call_id=tc.get("call_id", str(uuid.uuid4())),
                name=tool_name,
                result=json.dumps(result),
            )
        state.tool_calls.clear()
        return state

    async def _checkpoint_git(self, label: str) -> None:
        """Shadow git snapshot for rollback safety."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                return
            commit_msg = f"loop(iter-{self._run_id}): {label}"
            subprocess.run(
                ["git", "add", "-A"],
                capture_output=True, timeout=10,
            )
            proc = subprocess.run(
                ["git", "commit", "-m", commit_msg, "--allow-empty"],
                capture_output=True, text=True, timeout=10,
            )
            if proc.returncode == 0:
                sha = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    capture_output=True, text=True, timeout=5,
                ).stdout.strip()[:8]
                self._git_snapshots.append(sha)
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
