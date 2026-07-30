from __future__ import annotations

import json
from pathlib import Path

import pytest
from pytest import MonkeyPatch

from plotlot.cli_harness import main
from plotlot.harness.contracts import SourceMode
from plotlot.harness.fixture_runs import FixtureDealRunRequest, run_fixture_deal_analysis
from plotlot.harness.run_store import default_harness_run_store


@pytest.fixture(autouse=True)
def harness_store_path(tmp_path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("PLOTLOT_HARNESS_STORE_PATH", str(tmp_path / "harness-runs.json"))
    monkeypatch.setenv("PLOTLOT_HARNESS_JOB_STORE_PATH", str(tmp_path / "harness-jobs.json"))
    monkeypatch.setenv(
        "PLOTLOT_HARNESS_CALCULATION_STORE_PATH",
        str(tmp_path / "harness-calculations.json"),
    )
    monkeypatch.setenv(
        "PLOTLOT_HARNESS_EVIDENCE_STORE_PATH", str(tmp_path / "harness-evidence.json")
    )
    monkeypatch.setenv("PLOTLOT_HARNESS_REPORT_STORE_PATH", str(tmp_path / "harness-reports.json"))
    monkeypatch.setenv(
        "PLOTLOT_HARNESS_VERIFICATION_STORE_PATH",
        str(tmp_path / "harness-verifications.json"),
    )
    monkeypatch.setenv("PLOTLOT_HARNESS_TOOL_CALL_STORE_PATH", str(tmp_path / "tool-calls.json"))


def test_cli_help_lists_harness_commands(capsys) -> None:
    exit_code = main(["--help"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "plotlot run acquisition-memo" in output
    assert "plotlot scaffold tool" in output
    assert "plotlot tui" in output
    assert "plotlot training discover" in output


def test_cli_gis_search_outputs_json(capsys) -> None:
    exit_code = main(["gis", "search", "zoning", "--county", "Broward", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["source_mode"] == "fixture"
    assert payload["results"][0]["provider"] == "broward_geohub"


def test_cli_training_discover_youtube_fixture(capsys) -> None:
    exit_code = main(
        [
            "training",
            "discover",
            "--url",
            "https://www.youtube.com/watch?v=0IS1iFMJ8sQ",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["videos"][0]["platform_video_id"] == "0IS1iFMJ8sQ"
    assert "offer analysis" in payload["videos"][0]["metadata"]["tags"]


def test_cli_skills_lists_comparable_comping_skill(capsys) -> None:
    exit_code = main(["skills"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    names = {skill["name"] for skill in payload["skills"]}
    assert "comparable_comping" in names


def test_cli_calc_residual_land_value_outputs_json(capsys) -> None:
    payload = {
        "as_built_value": 1_235_000,
        "desired_profit": 150_000,
        "hard_costs": 600_000,
        "soft_costs": 90_000,
        "contingency": 60_000,
        "developer_fee": 30_000,
        "closing_costs": 15_000,
        "financing_costs": 40_000,
        "holding_costs": 20_000,
        "selling_costs": 35_000,
        "asking_price": 175_000,
    }

    exit_code = main(["calc", "residual-land-value", "--json", json.dumps(payload)])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["calculation_type"] == "residual_land_value"
    assert output["formula_version"] == "residual_land_value.v1"
    assert output["max_supportable_land_price"] == 195_000
    assert output["go_no_go_signal"] == "go"


def test_cli_calc_with_run_id_persists_calculation_for_inspection(capsys) -> None:
    payload = {
        "as_built_value": 1_235_000,
        "desired_profit": 150_000,
        "hard_costs": 600_000,
        "soft_costs": 90_000,
        "contingency": 60_000,
        "developer_fee": 30_000,
        "closing_costs": 15_000,
        "financing_costs": 40_000,
        "holding_costs": 20_000,
        "selling_costs": 35_000,
        "asking_price": 175_000,
    }

    calc_exit = main(
        [
            "calc",
            "residual-land-value",
            "--json",
            json.dumps(payload),
            "--run-id",
            "run_fixture_cli_calc",
        ]
    )
    calculation = json.loads(capsys.readouterr().out)
    list_exit = main(["calculations", "list", "--run-id", "run_fixture_cli_calc"])
    listed = json.loads(capsys.readouterr().out)
    show_exit = main(["calculations", "show", calculation["calculation_id"]])
    shown = json.loads(capsys.readouterr().out)

    assert calc_exit == 0
    assert list_exit == 0
    assert show_exit == 0
    assert calculation["run_id"] == "run_fixture_cli_calc"
    assert calculation["outputs"]["max_supportable_land_price"] == 195_000
    assert listed["calculations"][0]["calculation_id"] == calculation["calculation_id"]
    assert shown["calculation_id"] == calculation["calculation_id"]


def test_cli_runs_cancel_updates_queued_run_and_emits_event(capsys) -> None:
    result = run_fixture_deal_analysis(
        FixtureDealRunRequest(
            address="example queued CLI cancellation fixture address",
            analysis_type="acquisition_memo",
            source_mode=SourceMode.FIXTURE,
        )
    ).model_copy(update={"status": "queued"})
    default_harness_run_store().save_run(result)

    cancel_exit = main(
        [
            "runs",
            "cancel",
            str(result.run_id),
            "--reason",
            "Duplicate run.",
            "--actor-user-id",
            "analyst_fixture",
        ]
    )
    cancelled = json.loads(capsys.readouterr().out)
    events_exit = main(["runs", "events", str(result.run_id)])
    events = json.loads(capsys.readouterr().out)

    assert cancel_exit == 0
    assert events_exit == 0
    assert cancelled["status"] == "cancelled"
    assert events["events"][-1]["type"] == "run.cancelled"
    assert events["events"][-1]["payload"]["reason"] == "Duplicate run."


def test_cli_run_acquisition_memo_streams_events(capsys) -> None:
    exit_code = main(
        [
            "run",
            "acquisition-memo",
            "--address",
            "example Miami-Dade fixture address",
            "--source-mode",
            "fixture",
            "--assumption",
            "avgUnitSizeSf=850",
            "--stream",
        ]
    )

    assert exit_code == 0
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert lines[0]["type"] == "run.created"
    assert lines[0]["execution_mode"] == "cli"
    assert lines[-1]["run_id"].startswith("run_fixture_")
    assert lines[-1]["verification_status"] == "passed_with_warnings"


def test_cli_run_miami_gardens_fixture_default_far_runs(capsys) -> None:
    exit_code = main(
        [
            "run",
            "acquisition-memo",
            "--address",
            "45 NW 209 ST, Miami Gardens, FL 33169",
            "--source-mode",
            "fixture",
            "--assumption",
            "avgUnitSizeSf=850",
            "--assumption",
            "efficiencyFactor=0.85",
            "--assumption",
            "targetProfitPct=0.18",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "completed"
    assert payload["source_mode"] == "fixture"
    assert payload["artifacts"]["site"]["municipality"] == "Miami Gardens"
    assert payload["artifacts"]["feasibility"]["area_limiters"] == ["floor_area_ratio"]


def test_cli_run_comparable_comping_executes_comp_only_skill(capsys) -> None:
    exit_code = main(
        [
            "run",
            "comparable-comping",
            "--address",
            "45 NW 209 ST, Miami Gardens, FL 33169",
            "--source-mode",
            "fixture",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    tool_names = {call["tool_name"] for call in payload["tool_calls"]}
    find_comps_call = next(
        call for call in payload["tool_calls"] if call["tool_name"] == "find_comparables"
    )
    calculation_types = {calculation["calculation_type"] for calculation in payload["calculations"]}
    claim_types = {claim["claim_type"] for claim in payload["claims"]}
    land_comp_addresses = {comp["address"] for comp in payload["artifacts"]["comps"]["comparables"]}
    exit_comp_addresses = {
        comp["address"] for comp in payload["artifacts"]["comps"]["unit_comparables"]
    }
    workflow = payload["artifacts"]["comping_workflow"]
    assert payload["analysis_type"] == "comparable_comping"
    assert payload["artifacts"]["site"]["municipality"] == "Miami Gardens"
    assert payload["artifacts"]["site"]["zoning_code"] == "R-1"
    assert workflow["skill_name"] == "comparable_comping"
    assert workflow["agent_role"] == "comping_analyst"
    assert workflow["subject_context"]["source_tool"] == "lookup_property_info"
    assert workflow["subject_context"]["municipality"] == "Miami Gardens"
    assert workflow["subject_context"]["zoning_code"] == "R-1"
    assert "find_comparables" in tool_names
    assert find_comps_call["args"]["municipality"] == "Miami Gardens"
    assert find_comps_call["args"]["zoning_code"] == "R-1"
    assert find_comps_call["args"]["lot_size_sqft"] == 10105.0
    assert "run_residual_land_value" not in tool_names
    assert "residual_land_value" not in calculation_types
    assert "comp_candidate_quality" in claim_types
    assert "comps" in payload["artifacts"]
    assert {
        "17605 NW 19th Avenue, Miami Gardens, FL 33056",
        "2940 NW 169th Ter, Miami Gardens, FL 33056",
        "168 Terrace, Miami Gardens, FL 33056",
    } <= land_comp_addresses
    assert {
        "105 NE 213th St, Miami Gardens, FL 33179",
        "115 NE 213th St, Miami Gardens, FL 33179",
        "100 NW 208th St, Miami Gardens, FL 33169",
    } <= exit_comp_addresses
    assert {
        "17605 NW 19th Avenue, Miami Gardens, FL 33056",
        "2940 NW 169th Ter, Miami Gardens, FL 33056",
        "168 Terrace, Miami Gardens, FL 33056",
    } <= {candidate["address"] for candidate in workflow["accepted_land_comps"]}
    assert workflow["trust_gates"]["underwriting_status"] == "blocked_until_underwriting_skill"
    assert workflow["trust_gates"]["zoning_context_required"] is True


def test_cli_run_allows_live_source_mode_through_shared_executor(
    capsys,
    monkeypatch: MonkeyPatch,
) -> None:
    def _fake_run(request: FixtureDealRunRequest):
        return run_fixture_deal_analysis(
            FixtureDealRunRequest(
                address=request.address,
                analysis_type=request.analysis_type,
                source_mode=SourceMode.FIXTURE,
                execution_mode=request.execution_mode,
                assumptions=request.assumptions,
            )
        ).model_copy(update={"source_mode": SourceMode.LIVE, "preliminary": True})

    monkeypatch.setattr("plotlot.cli_harness_runs.run_deal_analysis", _fake_run)

    exit_code = main(
        [
            "run",
            "acquisition-memo",
            "--address",
            "171 NE 209th Ter, Miami, FL 33179",
            "--source-mode",
            "live",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["source_mode"] == "live"
    assert payload["status"] == "completed"


def test_cli_run_persists_fixture_evidence_for_inspection(capsys) -> None:
    run_exit = main(
        [
            "run",
            "acquisition-memo",
            "--address",
            "example Miami-Dade fixture address",
            "--source-mode",
            "fixture",
        ]
    )
    run_payload = json.loads(capsys.readouterr().out)
    run_id = run_payload["run_id"]

    list_exit = main(["evidence", "list", "--run-id", run_id])
    listed = json.loads(capsys.readouterr().out)
    evidence_id = listed["evidence"][0]["evidence_id"]
    show_exit = main(["evidence", "show", evidence_id])
    shown = json.loads(capsys.readouterr().out)

    assert run_exit == 0
    assert list_exit == 0
    assert show_exit == 0
    assert evidence_id in run_payload["evidence_ids"]
    assert shown["freshness_status"] == "fixture"
    assert shown["applicability"] == "requires_municipal_verification"


def test_cli_fixture_run_preserves_requested_address_in_site_and_parcel_evidence(capsys) -> None:
    requested_address = "45 NW 209 ST, Miami Gardens, FL 33169"

    run_exit = main(
        [
            "run",
            "acquisition-memo",
            "--address",
            requested_address,
            "--source-mode",
            "fixture",
        ]
    )
    run_payload = json.loads(capsys.readouterr().out)

    evidence_exit = main(["evidence", "list", "--run-id", run_payload["run_id"]])
    evidence_payload = json.loads(capsys.readouterr().out)

    parcel_evidence = next(
        item for item in evidence_payload["evidence"] if item["source_type"] == "parcel_record"
    )

    assert run_exit == 0
    assert evidence_exit == 0
    assert run_payload["artifacts"]["site"]["address"] == "45 NW 209 ST"
    assert run_payload["artifacts"]["site"]["municipality"] == "Miami Gardens"
    assert parcel_evidence["structured_payload"]["address"] == "45 NW 209 ST"
    assert "45 NW 209 ST" in parcel_evidence["normalized_text"]


def test_cli_runs_events_and_replay_read_saved_run(capsys) -> None:
    run_exit = main(
        [
            "run",
            "zoning-research",
            "--address",
            "example Broward fixture address",
            "--source-mode",
            "fixture",
        ]
    )
    run_payload = json.loads(capsys.readouterr().out)
    run_id = run_payload["run_id"]

    events_exit = main(["runs", "events", run_id])
    events_payload = json.loads(capsys.readouterr().out)
    replay_exit = main(["runs", "replay", run_id])
    replay_payload = json.loads(capsys.readouterr().out)

    assert run_exit == 0
    assert events_exit == 0
    assert replay_exit == 0
    event_types = [event["type"] for event in events_payload["events"]]
    assert event_types[0] == "run.created"
    assert "tool.completed" in event_types
    assert event_types[-1] == "run.completed"
    assert replay_payload["event_count"] == len(event_types)


def test_cli_jobs_create_run_next_and_events_share_queue(capsys) -> None:
    create_exit = main(
        [
            "jobs",
            "create",
            "--address",
            "example Miami-Dade fixture address",
            "--analysis-type",
            "acquisition-memo",
            "--source-mode",
            "fixture",
        ]
    )
    created = json.loads(capsys.readouterr().out)
    job_id = created["job_id"]

    run_exit = main(["jobs", "run-next"])
    completed = json.loads(capsys.readouterr().out)
    events_exit = main(["jobs", "events", job_id])
    events = json.loads(capsys.readouterr().out)

    assert create_exit == 0
    assert run_exit == 0
    assert events_exit == 0
    assert completed["status"] == "completed"
    assert events["events"][-1]["type"] == "job.completed"


def test_plotlot_console_entrypoint_targets_harness_cli() -> None:
    pyproject = Path("pyproject.toml").read_text()

    assert 'plotlot = "plotlot.cli_harness:entrypoint"' in pyproject
