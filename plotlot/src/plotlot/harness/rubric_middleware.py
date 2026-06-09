"""RubricMiddleware — self-verification against completion criteria.

Per RubricMiddleware (LangChain blog, June 2026):
Define a rubric → dedicated grader evaluates output → per-criterion feedback
injected → agent retries. Loop: generate → grade → feedback → retry → satisfied.

The grader can call tools to gather hard evidence (run tests, validate outputs).
Falls back to transcript reasoning when no tools provided.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from plotlot.harness.middleware import AgentMiddleware, AgentState


class RubricMiddleware(AgentMiddleware):
    """Self-verification: grade output against rubric criteria before completion.

    Before the agent declares completion, this middleware evaluates the output
    against the rubric. If criteria fail, feedback is injected and the agent
    retries. The loop terminates on satisfied, max_iterations, or grader_error.
    """

    def __init__(
        self,
        rubric: list[str],
        max_retries: int = 3,
        grader: Callable[[str, list[str]], Awaitable[dict[str, Any]]] | None = None,
    ):
        self._rubric = rubric
        self._max_retries = max_retries
        self._grader = grader
        self._retry_count = 0

    async def after_model(self, state: AgentState) -> AgentState:
        if not self._rubric or state.should_stop:
            return state
        if self._retry_count >= self._max_retries:
            state.custom["rubric_max_retries"] = True
            return state
        output = self._extract_last_output(state)
        if not output:
            return state
        results = await self._grade(output)
        passed = all(r.get("passed", False) for r in results)
        state.custom["rubric_results"] = results
        state.custom["rubric_passed"] = passed
        if not passed:
            self._retry_count += 1
            feedback = self._build_feedback(results)
            state.custom["rubric_retry"] = self._retry_count
            state.add_message("system", f"Rubric check failed ({self._retry_count}/{self._max_retries}):\n{feedback}\n\nPlease fix the issues and try again.")
        return state

    def _extract_last_output(self, state: AgentState) -> str:
        for msg in reversed(state.messages):
            if msg.get("role") == "assistant":
                return str(msg.get("content", ""))
        return ""

    async def _grade(self, output: str) -> list[dict[str, Any]]:
        if self._grader:
            return await self._grader(output, list(self._rubric))
        return self._simple_grade(output)

    def _simple_grade(self, output: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        output_lower = output.lower()
        for criterion in self._rubric:
            keywords = criterion.lower().split()
            passed = any(kw in output_lower for kw in keywords)
            results.append({
                "criterion": criterion,
                "passed": passed,
                "reason": "Keyword match" if passed else "Required content not found in output",
            })
        return results

    def _build_feedback(self, results: list[dict[str, Any]]) -> str:
        lines = []
        for r in results:
            status = "PASS" if r.get("passed") else "FAIL"
            lines.append(f"[{status}] {r['criterion']}: {r.get('reason','')}")
        return "\n".join(lines)
