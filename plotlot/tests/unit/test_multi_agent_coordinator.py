from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from plotlot.domain.types import PolicyDecision, ToolContext
from plotlot.harness.agents.coordinator import MultiAgentCoordinator
from plotlot.harness.agents.models import (
    MultiAgentRunRequest,
    MultiAgentRunStatus,
    TaskStatus,
    WorkflowIntent,
)
from plotlot.harness.runtime import ToolCallResult


@dataclass
class FakeRuntime:
    responses: dict[str, ToolCallResult]
    delay_tools: set[str] | None = None

    def __post_init__(self):
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.active = 0
        self.max_active = 0

    async def call_tool(
        self,
        *,
        tool_name: str,
        tool_args: dict[str, Any],
        context: ToolContext,
        approval_id: str | None = None,
        events=None,
    ) -> ToolCallResult:
        del context, approval_id, events
        self.calls.append((tool_name, tool_args))
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.delay_tools and tool_name in self.delay_tools:
                await asyncio.sleep(0.02)
            return self.responses[tool_name]
        finally:
            self.active -= 1


def _ok(tool: str, payload: dict[str, Any]) -> ToolCallResult:
    return ToolCallResult(
        tool_name=tool,
        decision=PolicyDecision(allowed=True, reason="allowed"),
        status="ok",
        result=payload,
    )


def _context(*, budget: int = 100, network: bool = True) -> ToolContext:
    return ToolContext(
        workspace_id="ws_test",
        actor_user_id="user_test",
        run_id="run_test",
        project_id="project_test",
        risk_budget_cents=budget,
        live_network_allowed=network,
        approved_approval_ids=set(),
    )


def _site_runtime(*, zoning_status: str = "success", include_report: bool = False) -> FakeRuntime:
    responses = {
        "geocode_address": _ok(
            "geocode_address",
            {
                "status": "success",
                "result": {
                    "formatted_address": "123 Main St, Charlotte, NC",
                    "municipality": "Charlotte",
                    "county": "Mecklenburg",
                    "state": "NC",
                    "lat": 35.2,
                    "lng": -80.8,
                },
                "evidence": [{"id": "ev_geocode"}],
            },
        ),
        "lookup_property_info": _ok(
            "lookup_property_info",
            {
                "status": "success",
                "result": {
                    "address": "123 Main St, Charlotte, NC",
                    "municipality": "Charlotte",
                    "county": "Mecklenburg",
                    "zoning_code": "N1-C",
                    "lot_size_sqft": 10_000,
                },
                "evidence": [{"id": "ev_parcel"}],
            },
        ),
        "analyze_property": _ok(
            "analyze_property",
            {
                "status": "success",
                "address": "123 Main St, Charlotte, NC",
                "lot_size_sqft": 10_000,
                "by_right": {"max_units": 4},
                "valuation": {"max_land_price_residual": 700_000},
            },
        ),
        "search_zoning_ordinance": _ok(
            "search_zoning_ordinance",
            {
                "status": zoning_status,
                "results": [] if zoning_status != "success" else [{"section": "4.3"}],
                "evidence": [] if zoning_status != "success" else [{"id": "ev_zone"}],
                "message": "No ordinance text" if zoning_status != "success" else "",
            },
        ),
    }
    if include_report:
        responses["generate_document"] = _ok(
            "generate_document",
            {
                "status": "success",
                "artifacts": {"report": {"status": "draft"}},
            },
        )
    return FakeRuntime(
        responses=responses,
        delay_tools={"lookup_property_info", "analyze_property"},
    )


@pytest.mark.asyncio
async def test_coordinator_executes_independent_specialists_concurrently_and_binds_outputs():
    runtime = _site_runtime()
    coordinator = MultiAgentCoordinator(runtime)

    result = await coordinator.run(
        MultiAgentRunRequest(
            workflow=WorkflowIntent.SITE_FEASIBILITY,
            objective="Can I build four units?",
            address="123 Main St, Charlotte, NC",
        ),
        _context(),
    )

    assert result.status == MultiAgentRunStatus.COMPLETED
    assert runtime.max_active >= 2
    parcel_call = next(args for tool, args in runtime.calls if tool == "lookup_property_info")
    assert parcel_call["county"] == "Mecklenburg"
    assert parcel_call["lat"] == 35.2
    zoning_call = next(args for tool, args in runtime.calls if tool == "search_zoning_ordinance")
    assert zoning_call == {
        "municipality": "Charlotte",
        "query": "N1-C setbacks density height allowed uses parking",
    }
    assert result.primary_output["by_right"]["max_units"] == 4
    assert set(result.evidence_ids) == {"ev_geocode", "ev_parcel", "ev_zone"}
    assert {summary.agent_name for summary in result.agents} == {
        "site_identity",
        "feasibility",
        "zoning_research",
    }


@pytest.mark.asyncio
async def test_optional_research_gap_yields_needs_review_not_false_success_or_total_failure():
    runtime = _site_runtime(zoning_status="no_results")
    coordinator = MultiAgentCoordinator(runtime)

    result = await coordinator.run(
        MultiAgentRunRequest(
            workflow=WorkflowIntent.SITE_FEASIBILITY,
            objective="Can I build four units?",
            address="123 Main St, Charlotte, NC",
        ),
        _context(),
    )

    assert result.status == MultiAgentRunStatus.NEEDS_REVIEW
    task = next(item for item in result.task_results if item.task_id == "zoning.research")
    assert task.status == TaskStatus.FAILED
    assert result.primary_output["by_right"]["max_units"] == 4
    assert any("zoning_research" in question for question in result.open_questions)


@pytest.mark.asyncio
async def test_report_agent_receives_accumulated_evidence_ids():
    runtime = _site_runtime(include_report=True)
    coordinator = MultiAgentCoordinator(runtime)

    result = await coordinator.run(
        MultiAgentRunRequest(
            workflow=WorkflowIntent.SITE_FEASIBILITY,
            objective="Analyze and document the site",
            address="123 Main St, Charlotte, NC",
            include_report=True,
        ),
        _context(),
    )

    report_args = next(args for tool, args in runtime.calls if tool == "generate_document")
    assert set(report_args["evidence_ids"]) == {"ev_geocode", "ev_parcel", "ev_zone"}
    assert result.status == MultiAgentRunStatus.COMPLETED
    assert "report.generate" in result.artifacts


@pytest.mark.asyncio
async def test_pending_approval_stops_dependent_sourcing_task_and_surfaces_approval():
    pending = ToolCallResult(
        tool_name="search_properties",
        decision=PolicyDecision(
            allowed=False,
            approval_required=True,
            approval_id="apr_run_test_search_properties",
            reason="budget required",
        ),
        status="pending_approval",
        message="budget required",
    )
    runtime = FakeRuntime(
        responses={
            "search_properties": pending,
            "get_dataset_info": _ok("get_dataset_info", {"status": "success"}),
        }
    )
    coordinator = MultiAgentCoordinator(runtime)

    result = await coordinator.run(
        MultiAgentRunRequest(
            workflow=WorkflowIntent.LEAD_SOURCING,
            objective="Find lots",
            market={"county": "Broward", "state": "FL"},
        ),
        _context(budget=0),
    )

    assert result.status == MultiAgentRunStatus.PENDING_APPROVAL
    search = next(item for item in result.task_results if item.task_id == "sourcing.search")
    dataset = next(item for item in result.task_results if item.task_id == "sourcing.dataset")
    assert search.status == TaskStatus.PENDING_APPROVAL
    assert search.approval_id == "apr_run_test_search_properties"
    assert dataset.status == TaskStatus.SKIPPED
    assert [tool for tool, _args in runtime.calls] == ["search_properties"]


@pytest.mark.asyncio
async def test_missing_required_binding_skips_only_dependent_task_and_marks_review():
    runtime = _site_runtime()
    runtime.responses["geocode_address"] = _ok(
        "geocode_address",
        {
            "status": "success",
            "result": {
                "formatted_address": "123 Main St, Charlotte, NC",
                "municipality": "Charlotte",
                "state": "NC",
                "lat": 35.2,
                "lng": -80.8,
            },
        },
    )
    coordinator = MultiAgentCoordinator(runtime)

    result = await coordinator.run(
        MultiAgentRunRequest(
            workflow=WorkflowIntent.SITE_FEASIBILITY,
            objective="Analyze",
            address="123 Main St, Charlotte, NC",
        ),
        _context(),
    )

    parcel = next(item for item in result.task_results if item.task_id == "identity.parcel")
    analysis = next(item for item in result.task_results if item.task_id == "feasibility.analyze")
    assert parcel.status == TaskStatus.SKIPPED
    assert analysis.status == TaskStatus.COMPLETED
    assert result.status == MultiAgentRunStatus.NEEDS_REVIEW


@pytest.mark.asyncio
async def test_report_waits_for_research_but_requires_primary_analysis_success():
    runtime = _site_runtime(include_report=True)
    runtime.responses["analyze_property"] = _ok(
        "analyze_property",
        {"status": "error", "message": "analysis failed"},
    )
    coordinator = MultiAgentCoordinator(runtime)

    result = await coordinator.run(
        MultiAgentRunRequest(
            workflow=WorkflowIntent.SITE_FEASIBILITY,
            objective="Analyze and document the site",
            address="123 Main St, Charlotte, NC",
            include_report=True,
        ),
        _context(),
    )

    report = next(item for item in result.task_results if item.task_id == "report.generate")
    assert report.status == TaskStatus.SKIPPED
    assert all(tool != "generate_document" for tool, _args in runtime.calls)
