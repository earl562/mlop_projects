"""Built-in middleware implementations for the PlotLot agent harness.

Each middleware handles one concern and composes freely.

References:
- LangChain prebuilt middleware catalog
- OpenAI Harness Engineering: token-aware compaction, lints as instructions
- Vivek Trivedy: PreCompletionChecklistMiddleware, LocalContextMiddleware, LoopDetectionMiddleware
- Claude Code: 5-layer compaction pipeline (arXiv 2604.14228)
"""

from __future__ import annotations

import os
from typing import Any

from plotlot.harness.middleware import AgentMiddleware, AgentState


class TokenAwareMiddleware(AgentMiddleware):
    """Track token usage and warn when approaching limits.

    Sets state.should_stop when max_tokens is exceeded.
    Injects context usage ratio into state.custom for downstream middleware.
    """

    def __init__(self, compact_at_ratio: float = 0.8, max_tokens: int = 200_000):
        self._compact_at = compact_at_ratio
        self._max_tokens = max_tokens

    async def before_model(self, state: AgentState) -> AgentState:
        tokens = state.estimate_tokens()
        state.total_tokens = tokens
        ratio = tokens / max(self._max_tokens, 1)
        state.custom["token_count"] = tokens
        state.custom["context_usage_ratio"] = ratio
        if tokens >= self._max_tokens:
            state.should_stop = True
            state.stop_reason = "context_overflow"
        return state


class ToolCallOffloadMiddleware(AgentMiddleware):
    """Offload large tool outputs to filesystem.

    Keeps head_tokens and tail_tokens in context.
    Writes full output to a temp file the agent can access if needed.
    """

    def __init__(self, head_tokens: int = 500, tail_tokens: int = 200):
        self._head = head_tokens
        self._tail = tail_tokens

    async def wrap_tool_call(
        self,
        state: AgentState,
        tool_name: str,
        tool_args: dict[str, Any],
        execute_tool: Any,
    ) -> dict[str, Any]:
        result = await execute_tool(tool_name, tool_args)
        output = str(result)
        if len(output) > (self._head + self._tail) * 4:
            truncated = output[: self._head * 4] + f"\n... [{len(output)} chars total] ...\n" + output[-self._tail * 4:]
            result["_truncated"] = True
            result["_full_output_length"] = len(output)
            result["output"] = truncated
        return result


class LoopDetectionMiddleware(AgentMiddleware):
    """Detect doom loops — repeated edits to the same file.

    After max_edits edits to any single file, injects a warning
    into state context for the next model call.
    Pattern from Vivek Trivedy's "Improving Deep Agents with Harness Engineering."
    """

    def __init__(self, max_edits_per_file: int = 5):
        self._max = max_edits_per_file
        self._edit_counts: dict[str, int] = {}

    async def wrap_tool_call(
        self,
        state: AgentState,
        tool_name: str,
        tool_args: dict[str, Any],
        execute_tool: Any,
    ) -> dict[str, Any]:
        if tool_name in ("edit_file", "write_file"):
            path = tool_args.get("filePath", tool_args.get("path", ""))
            self._edit_counts[path] = self._edit_counts.get(path, 0) + 1
            if self._edit_counts[path] >= self._max:
                state.custom["loop_warning"] = (
                    f"Edited {path} {self._edit_counts[path]} times. "
                    "Consider if your approach needs rethinking."
                )
        return await execute_tool(tool_name, tool_args)


class LocalContextMiddleware(AgentMiddleware):
    """Inject filesystem context on agent start.

    Maps cwd, directory structure, and available tooling (Python, git, etc.).
    Pattern from Vivek Trivedy: reduces context discovery errors.
    """

    async def before_agent(self, state: AgentState) -> AgentState:
        cwd = os.getcwd()
        try:
            entries = os.listdir(cwd)
            top_level = [e for e in entries if not e.startswith(".")][:20]
        except OSError:
            top_level = []
        state.custom["cwd"] = cwd
        state.custom["top_level_entries"] = top_level
        state.add_message(
            "system",
            f"Working directory: {cwd}\n"
            f"Top-level contents: {', '.join(top_level)}",
        )
        return state


class SaveStateMiddleware(AgentMiddleware):
    """Persist agent state to `.sisyphus/loop-state.md` after completion.

    Writes iteration count, stop reason, and key decisions.
    Pattern from Meta-Harness: filesystem-bridged state between iterations.
    """

    def __init__(self, state_path: str = ".sisyphus/loop-state.md"):
        self._path = state_path

    async def after_agent(self, state: AgentState) -> AgentState:
        try:
            os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
            with open(self._path, "w") as f:
                f.write(f"# Loop State (auto-written)\n\n")
                f.write(f"iterations: {state.iteration}\n")
                f.write(f"stop_reason: {state.stop_reason or 'completed'}\n")
                f.write(f"total_tokens: {state.total_tokens}\n")
                f.write(f"context_usage: {state.context_usage_ratio():.1%}\n")
                f.write(f"tool_calls: {len(state.tool_results)}\n")
        except OSError:
            pass
        return state
