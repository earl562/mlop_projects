"""Repeatable plan and live-run benchmarks for sanitized property lead fixtures."""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from plotlot.domain.types import ToolContext
from plotlot.evaluation.leads import LeadEvaluationCase
from plotlot.harness.agents import (
    AgentPlan,
    MultiAgentPlanner,
    MultiAgentRunRequest,
    MultiAgentRunResult,
    WorkflowIntent,
    build_default_agent_registry,
)


class PlannerProtocol(Protocol):
    def build(self, request: MultiAgentRunRequest) -> AgentPlan: ...


class CoordinatorProtocol(Protocol):
    async def run(
        self,
        request: MultiAgentRunRequest,
        context: ToolContext,
    ) -> MultiAgentRunResult: ...


class LeadPlanEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    address: str
    market: str
    workflow: WorkflowIntent
    task_count: int = Field(ge=0)
    agent_names: tuple[str, ...]
    open_questions: tuple[str, ...]


class LeadLiveEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    address: str
    market: str
    workflow: WorkflowIntent
    status: str
    evidence_count: int = Field(ge=0)
    open_questions: tuple[str, ...]
    elapsed_seconds: float = Field(ge=0)
    task_statuses: dict[str, str]


class LeadBenchmarkSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "1.0"
    generated_at: str
    case_count: int = Field(ge=0)
    market_counts: dict[str, int]
    workflow_counts: dict[str, int]
    plan_results: tuple[LeadPlanEvaluation, ...] = ()
    live_results: tuple[LeadLiveEvaluation, ...] = ()


def format_case_address(case: LeadEvaluationCase) -> str:
    parts = [case.address]
    if case.city and case.city.casefold() not in case.address.casefold():
        parts.append(case.city)
    if case.state and case.state.casefold() not in case.address.casefold():
        parts.append(case.state)
    return ", ".join(parts)


def case_market(case: LeadEvaluationCase) -> str:
    if case.county and case.state:
        return f"{case.county}, {case.state}"
    if case.city and case.state:
        return f"{case.city}, {case.state}"
    return case.state or "unknown"


def request_for_case(case: LeadEvaluationCase) -> MultiAgentRunRequest:
    workflow = WorkflowIntent(case.workflow)
    assumptions: dict[str, Any] = {}
    if case.asking_price is not None:
        assumptions["purchase_price"] = case.asking_price
    if case.lot_size_sqft is not None:
        assumptions["lot_sqft"] = case.lot_size_sqft
    if case.zoning_hint:
        assumptions["zoning_hint"] = case.zoning_hint
    return MultiAgentRunRequest(
        workflow=workflow,
        objective=(
            "Evaluate this property for zoning feasibility, evidence quality, "
            "and acquisition diligence."
        ),
        address=format_case_address(case),
        assumptions=assumptions,
    )


def build_plan_benchmark(
    cases: Sequence[LeadEvaluationCase],
    *,
    planner: PlannerProtocol | None = None,
    generated_at: datetime | None = None,
) -> LeadBenchmarkSummary:
    effective_planner = planner or MultiAgentPlanner(build_default_agent_registry())
    results: list[LeadPlanEvaluation] = []
    market_counts: Counter[str] = Counter()
    workflow_counts: Counter[str] = Counter()

    for case in cases:
        request = request_for_case(case)
        plan = effective_planner.build(request)
        market = case_market(case)
        market_counts[market] += 1
        workflow_counts[request.workflow.value] += 1
        results.append(
            LeadPlanEvaluation(
                case_id=case.case_id,
                address=request.address or case.address,
                market=market,
                workflow=request.workflow,
                task_count=len(plan.tasks),
                agent_names=tuple(
                    dict.fromkeys(task.agent_name for task in plan.tasks)
                ),
                open_questions=plan.open_questions,
            )
        )

    timestamp = generated_at or datetime.now(timezone.utc)
    return LeadBenchmarkSummary(
        generated_at=timestamp.isoformat(),
        case_count=len(cases),
        market_counts=dict(sorted(market_counts.items())),
        workflow_counts=dict(sorted(workflow_counts.items())),
        plan_results=tuple(results),
    )


async def run_live_benchmark(
    cases: Sequence[LeadEvaluationCase],
    *,
    coordinator: CoordinatorProtocol,
    workspace_id: str = "drive-lead-benchmark",
    actor_user_id: str = "benchmark",
    risk_budget_cents: int = 100,
    live_network_allowed: bool = True,
    generated_at: datetime | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> LeadBenchmarkSummary:
    results: list[LeadLiveEvaluation] = []
    market_counts: Counter[str] = Counter()
    workflow_counts: Counter[str] = Counter()

    for case in cases:
        request = request_for_case(case)
        market = case_market(case)
        market_counts[market] += 1
        workflow_counts[request.workflow.value] += 1
        started = clock()
        run_result = await coordinator.run(
            request,
            ToolContext(
                workspace_id=workspace_id,
                actor_user_id=actor_user_id,
                run_id=f"benchmark_{case.case_id}",
                risk_budget_cents=risk_budget_cents,
                live_network_allowed=live_network_allowed,
                approved_approval_ids=set(),
            ),
        )
        results.append(
            LeadLiveEvaluation(
                case_id=case.case_id,
                address=request.address or case.address,
                market=market,
                workflow=request.workflow,
                status=run_result.status.value,
                evidence_count=len(run_result.evidence_ids),
                open_questions=run_result.open_questions,
                elapsed_seconds=max(0.0, clock() - started),
                task_statuses={
                    task.task_id: task.status.value
                    for task in run_result.task_results
                },
            )
        )

    timestamp = generated_at or datetime.now(timezone.utc)
    return LeadBenchmarkSummary(
        generated_at=timestamp.isoformat(),
        case_count=len(cases),
        market_counts=dict(sorted(market_counts.items())),
        workflow_counts=dict(sorted(workflow_counts.items())),
        live_results=tuple(results),
    )


__all__ = [
    "CoordinatorProtocol",
    "LeadBenchmarkSummary",
    "LeadLiveEvaluation",
    "LeadPlanEvaluation",
    "PlannerProtocol",
    "build_plan_benchmark",
    "case_market",
    "format_case_address",
    "request_for_case",
    "run_live_benchmark",
]
