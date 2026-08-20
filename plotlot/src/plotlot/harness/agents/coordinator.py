"""Governed multi-agent coordinator for PlotLot workflows."""

from __future__ import annotations

import asyncio
from dataclasses import asdict

from plotlot.domain.types import ToolContext
from plotlot.harness.agents.aggregation import (
    agent_summaries,
    event,
    open_questions,
    primary_output,
    run_status,
    task_event,
)
from plotlot.harness.agents.execution import (
    RuntimeProtocol,
    TaskExecutor,
    ordered_evidence_ids,
    skipped_result,
)
from plotlot.harness.agents.models import (
    AgentExecutionSummary,
    AgentPlan,
    AgentTask,
    AgentTaskResult,
    MultiAgentRunRequest,
    MultiAgentRunResult,
    MultiAgentRunStatus,
    TaskStatus,
)
from plotlot.harness.agents.planner import MultiAgentPlanner
from plotlot.harness.agents.registry import AgentRegistry, build_default_agent_registry
from plotlot.harness.events import EventKind, HarnessEvent


class MultiAgentCoordinator:
    """Plan and execute specialist tasks through one policy-gated runtime."""

    def __init__(
        self,
        runtime: RuntimeProtocol,
        *,
        registry: AgentRegistry | None = None,
        planner: MultiAgentPlanner | None = None,
        max_concurrency: int = 4,
    ) -> None:
        self._registry = registry or build_default_agent_registry()
        self._planner = planner or MultiAgentPlanner(self._registry)
        self._executor = TaskExecutor(runtime, max_concurrency=max_concurrency)

    def plan(self, request: MultiAgentRunRequest) -> AgentPlan:
        return self._planner.build(request)

    async def run(
        self,
        request: MultiAgentRunRequest,
        context: ToolContext,
    ) -> MultiAgentRunResult:
        plan = self.plan(request)
        events: list[HarnessEvent] = [
            event(
                "run_started",
                {
                    "run_id": context.run_id,
                    "workflow": request.workflow.value,
                    "objective": request.objective,
                },
            ),
            event(
                "plan_created",
                {
                    "run_id": context.run_id,
                    "task_ids": [task.task_id for task in plan.tasks],
                    "agent_names": sorted({task.agent_name for task in plan.tasks}),
                },
            ),
        ]
        task_by_id = {task.task_id: task for task in plan.tasks}
        pending = set(task_by_id)
        results: dict[str, AgentTaskResult] = {}
        started_agents: set[str] = set()

        while pending:
            ready = [
                task
                for task in plan.tasks
                if task.task_id in pending
                and all(dependency in results for dependency in task.depends_on)
            ]
            if not ready:
                self._skip_unschedulable(pending, task_by_id, results, events)
                break

            runnable: list[AgentTask] = []
            for task in ready:
                pending.remove(task.task_id)
                if self._dependency_failed(task, results):
                    result = skipped_result(
                        task,
                        "A required dependency did not complete successfully.",
                    )
                    results[task.task_id] = result
                    events.append(task_event("task_skipped", result))
                    continue
                self._start_task(task, started_agents, events)
                runnable.append(task)

            if runnable:
                completed = await asyncio.gather(
                    *(
                        self._executor.execute(
                            task,
                            results=results,
                            context=context,
                            events=events,
                        )
                        for task in runnable
                    )
                )
                for result in completed:
                    results[result.task_id] = result
                    kind: EventKind = (
                        "task_skipped" if result.status == TaskStatus.SKIPPED else "task_completed"
                    )
                    events.append(task_event(kind, result))

        ordered_results = tuple(results[task.task_id] for task in plan.tasks)
        evidence_ids = ordered_evidence_ids(ordered_results)
        artifacts = {
            result.task_id: result.artifacts for result in ordered_results if result.artifacts
        }
        questions = open_questions(plan, ordered_results)
        status = run_status(plan, ordered_results, questions)
        summaries = agent_summaries(plan, ordered_results, self._registry)
        self._append_terminal_events(
            events,
            context=context,
            summaries=summaries,
            status=status,
            evidence_count=len(evidence_ids),
            task_count=len(ordered_results),
            questions=questions,
        )

        return MultiAgentRunResult(
            run_id=context.run_id,
            workflow=request.workflow,
            status=status,
            plan=plan,
            task_results=ordered_results,
            agents=summaries,
            evidence_ids=evidence_ids,
            artifacts=artifacts,
            open_questions=questions,
            primary_output=primary_output(plan, ordered_results),
            events=tuple(asdict(item) for item in events),
        )

    @staticmethod
    def _dependency_failed(
        task: AgentTask,
        results: dict[str, AgentTaskResult],
    ) -> bool:
        dependencies = [results[dependency] for dependency in task.depends_on]
        required_success = [
            results[dependency] for dependency in task.required_success_dependencies
        ]
        return (
            task.dependency_mode == "all_success"
            and any(result.status != TaskStatus.COMPLETED for result in dependencies)
        ) or any(result.status != TaskStatus.COMPLETED for result in required_success)

    def _start_task(
        self,
        task: AgentTask,
        started_agents: set[str],
        events: list[HarnessEvent],
    ) -> None:
        if task.agent_name not in started_agents:
            started_agents.add(task.agent_name)
            events.append(
                event(
                    "agent_started",
                    {
                        "agent_name": task.agent_name,
                        "role": self._registry.get(task.agent_name).role.value,
                    },
                )
            )
        events.append(
            event(
                "task_started",
                {
                    "task_id": task.task_id,
                    "agent_name": task.agent_name,
                    "tool_name": task.tool_name,
                },
            )
        )

    @staticmethod
    def _skip_unschedulable(
        pending: set[str],
        task_by_id: dict[str, AgentTask],
        results: dict[str, AgentTaskResult],
        events: list[HarnessEvent],
    ) -> None:
        # AgentPlan validates cycles, so this is a defensive runtime guard.
        for task_id in sorted(pending):
            result = skipped_result(
                task_by_id[task_id],
                "Task could not be scheduled because its dependencies did not terminate.",
            )
            results[task_id] = result
            events.append(task_event("task_skipped", result))
        pending.clear()

    @staticmethod
    def _append_terminal_events(
        events: list[HarnessEvent],
        *,
        context: ToolContext,
        summaries: tuple[AgentExecutionSummary, ...],
        status: MultiAgentRunStatus,
        evidence_count: int,
        task_count: int,
        questions: tuple[str, ...],
    ) -> None:
        for summary in summaries:
            events.append(
                event(
                    "agent_completed",
                    {
                        "agent_name": summary.agent_name,
                        "role": summary.role.value,
                        "status": summary.status.value,
                        "completed_tasks": summary.completed_tasks,
                        "failed_tasks": summary.failed_tasks,
                        "skipped_tasks": summary.skipped_tasks,
                    },
                )
            )
        if status == MultiAgentRunStatus.FAILED:
            events.append(
                event(
                    "run_failed",
                    {"run_id": context.run_id, "open_questions": list(questions)},
                )
            )
        events.append(
            event(
                "run_completed",
                {
                    "run_id": context.run_id,
                    "status": status.value,
                    "evidence_count": evidence_count,
                    "task_count": task_count,
                },
            )
        )


__all__ = ["MultiAgentCoordinator", "RuntimeProtocol"]
