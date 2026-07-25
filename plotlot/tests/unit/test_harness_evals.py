from __future__ import annotations

import json
from types import SimpleNamespace

from plotlot.cli_harness import main
from plotlot.harness.contracts import SourceMode
from plotlot.harness.evals import run_all_eval_suites, run_eval_suite
from plotlot.harness.eval_suites import _live_address_path_cases, _run_live_address_path_case
from plotlot.harness.fixture_runs import FixtureDealRunResult


def test_harness_eval_suite_checks_fixture_run_trajectory() -> None:
    result = run_eval_suite("harness")

    assert result.suite == "harness"
    assert result.passed is True
    assert result.cases[0].run_id is not None
    assert result.cases[0].metrics["event_count"] >= 10


def test_all_eval_suites_cover_core_fixture_lanes() -> None:
    results = run_all_eval_suites()

    assert {result.suite for result in results} >= {
        "harness",
        "manual-offer-workflows",
        "municode",
        "south-florida-address-paths-live",
        "south-florida-address-paths",
        "south-florida-five-addresses",
        "south-florida-gis",
        "underwriting",
        "training-discovery",
        "health",
    }
    assert all(result.passed for result in results)


def test_south_florida_address_path_eval_covers_miami_dade_and_broward() -> None:
    result = run_eval_suite("south-florida-address-paths")

    assert result.suite == "south-florida-address-paths"
    assert result.passed is True
    assert {case.name for case in result.cases} == {
        "miami_dade_acquisition_path",
        "broward_acquisition_path",
    }
    assert all(case.run_id is not None for case in result.cases)


def test_live_address_path_eval_is_registered_and_skips_cleanly_without_env() -> None:
    result = run_eval_suite("south-florida-address-paths-live")

    assert result.suite == "south-florida-address-paths-live"
    assert result.passed is True
    assert result.cases[0].name == "live_tests_disabled"
    assert result.cases[0].metrics["requires_env"] == "PLOTLOT_LIVE_TESTS=1"


def test_live_address_path_case_allows_insufficient_support_for_weak_land_signal(monkeypatch) -> None:
    case = _live_address_path_cases()[0]
    fake_run = FixtureDealRunResult.model_construct(
        run_id="run_fixture_live_case",
        analysis_type="acquisition_memo",
        status="completed",
        events_url="/api/v1/harness/runs/run_fixture_live_case/events",
        report_id="report_fixture_live_case",
        evidence_ids=["evidence_parcel", "evidence_market_comp"],
        verification_status="passed_with_warnings",
        source_mode=SourceMode.LIVE,
        preliminary=True,
        events=[],
        evidence_items=[
            SimpleNamespace(source_type=SimpleNamespace(value="parcel_record")),
            SimpleNamespace(source_type=SimpleNamespace(value="market_comp")),
        ],
        claims=[],
        calculations=[],
        tool_calls=[
            SimpleNamespace(tool_name="geocode_address"),
            SimpleNamespace(tool_name="lookup_property_info"),
            SimpleNamespace(tool_name="find_comparables"),
            SimpleNamespace(tool_name="compute_feasibility"),
            SimpleNamespace(tool_name="run_pro_forma"),
        ],
        report=None,
        artifacts={
            "property_record": {
                "county": case.county,
                "municipality": case.municipality,
                "zoning_code": case.zoning_code,
                "lot_size_sqft": 10105.0,
            },
            "comps": {
                "comparables": [{"address": "2205 NW 177 TER"}],
                "adv_per_unit": 500000.0,
            },
            "acquisition_guidance": {
                "recommended_action": "insufficient_support",
                "recommended_offer": 0.0,
            },
            "underwriting_mode": {"status": "completed"},
        },
        pipeline_stages=[],
    )

    monkeypatch.setattr("plotlot.harness.eval_suites.run_deal_analysis", lambda request: fake_run)

    result = _run_live_address_path_case(case)

    assert result.passed is True
    assert result.failures == []


def test_manual_offer_eval_covers_conservative_miami_gardens_path() -> None:
    result = run_eval_suite("manual-offer-workflows")

    assert result.suite == "manual-offer-workflows"
    assert result.passed is True

    cases = {case.name: case for case in result.cases}
    assert {"miami_gardens_manual_offer", "broward_manual_offer"} <= set(cases)
    assert cases["miami_gardens_manual_offer"].passed is True
    assert cases["miami_gardens_manual_offer"].run_id is not None


def test_five_address_eval_covers_miami_dade_and_broward_gold_path_cases() -> None:
    result = run_eval_suite("south-florida-five-addresses")

    assert result.suite == "south-florida-five-addresses"
    assert result.passed is True
    assert len(result.cases) == 5
    assert all(case.passed for case in result.cases)
    assert all(case.run_id is not None for case in result.cases)


def test_cli_eval_run_known_suite_outputs_json(capsys) -> None:
    exit_code = main(["eval", "run", "--suite", "training-discovery"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["passed"] is True
    assert payload["result"]["suite"] == "training-discovery"
    assert payload["result"]["cases"][0]["metrics"]["concept_count"] >= 1


def test_cli_eval_run_unknown_suite_returns_nonzero(capsys) -> None:
    exit_code = main(["eval", "run", "--suite", "not-a-suite"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["passed"] is False
    assert payload["result"]["suite"] == "not-a-suite"
    assert payload["result"]["cases"][0]["failures"] == ["unknown eval suite"]
