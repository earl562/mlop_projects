"""Typed contracts for PlotLot multi-agent workflow orchestration."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class WorkflowIntent(StrEnum):
    SITE_FEASIBILITY = "site_feasibility"
    LEAD_SOURCING = "lead_sourcing"
    DEEP_UNDERWRITING = "deep_underwriting"


class AgentRole(StrEnum):
    SITE_IDENTITY = "site_identity"
    ZONING_RESEARCH = "zoning_research"
    FEASIBILITY = "feasibility"
    UNDERWRITING = "underwriting"
    SOURCING = "sourcing"
    REPORTING = "reporting"


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    PENDING_APPROVAL = "pending_approval"
    SKIPPED = "skipped"


class MultiAgentRunStatus(StrEnum):
    COMPLETED = "completed"
    NEEDS_REVIEW = "needs_review"
    PENDING_APPROVAL = "pending_approval"
    FAILED = "failed"


DependencyMode = Literal["all_success", "all_terminal"]


class MarketScope(BaseModel):
    model_config = ConfigDict(frozen=True)

    county: str | None = Field(default=None, min_length=1, max_length=120)
    state: str | None = Field(default=None, min_length=2, max_length=2)
    city: str | None = Field(default=None, min_length=1, max_length=120)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)

    @field_validator("county", "city", mode="before")
    @classmethod
    def _strip_optional_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("state", mode="before")
    @classmethod
    def _normalize_state(cls, value: Any) -> Any:
        return value.strip().upper() if isinstance(value, str) else value


class MultiAgentRunRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    workflow: WorkflowIntent
    objective: str = Field(min_length=1, max_length=1_000)
    address: str | None = Field(default=None, min_length=3, max_length=240)
    addresses: list[str] = Field(default_factory=list, max_length=20)
    market: MarketScope | None = None
    buy_box: dict[str, Any] = Field(default_factory=dict)
    assumptions: dict[str, Any] = Field(default_factory=dict)
    include_report: bool = False
    report_title: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("objective", "address", "report_title", mode="before")
    @classmethod
    def _strip_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("addresses", mode="before")
    @classmethod
    def _normalize_addresses(cls, value: Any) -> Any:
        if value is None:
            return []
        if not isinstance(value, list):
            return value
        unique: list[str] = []
        seen: set[str] = set()
        for raw in value:
            if not isinstance(raw, str):
                continue
            address = raw.strip()
            key = address.casefold()
            if address and key not in seen:
                seen.add(key)
                unique.append(address)
        return unique[:20]

    @model_validator(mode="after")
    def _require_workflow_scope(self) -> "MultiAgentRunRequest":
        if (
            self.workflow
            in {
                WorkflowIntent.SITE_FEASIBILITY,
                WorkflowIntent.DEEP_UNDERWRITING,
            }
            and not self.address
        ):
            raise ValueError(f"{self.workflow.value} requires address")
        if (
            self.workflow == WorkflowIntent.LEAD_SOURCING
            and not self.addresses
            and not (self.market and self.market.county)
        ):
            raise ValueError("lead_sourcing requires addresses or market.county")
        return self


class AgentSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    role: AgentRole
    description: str = Field(min_length=1)
    allowed_tools: tuple[str, ...] = Field(min_length=1)
    workflows: tuple[WorkflowIntent, ...] = Field(min_length=1)
    max_parallel_tasks: int = Field(default=1, ge=1, le=8)


class OutputBinding(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_task_id: str = Field(min_length=1)
    path: str = Field(min_length=1)
    required: bool = True
    default: Any = None
    prefix: str = ""
    suffix: str = ""


class AgentTask(BaseModel):
    model_config = ConfigDict(frozen=True)

    task_id: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_.-]*$")
    agent_name: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    bindings: dict[str, OutputBinding] = Field(default_factory=dict)
    depends_on: tuple[str, ...] = ()
    dependency_mode: DependencyMode = "all_success"
    required_success_dependencies: tuple[str, ...] = ()
    optional: bool = False
    collect_evidence: bool = False

    @model_validator(mode="after")
    def _validate_dependencies(self) -> "AgentTask":
        if self.task_id in self.depends_on:
            raise ValueError("task cannot depend on itself")
        unknown_required = set(self.required_success_dependencies).difference(self.depends_on)
        if unknown_required:
            raise ValueError(
                "required_success_dependencies must be declared dependencies: "
                f"{sorted(unknown_required)}"
            )
        for binding in self.bindings.values():
            if binding.source_task_id not in self.depends_on:
                raise ValueError(
                    f"binding source {binding.source_task_id!r} must be a declared dependency"
                )
        return self


class AgentPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    workflow: WorkflowIntent
    objective: str
    tasks: tuple[AgentTask, ...]
    primary_task_id: str | None = None
    open_questions: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _validate_dag(self) -> "AgentPlan":
        task_by_id = {task.task_id: task for task in self.tasks}
        if len(task_by_id) != len(self.tasks):
            raise ValueError("task IDs must be unique")
        if self.primary_task_id and self.primary_task_id not in task_by_id:
            raise ValueError("primary_task_id must reference a task")
        for task in self.tasks:
            missing = set(task.depends_on).difference(task_by_id)
            if missing:
                raise ValueError(f"task {task.task_id!r} has unknown dependencies: {missing}")

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(task_id: str) -> None:
            if task_id in visited:
                return
            if task_id in visiting:
                raise ValueError("agent plan contains a dependency cycle")
            visiting.add(task_id)
            for dependency in task_by_id[task_id].depends_on:
                visit(dependency)
            visiting.remove(task_id)
            visited.add(task_id)

        for task_id in task_by_id:
            visit(task_id)
        return self


class AgentTaskResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    task_id: str
    agent_name: str
    tool_name: str
    status: TaskStatus
    runtime_status: str | None = None
    result: dict[str, Any] | None = None
    message: str | None = None
    approval_id: str | None = None
    evidence_ids: tuple[str, ...] = ()
    artifacts: dict[str, Any] = Field(default_factory=dict)


class AgentExecutionSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    agent_name: str
    role: AgentRole
    status: MultiAgentRunStatus
    task_ids: tuple[str, ...]
    completed_tasks: int = 0
    failed_tasks: int = 0
    skipped_tasks: int = 0
    approval_ids: tuple[str, ...] = ()


class MultiAgentRunResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    workflow: WorkflowIntent
    status: MultiAgentRunStatus
    plan: AgentPlan
    task_results: tuple[AgentTaskResult, ...]
    agents: tuple[AgentExecutionSummary, ...]
    evidence_ids: tuple[str, ...] = ()
    artifacts: dict[str, Any] = Field(default_factory=dict)
    open_questions: tuple[str, ...] = ()
    primary_output: dict[str, Any] = Field(default_factory=dict)
    events: tuple[dict[str, Any], ...] = ()
