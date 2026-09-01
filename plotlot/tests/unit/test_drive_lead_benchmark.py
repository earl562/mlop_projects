"""Plan-level and execution-contract tests for the Drive lead benchmark."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from plotlot.evaluation.benchmark import build_plan_benchmark, request_for_case
from plotlot.evaluation.leads import load_lead_fixture
from plotlot.harness.agents import WorkflowIntent


FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "leads"
    / "plotlot_drive_leads.json"
)


def test_every_drive_case_builds_a_valid_multi_agent_plan():
    cases = load_lead_fixture(FIXTURE_PATH)

    benchmark = build_plan_benchmark(
        cases,
        generated_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )

    assert benchmark.case_count == 16
    assert benchmark.market_counts == {
        "Broward, FL": 4,
        "Mecklenburg, NC": 3,
        "Miami-Dade, FL": 4,
        "Palm Beach, FL": 4,
        "San Diego, CA": 1,
    }
    assert benchmark.workflow_counts == {
        "deep_underwriting": 2,
        "site_feasibility": 14,
    }
    assert len(benchmark.plan_results) == 16
    assert all(result.task_count >= 4 for result in benchmark.plan_results)
    assert all("feasibility" in result.agent_names for result in benchmark.plan_results)


def test_benchmark_request_contains_only_property_and_workflow_inputs():
    case = load_lead_fixture(FIXTURE_PATH)[0]

    request = request_for_case(case)
    payload = request.model_dump(mode="json")
    serialized = str(payload).casefold()

    assert request.workflow == WorkflowIntent.SITE_FEASIBILITY
    assert request.address == "1706-1708 Dewey St # 1-2, Hollywood, FL"
    assert "email" not in serialized
    assert "phone" not in serialized
    assert "owner" not in serialized
    assert "contact" not in serialized


def test_price_is_a_user_assumption_not_an_agent_invention():
    cases = load_lead_fixture(FIXTURE_PATH)
    priced_case = next(case for case in cases if case.asking_price is not None)

    request = request_for_case(priced_case)

    assert request.workflow == WorkflowIntent.DEEP_UNDERWRITING
    assert request.assumptions["purchase_price"] == priced_case.asking_price
