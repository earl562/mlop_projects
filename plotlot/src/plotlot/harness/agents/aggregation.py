"""Result aggregation helpers for PlotLot specialist-agent runs."""

from __future__ import annotations

import uuid
from typing import Any

from plotlot.harness.agents.models import (
    AgentExecutionSummary,
    AgentPlan,
    AgentTaskResult,
    MultiAgentRunStatus,
    TaskStatus,
)
from plotlot.harness.agents.registry import AgentRegistry
from plotlot.harness.events import EventKind, HarnessEvent


def event(kind: EventKind, payload: dict[str, Any]) -> HarnessEvent:
    return HarnessEvent(kind=kind, id=str(uuid.uuid4()), payload=payload)


def task_event(kind: EventKind, result: AgentTaskResult) -> HarnessEvent:
    return event(
        kind,
        {
            "task_id": result.task_id,
            "agent_name": result.agent_name,
            "tool_name": result.tool_name,
            "status": result.status.value,
            "message": result.message,
            "approval_id": result.approval_id,
            "evidence_ids": list(result.evidence_ids),
        },
    )


def agent_summaries(
    plan: AgentPlan,
    results: tuple[AgentTaskResult, ...],
    registry: AgentRegistry,
) -> tuple[AgentExecutionSummary, ...]:
    result_by_task = {result.task_id: result for result in results}
    summaries: list[AgentExecutionSummary] = []
    seen: set[str] = set()
    for task in plan.tasks:
        if task.agent_name in seen:
            continue
        seen.add(task.agent_name)
        agent_tasks = [item for item in plan.tasks if item.agent_name == task.agent_name]
        agent_results = [result_by_task[item.task_id] for item in agent_tasks]
        approvals = tuple(
            result.approval_id for result in agent_results if result.approval_id is not None
        )
        if any(result.status == TaskStatus.PENDING_APPROVAL for result in agent_results):
            status = MultiAgentRunStatus.PENDING_APPROVAL
        elif all(result.status == TaskStatus.COMPLETED for result in agent_results):
            status = MultiAgentRunStatus.COMPLETED
        elif any(result.status == TaskStatus.COMPLETED for result in agent_results):
            status = MultiAgentRunStatus.NEEDS_REVIEW
        elif any(
            result.status in {TaskStatus.FAILED, TaskStatus.BLOCKED} for result in agent_results
        ):
            status = MultiAgentRunStatus.FAILED
        else:
            status = MultiAgentRunStatus.NEEDS_REVIEW
        summaries.append(
            AgentExecutionSummary(
                agent_name=task.agent_name,
                role=registry.get(task.agent_name).role,
                status=status,
                task_ids=tuple(item.task_id for item in agent_tasks),
                completed_tasks=sum(
                    result.status == TaskStatus.COMPLETED for result in agent_results
                ),
                failed_tasks=sum(
                    result.status in {TaskStatus.FAILED, TaskStatus.BLOCKED}
                    for result in agent_results
                ),
                skipped_tasks=sum(result.status == TaskStatus.SKIPPED for result in agent_results),
                approval_ids=approvals,
            )
        )
    return tuple(summaries)


def open_questions(
    plan: AgentPlan,
    results: tuple[AgentTaskResult, ...],
) -> tuple[str, ...]:
    questions = list(plan.open_questions)
    task_by_id = {task.task_id: task for task in plan.tasks}
    for result in results:
        if result.status == TaskStatus.COMPLETED:
            continue
        task = task_by_id[result.task_id]
        message = result.message or result.status.value.replace("_", " ")
        question = f"{task.agent_name}: {message}"
        if question not in questions:
            questions.append(question)
    return tuple(questions)


def run_status(
    plan: AgentPlan,
    results: tuple[AgentTaskResult, ...],
    questions: tuple[str, ...],
) -> MultiAgentRunStatus:
    if any(result.status == TaskStatus.PENDING_APPROVAL for result in results):
        return MultiAgentRunStatus.PENDING_APPROVAL

    result_by_task = {result.task_id: result for result in results}
    required = [task for task in plan.tasks if not task.optional]
    required_results = [result_by_task[task.task_id] for task in required]
    all_required_completed = all(
        result.status == TaskStatus.COMPLETED for result in required_results
    )
    any_required_completed = any(
        result.status == TaskStatus.COMPLETED for result in required_results
    )
    optional_issue = any(
        task.optional and result_by_task[task.task_id].status != TaskStatus.COMPLETED
        for task in plan.tasks
    )
    if all_required_completed:
        return (
            MultiAgentRunStatus.NEEDS_REVIEW
            if optional_issue or questions
            else MultiAgentRunStatus.COMPLETED
        )
    if any_required_completed:
        return MultiAgentRunStatus.NEEDS_REVIEW
    return MultiAgentRunStatus.FAILED


def primary_output(
    plan: AgentPlan,
    results: tuple[AgentTaskResult, ...],
) -> dict[str, Any]:
    if plan.primary_task_id:
        result = next(
            (item for item in results if item.task_id == plan.primary_task_id),
            None,
        )
        if result and result.status == TaskStatus.COMPLETED and result.result:
            return result.result
    for result in results:
        if result.status == TaskStatus.COMPLETED and result.result:
            return result.result
    return {}


__all__ = [
    "agent_summaries",
    "event",
    "open_questions",
    "primary_output",
    "run_status",
    "task_event",
]
