"""Sub-agent orchestration — spawn, isolate, filter tools, collect results.

Per AOrchestra (Paper 67): 4-tuple dynamic sub-agent creation (name, description, tools, prompt).
Per GTM Agent blog: one sub-agent per domain, isolated tools, parallel execution.
Per Claude Code arch (2604.14228): worktree isolation per sub-agent.
Per Text Block 2 (Obsidian vault): "Router doesn't see schema. Lane doesn't see router context."

Architecture: each sub-agent gets a fresh AgentState with filtered tools
and isolated context. Results collected by parent. Parallel execution supported.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from plotlot.harness.middleware import AgentMiddleware, AgentState


@dataclass
class SubAgent:
    name: str
    description: str
    system_prompt: str
    tools: list[dict[str, Any]] = field(default_factory=list)
    model: str | None = None
    max_iterations: int = 10

    def to_tool_schema(self) -> dict[str, Any]:
        return {
            "name": f"spawn_{self.name}",
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": f"Task for the {self.name} sub-agent"},
                },
                "required": ["task"],
            },
        }


@dataclass
class SubAgentResult:
    agent_name: str
    task: str
    output: str
    iterations: int
    stop_reason: str | None
    tool_calls: int


class SubAgentMiddleware(AgentMiddleware):
    """Middleware that registers sub-agents and handles spawning.

    Usage:
        zoning_agent = SubAgent(
            name="zoning",
            description="Analyze zoning code compliance for a parcel",
            system_prompt="You are a zoning analyst. Check compliance against municipal code.",
            tools=[zoning_lookup_schema, setback_calculator_schema],
        )
        middleware = SubAgentMiddleware(sub_agents=[zoning_agent], execute_agent=my_executor)
    """

    def __init__(
        self,
        sub_agents: list[SubAgent] | None = None,
        execute_agent: Callable[[SubAgent, str], Awaitable[SubAgentResult]] | None = None,
        max_parallel: int = 10,
    ):
        self._sub_agents: dict[str, SubAgent] = {}
        self._execute = execute_agent or self._default_execute
        self._max_parallel = max_parallel
        self._results: dict[str, list[SubAgentResult]] = {}
        for sa in (sub_agents or []):
            self._sub_agents[sa.name] = sa

    @property
    def name(self) -> str:
        return "SubAgentMiddleware"

    def register(self, agent: SubAgent) -> None:
        self._sub_agents[agent.name] = agent

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        return [sa.to_tool_schema() for sa in self._sub_agents.values()]

    def get_agent_names(self) -> list[str]:
        return list(self._sub_agents.keys())

    async def wrap_tool_call(
        self,
        state: AgentState,
        tool_name: str,
        tool_args: dict[str, Any],
        execute_tool: Any,
    ) -> dict[str, Any]:
        prefix = "spawn_"
        if tool_name.startswith(prefix):
            agent_name = tool_name[len(prefix):]
            task = tool_args.get("task", "")
            if agent_name in self._sub_agents:
                return await self._handle_spawn(state, agent_name, task)
        return await execute_tool(tool_name, tool_args)

    async def after_agent(self, state: AgentState) -> AgentState:
        if self._results:
            summary = self._summarize_results()
            state.add_message("system", f"Sub-agent results:\n{summary}")
            state.custom["sub_agent_results"] = {
                name: [{"task": r.task, "output": r.output[:500]} for r in results]
                for name, results in self._results.items()
            }
        return state

    async def _handle_spawn(self, state: AgentState, agent_name: str, task: str) -> dict[str, Any]:
        agent = self._sub_agents[agent_name]
        result = await self._execute(agent, task)
        self._results.setdefault(agent_name, []).append(result)
        return {
            "ok": True,
            "agent": agent_name,
            "task": task,
            "output": result.output,
            "iterations": result.iterations,
            "tool_calls": result.tool_calls,
        }

    async def spawn_parallel(self, tasks: list[tuple[str, str]]) -> dict[str, SubAgentResult]:
        """Spawn multiple sub-agents in parallel. Returns results keyed by agent_name."""
        results: dict[str, SubAgentResult] = {}
        sem = asyncio.Semaphore(self._max_parallel)

        async def run_one(agent_name: str, task: str) -> None:
            async with sem:
                result = await self._execute(self._sub_agents[agent_name], task)
                results[agent_name] = result

        await asyncio.gather(*(run_one(name, task) for name, task in tasks))
        return results

    async def _default_execute(self, agent: SubAgent, task: str) -> SubAgentResult:
        """Execute sub-agent using its own model caller with isolated state."""
        from plotlot.harness.agent_loop import AgentConfig, AgentLoop
        from plotlot.harness.model_adapter import create_model_caller

        config = AgentConfig(
            model=agent.model or "openai/gpt-4.1-mini",
            system_prompt=agent.system_prompt,
            tools=agent.tools,
            max_iterations=agent.max_iterations,
        )
        call_model = create_model_caller(provider="openrouter", model=config.model)
        loop = AgentLoop(config=config, call_model=call_model, execute_tool=_default_tool_executor)
        state = await loop.run(task)
        output = ""
        for msg in state.messages:
            if msg.get("role") == "assistant":
                output = str(msg.get("content", ""))
        return SubAgentResult(
            agent_name=agent.name, task=task, output=output or "[Sub-agent completed — see trace]",
            iterations=state.iteration, stop_reason=state.stop_reason,
            tool_calls=len(state.tool_results),
        )


async def _default_tool_executor(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "tool": tool_name, "args": str(args)[:200]}

    def _summarize_results(self) -> str:
        lines = []
        for name, results in self._results.items():
            for r in results:
                lines.append(f"[{name}] {r.task[:100]} → {r.iterations} iter, {r.tool_calls} tools")
        return "\n".join(lines)


# ==========================================================================
# Stage isolation helper
# ==========================================================================


def isolated_tools(all_tools: list[dict[str, Any]], allowed: list[str]) -> list[dict[str, Any]]:
    """Filter tool schemas to only those allowed for a sub-agent.

    Per stage isolation pattern: each sub-agent gets exactly what it needs.
    Router doesn't see schema. Lane doesn't see router context.
    """
    return [t for t in all_tools if t.get("name") in allowed]
