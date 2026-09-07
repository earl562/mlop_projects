"""Task execution helpers for the governed multi-agent coordinator."""

from __future__ import annotations

import asyncio
from typing import Any, Protocol

from plotlot.domain.types import ToolContext
from plotlot.harness.agents.models import AgentTask, AgentTaskResult, TaskStatus
from plotlot.harness.events import HarnessEvent
from plotlot.harness.runtime import ToolCallResult


class RuntimeProtocol(Protocol):
    async def call_tool(
        self,
        *,
        tool_name: str,
        tool_args: dict[str, Any],
        context: ToolContext,
        approval_id: str | None = None,
        events: list[HarnessEvent] | None = None,
    ) -> ToolCallResult: ...


_MISSING = object()
_FAILURE_PAYLOAD_STATUSES = {
    "error",
    "not_found",
    "no_results",
    "not_configured",
    "empty",
    "unsupported",
    "unavailable",
}


class TaskExecutor:
    def __init__(self, runtime: RuntimeProtocol, *, max_concurrency: int) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be positive")
        self._runtime = runtime
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def execute(
        self,
        task: AgentTask,
        *,
        results: dict[str, AgentTaskResult],
        context: ToolContext,
        events: list[HarnessEvent],
    ) -> AgentTaskResult:
        arguments, missing = resolve_arguments(task, results)
        if missing:
            return skipped_result(task, missing)

        if task.collect_evidence:
            # Include the full completed research chain. Geocode and parcel evidence
            # are transitive dependencies of an evidence-backed report task.
            evidence_ids = ordered_evidence_ids(tuple(results.values()))
            if not evidence_ids:
                return skipped_result(
                    task,
                    "No cited evidence was available for the evidence-backed artifact.",
                )
            arguments["evidence_ids"] = list(evidence_ids)

        task_context = context.model_copy(update={"tool_run_id": task.task_id})
        async with self._semaphore:
            call_result = await self._runtime.call_tool(
                tool_name=task.tool_name,
                tool_args=arguments,
                context=task_context,
                events=events,
            )
        return from_tool_result(task, call_result)


def resolve_arguments(
    task: AgentTask,
    results: dict[str, AgentTaskResult],
) -> tuple[dict[str, Any], str | None]:
    arguments = dict(task.arguments)
    for name, binding in task.bindings.items():
        source = results[binding.source_task_id].result
        value = read_path(source, binding.path)
        if value is _MISSING or value is None or value == "":
            if binding.required:
                return (
                    arguments,
                    f"Required input {name!r} was missing from task "
                    f"{binding.source_task_id!r} at {binding.path!r}.",
                )
            value = binding.default
        if binding.prefix or binding.suffix:
            value = f"{binding.prefix}{value}{binding.suffix}"
        arguments[name] = value
    return arguments, None


def read_path(payload: dict[str, Any] | None, path: str) -> Any:
    current: Any = payload
    for segment in path.split("."):
        if isinstance(current, dict) and segment in current:
            current = current[segment]
            continue
        if isinstance(current, list) and segment.isdigit():
            index = int(segment)
            if 0 <= index < len(current):
                current = current[index]
                continue
        return _MISSING
    return current


def from_tool_result(task: AgentTask, call_result: ToolCallResult) -> AgentTaskResult:
    payload = call_result.result
    if call_result.status == "pending_approval":
        status = TaskStatus.PENDING_APPROVAL
    elif call_result.status == "blocked":
        status = TaskStatus.BLOCKED
    elif call_result.status != "ok" or payload is None:
        status = TaskStatus.FAILED
    else:
        payload_status = str(payload.get("status") or "success").lower()
        status = (
            TaskStatus.FAILED
            if payload_status in _FAILURE_PAYLOAD_STATUSES
            else TaskStatus.COMPLETED
        )

    message = call_result.message
    if not message and isinstance(payload, dict):
        raw_message = payload.get("message")
        if raw_message:
            message = str(raw_message)
    return AgentTaskResult(
        task_id=task.task_id,
        agent_name=task.agent_name,
        tool_name=task.tool_name,
        status=status,
        runtime_status=call_result.status,
        result=payload,
        message=message,
        approval_id=call_result.decision.approval_id,
        evidence_ids=extract_evidence_ids(payload),
        artifacts=(payload.get("artifacts") if isinstance(payload, dict) else {}) or {},
    )


def extract_evidence_ids(payload: dict[str, Any] | None) -> tuple[str, ...]:
    if not isinstance(payload, dict):
        return ()
    ordered: list[str] = []

    def add(value: Any) -> None:
        if isinstance(value, str) and value and value not in ordered:
            ordered.append(value)

    for value in payload.get("evidence_ids") or []:
        add(value)
    for item in payload.get("evidence") or []:
        if isinstance(item, dict):
            add(item.get("id"))
            add(item.get("evidence_id"))
    for item in payload.get("source_refs") or []:
        if isinstance(item, dict):
            add(item.get("evidence_id"))
    return tuple(ordered)


def ordered_evidence_ids(results: tuple[AgentTaskResult, ...]) -> tuple[str, ...]:
    ordered: list[str] = []
    for result in results:
        for evidence_id in result.evidence_ids:
            if evidence_id not in ordered:
                ordered.append(evidence_id)
    return tuple(ordered)


def skipped_result(task: AgentTask, message: str) -> AgentTaskResult:
    return AgentTaskResult(
        task_id=task.task_id,
        agent_name=task.agent_name,
        tool_name=task.tool_name,
        status=TaskStatus.SKIPPED,
        message=message,
    )


__all__ = [
    "RuntimeProtocol",
    "TaskExecutor",
    "extract_evidence_ids",
    "from_tool_result",
    "ordered_evidence_ids",
    "read_path",
    "resolve_arguments",
    "skipped_result",
]
