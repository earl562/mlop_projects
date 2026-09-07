from __future__ import annotations

import pytest
from pydantic import ValidationError

from plotlot.harness.agents.models import (
    MarketScope,
    MultiAgentRunRequest,
    WorkflowIntent,
)
from plotlot.harness.agents.planner import MultiAgentPlanner
from plotlot.harness.agents.registry import build_default_agent_registry


def _planner() -> MultiAgentPlanner:
    return MultiAgentPlanner(build_default_agent_registry())


def test_site_feasibility_plan_decomposes_identity_analysis_and_zoning():
    plan = _planner().build(
        MultiAgentRunRequest(
            workflow=WorkflowIntent.SITE_FEASIBILITY,
            objective="Can I build apartments here?",
            address="123 Main St, Charlotte, NC",
            include_report=True,
        )
    )

    tasks = {task.task_id: task for task in plan.tasks}
    assert plan.primary_task_id == "feasibility.analyze"
    assert tasks["identity.geocode"].depends_on == ()
    assert tasks["identity.parcel"].depends_on == ("identity.geocode",)
    assert tasks["feasibility.analyze"].depends_on == ("identity.geocode",)
    assert tasks["zoning.research"].depends_on == ("identity.parcel",)
    assert tasks["report.generate"].dependency_mode == "all_terminal"
    assert tasks["report.generate"].collect_evidence is True


def test_deep_underwriting_binds_verified_lot_and_baseline_into_upzoning():
    plan = _planner().build(
        MultiAgentRunRequest(
            workflow=WorkflowIntent.DEEP_UNDERWRITING,
            objective="Test a four-lot entitlement scenario",
            address="123 Main St, Charlotte, NC",
            assumptions={"upzoned_yield": 4, "value_per_lot": 300_000},
        )
    )

    task = next(task for task in plan.tasks if task.task_id == "underwriting.upzoning")
    assert task.depends_on == ("feasibility.analyze",)
    assert task.arguments["upzoned_yield"] == 4
    assert task.bindings["lot_sqft"].path == "lot_size_sqft"
    assert task.bindings["baseline_yield"].path == "by_right.max_units"
    assert plan.primary_task_id == "underwriting.upzoning"


def test_deep_underwriting_without_target_records_open_question_instead_of_guessing():
    plan = _planner().build(
        MultiAgentRunRequest(
            workflow=WorkflowIntent.DEEP_UNDERWRITING,
            objective="Underwrite this parcel",
            address="123 Main St, Charlotte, NC",
        )
    )

    assert all(task.task_id != "underwriting.upzoning" for task in plan.tasks)
    assert any("target yield" in question.lower() for question in plan.open_questions)


def test_lead_sourcing_can_search_market_and_screen_supplied_addresses_in_parallel():
    plan = _planner().build(
        MultiAgentRunRequest(
            workflow=WorkflowIntent.LEAD_SOURCING,
            objective="Find infill lots",
            addresses=["1 Main St", "2 Main St"],
            market=MarketScope(county="Broward", state="fl", city="Hollywood"),
            buy_box={"min_lot_sqft": 8_000, "min_units": 4},
        )
    )

    tasks = {task.task_id: task for task in plan.tasks}
    assert tasks["sourcing.search"].depends_on == ()
    assert tasks["sourcing.screen"].depends_on == ()
    assert tasks["sourcing.dataset"].depends_on == ("sourcing.search",)
    assert tasks["sourcing.search"].arguments["state"] == "FL"
    assert tasks["sourcing.screen"].arguments["addresses"] == ["1 Main St", "2 Main St"]


def test_workflow_request_rejects_missing_required_scope():
    with pytest.raises(ValidationError):
        MultiAgentRunRequest(
            workflow=WorkflowIntent.SITE_FEASIBILITY,
            objective="Analyze it",
        )

    with pytest.raises(ValidationError):
        MultiAgentRunRequest(
            workflow=WorkflowIntent.LEAD_SOURCING,
            objective="Find land",
        )
