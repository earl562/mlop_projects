"""Specialist-agent registry with explicit, least-privilege tool boundaries."""

from __future__ import annotations

from collections.abc import Iterable

from plotlot.harness.agents.models import AgentRole, AgentSpec, AgentTask, WorkflowIntent
from plotlot.harness.tool_registry import tool_exists


class UnknownAgentError(KeyError):
    pass


class AgentToolViolationError(ValueError):
    pass


class AgentRegistry:
    def __init__(self, specs: Iterable[AgentSpec]) -> None:
        spec_list = list(specs)
        self._specs = {spec.name: spec for spec in spec_list}
        if len(self._specs) != len(spec_list):
            raise ValueError("agent names must be unique")
        for spec in spec_list:
            missing = sorted(tool for tool in spec.allowed_tools if not tool_exists(tool))
            if missing:
                raise ValueError(f"agent {spec.name!r} references unknown tools: {missing}")

    def get(self, name: str) -> AgentSpec:
        try:
            return self._specs[name]
        except KeyError as exc:
            raise UnknownAgentError(name) from exc

    def list(self) -> tuple[AgentSpec, ...]:
        return tuple(self._specs.values())

    def for_workflow(self, workflow: WorkflowIntent) -> tuple[AgentSpec, ...]:
        return tuple(spec for spec in self._specs.values() if workflow in spec.workflows)

    def validate_task(self, task: AgentTask) -> None:
        spec = self.get(task.agent_name)
        if task.tool_name not in spec.allowed_tools:
            raise AgentToolViolationError(
                f"agent {spec.name!r} may not call tool {task.tool_name!r}"
            )


def default_agent_specs() -> tuple[AgentSpec, ...]:
    site_workflows = (
        WorkflowIntent.SITE_FEASIBILITY,
        WorkflowIntent.DEEP_UNDERWRITING,
    )
    all_workflows = tuple(WorkflowIntent)
    return (
        AgentSpec(
            name="site_identity",
            role=AgentRole.SITE_IDENTITY,
            description="Resolve the site and establish county parcel facts.",
            allowed_tools=("geocode_address", "lookup_property_info"),
            workflows=site_workflows,
            max_parallel_tasks=2,
        ),
        AgentSpec(
            name="zoning_research",
            role=AgentRole.ZONING_RESEARCH,
            description=(
                "Retrieve ordinance and public-data evidence for the governing jurisdiction."
            ),
            allowed_tools=(
                "search_zoning_ordinance",
                "search_ordinances",
                "fetch_ordinance_section",
                "search_municode_live",
                "discover_municode_authorities",
                "discover_code_authorities",
                "search_code_authority_live",
                "discover_open_data_layers",
                "web_search",
            ),
            workflows=site_workflows,
            max_parallel_tasks=3,
        ),
        AgentSpec(
            name="feasibility",
            role=AgentRole.FEASIBILITY,
            description="Run deterministic site feasibility and supporting arithmetic.",
            allowed_tools=("analyze_property", "calculate"),
            workflows=site_workflows,
            max_parallel_tasks=2,
        ),
        AgentSpec(
            name="underwriting",
            role=AgentRole.UNDERWRITING,
            description="Evaluate entitlement scenarios and deterministic financial assumptions.",
            allowed_tools=("analyze_upzoning", "calculate"),
            workflows=(WorkflowIntent.DEEP_UNDERWRITING,),
            max_parallel_tasks=2,
        ),
        AgentSpec(
            name="sourcing",
            role=AgentRole.SOURCING,
            description="Search, filter, summarize, and screen acquisition candidates.",
            allowed_tools=(
                "search_properties",
                "filter_dataset",
                "get_dataset_info",
                "screen_properties",
            ),
            workflows=(WorkflowIntent.LEAD_SOURCING,),
            max_parallel_tasks=3,
        ),
        AgentSpec(
            name="reporting",
            role=AgentRole.REPORTING,
            description="Create evidence-backed internal artifacts and approval-gated exports.",
            allowed_tools=(
                "generate_document",
                "draft_google_doc",
                "draft_email",
                "create_spreadsheet",
                "create_document",
                "export_dataset",
                "gmail_send_draft",
            ),
            workflows=all_workflows,
            max_parallel_tasks=1,
        ),
    )


def build_default_agent_registry() -> AgentRegistry:
    return AgentRegistry(default_agent_specs())


__all__ = [
    "AgentRegistry",
    "AgentToolViolationError",
    "UnknownAgentError",
    "build_default_agent_registry",
    "default_agent_specs",
]
