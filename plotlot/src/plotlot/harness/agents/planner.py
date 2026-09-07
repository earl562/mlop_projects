"""Deterministic workflow planner for PlotLot specialist agents."""

from __future__ import annotations

from typing import Any

from plotlot.harness.agents.models import (
    AgentPlan,
    AgentTask,
    MultiAgentRunRequest,
    OutputBinding,
    WorkflowIntent,
)
from plotlot.harness.agents.registry import AgentRegistry


_SEARCH_BUY_BOX_KEYS = {
    "land_use_type",
    "min_lot_size_sqft",
    "max_lot_size_sqft",
    "min_sale_price",
    "max_sale_price",
    "min_assessed_value",
    "max_assessed_value",
    "year_built_before",
    "year_built_after",
    "owner_name_contains",
    "ownership_min_years",
    "max_results",
}
_SCREEN_BUY_BOX_KEYS = {
    "states",
    "counties",
    "zoning_prefixes",
    "min_lot_sqft",
    "max_lot_sqft",
    "min_units",
    "min_residual",
    "require_verified",
    "exclude_high_flood_risk",
    "max_results",
}
_UPZONING_KEYS = {
    "lot_sqft",
    "value_per_lot",
    "purchase_price",
    "entitlement_soft_costs",
    "baseline_yield",
    "upzoned_yield",
    "baseline_min_lot_area_sqft",
    "upzoned_min_lot_area_sqft",
    "yield_basis",
    "min_lot_width_ft",
    "lot_frontage_ft",
    "value_source",
}


class MultiAgentPlanner:
    def __init__(self, registry: AgentRegistry) -> None:
        self._registry = registry

    def build(self, request: MultiAgentRunRequest) -> AgentPlan:
        if request.workflow == WorkflowIntent.SITE_FEASIBILITY:
            return self._site_plan(request, underwriting=False)
        if request.workflow == WorkflowIntent.DEEP_UNDERWRITING:
            return self._site_plan(request, underwriting=True)
        return self._sourcing_plan(request)

    def _validated(self, task: AgentTask) -> AgentTask:
        self._registry.validate_task(task)
        return task

    def _site_plan(self, request: MultiAgentRunRequest, *, underwriting: bool) -> AgentPlan:
        address = request.address or ""
        tasks: list[AgentTask] = [
            self._validated(
                AgentTask(
                    task_id="identity.geocode",
                    agent_name="site_identity",
                    tool_name="geocode_address",
                    arguments={"address": address},
                )
            ),
            self._validated(
                AgentTask(
                    task_id="identity.parcel",
                    agent_name="site_identity",
                    tool_name="lookup_property_info",
                    arguments={"address": address},
                    bindings={
                        "address": OutputBinding(
                            source_task_id="identity.geocode",
                            path="result.formatted_address",
                            required=False,
                            default=address,
                        ),
                        "county": OutputBinding(
                            source_task_id="identity.geocode",
                            path="result.county",
                        ),
                        "state": OutputBinding(
                            source_task_id="identity.geocode",
                            path="result.state",
                            required=False,
                            default="",
                        ),
                        "lat": OutputBinding(
                            source_task_id="identity.geocode",
                            path="result.lat",
                        ),
                        "lng": OutputBinding(
                            source_task_id="identity.geocode",
                            path="result.lng",
                        ),
                    },
                    depends_on=("identity.geocode",),
                )
            ),
            self._validated(
                AgentTask(
                    task_id="feasibility.analyze",
                    agent_name="feasibility",
                    tool_name="analyze_property",
                    arguments={"address": address},
                    depends_on=("identity.geocode",),
                )
            ),
            self._validated(
                AgentTask(
                    task_id="zoning.research",
                    agent_name="zoning_research",
                    tool_name="search_zoning_ordinance",
                    bindings={
                        "municipality": OutputBinding(
                            source_task_id="identity.parcel",
                            path="result.municipality",
                        ),
                        "query": OutputBinding(
                            source_task_id="identity.parcel",
                            path="result.zoning_code",
                            required=False,
                            default="zoning",
                            suffix=" setbacks density height allowed uses parking",
                        ),
                    },
                    depends_on=("identity.parcel",),
                    optional=True,
                )
            ),
        ]
        open_questions: list[str] = []
        primary_task_id = "feasibility.analyze"

        if underwriting:
            target_supplied = any(
                request.assumptions.get(key) is not None
                for key in ("upzoned_yield", "upzoned_min_lot_area_sqft")
            )
            if target_supplied:
                arguments = {
                    key: value
                    for key, value in request.assumptions.items()
                    if key in _UPZONING_KEYS and value is not None
                }
                bindings: dict[str, OutputBinding] = {}
                if "lot_sqft" not in arguments:
                    bindings["lot_sqft"] = OutputBinding(
                        source_task_id="feasibility.analyze",
                        path="lot_size_sqft",
                    )
                if "baseline_yield" not in arguments:
                    bindings["baseline_yield"] = OutputBinding(
                        source_task_id="feasibility.analyze",
                        path="by_right.max_units",
                        required=False,
                    )
                tasks.append(
                    self._validated(
                        AgentTask(
                            task_id="underwriting.upzoning",
                            agent_name="underwriting",
                            tool_name="analyze_upzoning",
                            arguments=arguments,
                            bindings=bindings,
                            depends_on=("feasibility.analyze",),
                        )
                    )
                )
                primary_task_id = "underwriting.upzoning"
                if request.assumptions.get("value_per_lot") is None:
                    open_questions.append(
                        "Provide a comp-supported value per finished lot to price "
                        "entitlement equity."
                    )
            else:
                open_questions.append(
                    "Provide a target yield or target minimum lot area for the "
                    "entitlement scenario."
                )

        if request.include_report:
            dependencies = ["feasibility.analyze", "zoning.research"]
            if any(task.task_id == "underwriting.upzoning" for task in tasks):
                dependencies.append("underwriting.upzoning")
            tasks.append(
                self._validated(
                    AgentTask(
                        task_id="report.generate",
                        agent_name="reporting",
                        tool_name="generate_document",
                        arguments={
                            "title": request.report_title
                            or f"PlotLot {request.workflow.value.replace('_', ' ').title()}"
                        },
                        depends_on=tuple(dependencies),
                        dependency_mode="all_terminal",
                        required_success_dependencies=("feasibility.analyze",),
                        optional=True,
                        collect_evidence=True,
                    )
                )
            )

        return AgentPlan(
            workflow=request.workflow,
            objective=request.objective,
            tasks=tuple(tasks),
            primary_task_id=primary_task_id,
            open_questions=tuple(open_questions),
        )

    def _sourcing_plan(self, request: MultiAgentRunRequest) -> AgentPlan:
        tasks: list[AgentTask] = []
        open_questions: list[str] = []
        primary_task_id: str | None = None

        if request.market and request.market.county:
            market = request.market
            search_args: dict[str, Any] = {"county": market.county}
            if market.state:
                search_args["state"] = market.state
            if market.city:
                search_args["city"] = market.city
            if market.lat is not None:
                search_args["lat"] = market.lat
            if market.lng is not None:
                search_args["lng"] = market.lng
            search_args.update(
                {
                    key: value
                    for key, value in request.buy_box.items()
                    if key in _SEARCH_BUY_BOX_KEYS and value is not None
                }
            )
            # Accept the shorter lot-size names used by screen_properties as aliases.
            if "min_lot_size_sqft" not in search_args and request.buy_box.get("min_lot_sqft"):
                search_args["min_lot_size_sqft"] = request.buy_box["min_lot_sqft"]
            if "max_lot_size_sqft" not in search_args and request.buy_box.get("max_lot_sqft"):
                search_args["max_lot_size_sqft"] = request.buy_box["max_lot_sqft"]

            tasks.extend(
                [
                    self._validated(
                        AgentTask(
                            task_id="sourcing.search",
                            agent_name="sourcing",
                            tool_name="search_properties",
                            arguments=search_args,
                        )
                    ),
                    self._validated(
                        AgentTask(
                            task_id="sourcing.dataset",
                            agent_name="sourcing",
                            tool_name="get_dataset_info",
                            depends_on=("sourcing.search",),
                        )
                    ),
                ]
            )
            primary_task_id = "sourcing.search"

        if request.addresses:
            screen_args: dict[str, Any] = {
                "addresses": request.addresses,
                **{
                    key: value
                    for key, value in request.buy_box.items()
                    if key in _SCREEN_BUY_BOX_KEYS and value is not None
                },
            }
            if "min_lot_sqft" not in screen_args and request.buy_box.get("min_lot_size_sqft"):
                screen_args["min_lot_sqft"] = request.buy_box["min_lot_size_sqft"]
            if "max_lot_sqft" not in screen_args and request.buy_box.get("max_lot_size_sqft"):
                screen_args["max_lot_sqft"] = request.buy_box["max_lot_size_sqft"]
            if request.market:
                if "states" not in screen_args and request.market.state:
                    screen_args["states"] = [request.market.state]
                if "counties" not in screen_args and request.market.county:
                    screen_args["counties"] = [request.market.county]
            tasks.append(
                self._validated(
                    AgentTask(
                        task_id="sourcing.screen",
                        agent_name="sourcing",
                        tool_name="screen_properties",
                        arguments=screen_args,
                    )
                )
            )
            primary_task_id = "sourcing.screen"

        if request.include_report:
            dependencies = tuple(task.task_id for task in tasks)
            tasks.append(
                self._validated(
                    AgentTask(
                        task_id="report.generate",
                        agent_name="reporting",
                        tool_name="generate_document",
                        arguments={"title": request.report_title or "PlotLot Lead Sourcing Report"},
                        depends_on=dependencies,
                        dependency_mode="all_terminal",
                        required_success_dependencies=(primary_task_id,) if primary_task_id else (),
                        optional=True,
                        collect_evidence=True,
                    )
                )
            )

        return AgentPlan(
            workflow=request.workflow,
            objective=request.objective,
            tasks=tuple(tasks),
            primary_task_id=primary_task_id,
            open_questions=tuple(open_questions),
        )


__all__ = ["MultiAgentPlanner"]
