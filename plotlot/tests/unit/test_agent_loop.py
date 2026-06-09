"""Unit tests for agent loop and middleware.

Tests the core agent loop infrastructure: middleware composition,
ReAct loop execution, token tracking, context management.
"""

import asyncio
from typing import Any

import pytest

from plotlot.harness.agent_loop import AgentConfig, AgentLoop
from plotlot.harness.builtin_middleware import (
    LocalContextMiddleware,
    LoopDetectionMiddleware,
    SaveStateMiddleware,
    TokenAwareMiddleware,
    ToolCallOffloadMiddleware,
)
from plotlot.harness.middleware import AgentMiddleware, AgentState, MiddlewarePipeline


class CountingModel:
    """Fake model that returns a fixed response and counts calls."""

    def __init__(self, response: str = "Final answer.", call_count: int = 1):
        self._response = response
        self._call_count = call_count
        self.calls: list[AgentState] = []

    async def __call__(self, state: AgentState, tools: list[dict[str, Any]]) -> AgentState:
        self.calls.append(state)
        if len(self.calls) >= self._call_count:
            state.should_stop = True
            state.stop_reason = "completed"
        state.add_message("assistant", self._response)
        return state


class EchoTool:
    """Fake tool that echoes its arguments."""

    async def __call__(self, tool_name: str, tool_args: dict[str, Any]) -> dict[str, Any]:
        return {"tool": tool_name, "args": tool_args, "ok": True}


class TestAgentState:
    def test_initial_state_values(self):
        state = AgentState()
        assert state.iteration == 0
        assert state.total_tokens == 0
        assert state.should_stop is False
        assert state.messages == []

    def test_add_message(self):
        state = AgentState()
        state.add_message("user", "hello")
        assert len(state.messages) == 1
        assert state.messages[0]["role"] == "user"
        assert state.messages[0]["content"] == "hello"

    def test_token_estimation(self):
        state = AgentState()
        state.add_message("user", "hello world " * 100)
        tokens = state.estimate_tokens()
        assert tokens > 0

    def test_context_usage_ratio(self):
        state = AgentState(max_tokens=1000)
        state.add_message("user", "x" * 4000)  # ~1000 tokens
        ratio = state.context_usage_ratio()
        assert ratio > 0.5


class TestMiddlewarePipeline:
    async def test_empty_pipeline_passes_state_through(self):
        pipeline = MiddlewarePipeline()
        state = AgentState()
        result = await pipeline.before_model(state)
        assert result is state

    async def test_single_middleware_runs(self):
        class CounterMiddleware(AgentMiddleware):
            async def before_model(self, state: AgentState) -> AgentState:
                state.custom["count"] = state.custom.get("count", 0) + 1
                return state

        pipeline = MiddlewarePipeline([CounterMiddleware()])
        state = AgentState()
        state = await pipeline.before_model(state)
        assert state.custom["count"] == 1

    async def test_multiple_middleware_run_in_order(self):
        collected: list[str] = []

        class A(AgentMiddleware):
            async def before_model(self, s: AgentState) -> AgentState:
                collected.append("A")
                return s

        class B(AgentMiddleware):
            async def before_model(self, s: AgentState) -> AgentState:
                collected.append("B")
                return s

        pipeline = MiddlewarePipeline([A(), B()])
        await pipeline.before_model(AgentState())
        assert collected == ["A", "B"]


class TestTokenAwareMiddleware:
    async def test_runs_before_model(self):
        mw = TokenAwareMiddleware(max_tokens=500)
        state = AgentState(max_tokens=500)
        state.add_message("user", "x" * 2000)  # ~500 tokens
        state = await mw.before_model(state)
        assert state.custom["context_usage_ratio"] >= 0.5

    async def test_stops_on_overflow(self):
        mw = TokenAwareMiddleware(max_tokens=10)
        state = AgentState(max_tokens=10)
        state.add_message("user", "x" * 1000)  # far exceeds 10 tokens
        state = await mw.before_model(state)
        assert state.should_stop is True
        assert state.stop_reason == "context_overflow"


class TestLocalContextMiddleware:
    async def test_injects_cwd(self):
        mw = LocalContextMiddleware()
        state = AgentState()
        state = await mw.before_agent(state)
        assert "cwd" in state.custom
        assert len(state.messages) >= 1


class TestLoopDetectionMiddleware:
    async def test_warns_after_max_edits(self):
        mw = LoopDetectionMiddleware(max_edits_per_file=2)
        state = AgentState()

        async def fake_execute(name: str, args: dict[str, Any]) -> dict[str, Any]:
            return {"ok": True}

        await mw.wrap_tool_call(state, "edit_file", {"filePath": "/x"}, fake_execute)
        await mw.wrap_tool_call(state, "edit_file", {"filePath": "/x"}, fake_execute)
        assert "loop_warning" in state.custom
        assert "rethinking" in state.custom["loop_warning"]

    async def test_no_warning_for_different_files(self):
        mw = LoopDetectionMiddleware(max_edits_per_file=2)
        state = AgentState()

        async def fake_execute(name: str, args: dict[str, Any]) -> dict[str, Any]:
            return {"ok": True}

        await mw.wrap_tool_call(state, "edit_file", {"filePath": "/a"}, fake_execute)
        await mw.wrap_tool_call(state, "edit_file", {"filePath": "/b"}, fake_execute)
        assert "loop_warning" not in state.custom


class TestAgentLoop:
    async def test_runs_to_completion(self):
        config = AgentConfig(
            model="test-model",
            system_prompt="You are a test agent.",
            max_iterations=5,
            middleware=[TokenAwareMiddleware(max_tokens=100_000)],
        )
        loop = AgentLoop(
            config=config,
            call_model=CountingModel(response="Done.", call_count=1),
            execute_tool=EchoTool(),
        )
        state = await loop.run("test task")
        assert state.should_stop is True
        assert state.iteration >= 1

    async def test_respects_max_iterations(self):
        config = AgentConfig(
            model="test-model",
            system_prompt="You are a test agent.",
            max_iterations=3,
        )
        loop = AgentLoop(
            config=config,
            call_model=CountingModel(response="Keep going.", call_count=99),
            execute_tool=EchoTool(),
        )
        state = await loop.run("test task")
        assert state.iteration >= state.max_iterations
        assert state.stop_reason == "max_iterations"

    async def test_middleware_composition(self):
        events: list[str] = []

        class TrackBefore(AgentMiddleware):
            async def before_model(self, s: AgentState) -> AgentState:
                events.append("before_model")
                return s

        class TrackAfter(AgentMiddleware):
            async def after_agent(self, s: AgentState) -> AgentState:
                events.append("after_agent")
                return s

        config = AgentConfig(
            model="test-model",
            system_prompt="Test",
            max_iterations=1,
            middleware=[TrackBefore(), TrackAfter()],
        )
        loop = AgentLoop(
            config=config,
            call_model=CountingModel(response="Done.", call_count=1),
            execute_tool=EchoTool(),
        )
        await loop.run("test")
        assert "before_model" in events
        assert "after_agent" in events


class TestSaveStateMiddleware:
    async def test_writes_state_file(self, tmp_path):
        state_path = str(tmp_path / "loop-state.md")
        mw = SaveStateMiddleware(state_path=state_path)
        state = AgentState()
        state.iteration = 5
        state.stop_reason = "completed"
        state.total_tokens = 1000
        state.tool_results.append({"call_id": "1", "name": "test", "result": "ok"})
        result = await mw.after_agent(state)
        assert result is state
        with open(state_path) as f:
            content = f.read()
        assert "iterations: 5" in content
        assert "completed" in content
