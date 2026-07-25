from __future__ import annotations

import json

import pytest
from pytest import MonkeyPatch

from plotlot.cli_harness import main


@pytest.fixture(autouse=True)
def harness_tui_paths(tmp_path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("PLOTLOT_HARNESS_STORE_PATH", str(tmp_path / "harness-runs.json"))
    monkeypatch.setenv(
        "PLOTLOT_HARNESS_EVIDENCE_STORE_PATH", str(tmp_path / "harness-evidence.json")
    )
    monkeypatch.setenv("PLOTLOT_HARNESS_REPORT_STORE_PATH", str(tmp_path / "harness-reports.json"))
    monkeypatch.setenv(
        "PLOTLOT_HARNESS_VERIFICATION_STORE_PATH",
        str(tmp_path / "harness-verifications.json"),
    )
    monkeypatch.setenv("PLOTLOT_HARNESS_TOOL_CALL_STORE_PATH", str(tmp_path / "tool-calls.json"))
    monkeypatch.setenv(
        "PLOTLOT_HARNESS_APPROVAL_STORE_PATH",
        str(tmp_path / "harness-approvals.json"),
    )
    monkeypatch.setenv(
        "PLOTLOT_HARNESS_CALCULATION_STORE_PATH",
        str(tmp_path / "harness-calculations.json"),
    )
    monkeypatch.setenv("PLOTLOT_HARNESS_MEMORY_STORE_PATH", str(tmp_path / "harness-memory.json"))


def test_cli_tui_home_renders_terminal_workbench(capsys) -> None:
    exit_code = main(["tui"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "PlotLot TUI Workbench" in output
    assert "Run Monitor" in output
    assert "Training Corpus" in output


def test_cli_tui_home_json_lists_operator_screens(capsys) -> None:
    exit_code = main(["tui", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["screen"] == "home"
    assert "run-monitor" in payload["summary"]["screens"]
    assert "approvals" in payload["summary"]["screens"]
    assert payload["summary"]["source_mode"] == "fixture"


def test_cli_tui_run_monitor_reads_persisted_run_state(capsys) -> None:
    run_id = _create_fixture_run(capsys)

    exit_code = main(["tui", "--screen", "run-monitor", "--run-id", run_id, "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["screen"] == "run_monitor"
    assert payload["summary"]["run_id"] == run_id
    assert payload["summary"]["event_count"] >= 2
    assert payload["summary"]["verification_status"] == "passed_with_warnings"
    assert payload["summary"]["comp_support_status"] == "passed"
    assert payload["summary"]["combined_support_tier"] != "unknown"
    assert payload["summary"]["land_support_source"] != "unknown"
    assert payload["summary"]["jurisdiction_alignment_status"] in {"passed", "warning"}
    assert payload["summary"]["jurisdiction_mismatch_count"] >= 0


def test_cli_tui_inspection_screens_share_persisted_ledgers(capsys) -> None:
    run_id = _create_fixture_run(capsys)

    evidence_exit = main(["tui", "--screen", "evidence", "--run-id", run_id, "--json"])
    evidence = json.loads(capsys.readouterr().out)
    verification_exit = main(["tui", "--screen", "verification", "--run-id", run_id, "--json"])
    verification = json.loads(capsys.readouterr().out)
    report_exit = main(["tui", "--screen", "report", "--run-id", run_id, "--json"])
    report = json.loads(capsys.readouterr().out)

    assert evidence_exit == 0
    assert verification_exit == 0
    assert report_exit == 0
    assert evidence["summary"]["evidence_count"] >= 1
    assert evidence["panels"][0]["items"][0]["run_id"] == run_id
    assert verification["summary"]["verification_count"] == 1
    assert verification["panels"][0]["items"][0]["status"] == "blocked"
    assert verification["panels"][0]["items"][0]["blocked_checks"] == ["source_mode"]
    assert verification["summary"]["comp_support_status"] == "passed"
    assert verification["summary"]["combined_support_tier"] != "unknown"
    assert verification["summary"]["jurisdiction_alignment_status"] in {"passed", "warning"}
    assert verification["summary"]["jurisdiction_mismatch_count"] >= 0
    assert verification["panels"][1]["items"][0]["land_support_source"] != "unknown"
    assert report["summary"]["report_count"] == 1
    assert report["panels"][0]["items"][0]["status"] == "preliminary"
    assert report["summary"]["comp_support_status"] == "passed"
    assert report["summary"]["combined_support_tier"] != "unknown"
    assert report["panels"][1]["items"][0]["combined_support_tier"] != "unknown"


def test_cli_tui_source_and_training_screens_use_shared_catalogs(capsys) -> None:
    source_exit = main(["tui", "--screen", "source-catalog", "--json"])
    source = json.loads(capsys.readouterr().out)
    training_exit = main(["tui", "--screen", "training", "--json"])
    training = json.loads(capsys.readouterr().out)

    assert source_exit == 0
    assert training_exit == 0
    assert source["summary"]["gis_source_count"] >= 2
    assert training["summary"]["video_count"] >= 1
    assert training["panels"][0]["items"][0]["source_mode"] == "fixture"


def test_cli_tui_approvals_screen_lists_and_approves_pending_request(capsys) -> None:
    run_id = _create_fixture_run(capsys)
    approval_id = _request_fixture_approval(capsys, run_id)

    list_exit = main(["tui", "--screen", "approvals", "--run-id", run_id, "--json"])
    listed = json.loads(capsys.readouterr().out)
    approve_exit = main(
        [
            "tui",
            "--screen",
            "approvals",
            "--approve",
            approval_id,
            "--resolved-by",
            "analyst@example.test",
            "--json",
        ]
    )
    approved = json.loads(capsys.readouterr().out)

    assert list_exit == 0
    assert approve_exit == 0
    assert listed["summary"]["approval_count"] == 1
    assert listed["panels"][0]["items"][0]["status"] == "pending"
    assert approved["summary"]["decision"] == "approved"
    assert approved["panels"][0]["items"][0]["status"] == "approved"
    assert approved["summary"]["event_count"] == 2


def test_cli_tui_approvals_screen_denies_pending_request(capsys) -> None:
    run_id = _create_fixture_run(capsys)
    approval_id = _request_fixture_approval(capsys, run_id)

    deny_exit = main(
        [
            "tui",
            "--screen",
            "approvals",
            "--deny",
            approval_id,
            "--resolved-by",
            "analyst@example.test",
            "--json",
        ]
    )
    denied = json.loads(capsys.readouterr().out)

    assert deny_exit == 0
    assert denied["summary"]["decision"] == "denied"
    assert denied["panels"][0]["items"][0]["status"] == "denied"


def test_cli_tui_approvals_screen_requires_run_id_for_listing(capsys) -> None:
    exit_code = main(["tui", "--screen", "approvals", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert payload["error"] == "missing_run_id"


def test_cli_tui_replay_debug_screen_exports_timeline_and_bundle_summary(capsys) -> None:
    run_id = _create_fixture_run(capsys)

    exit_code = main(["tui", "--screen", "replay-debug", "--run-id", run_id, "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["screen"] == "replay_debug"
    assert payload["summary"]["run_id"] == run_id
    assert payload["summary"]["event_count"] >= 2
    assert payload["summary"]["evidence_count"] >= 1
    assert payload["summary"]["report_count"] == 1
    assert payload["summary"]["redactions"] == "secrets_omitted,full_transcripts_omitted"
    assert payload["panels"][0]["items"][0]["type"] == "run.created"


def test_cli_tui_replay_debug_screen_requires_run_id(capsys) -> None:
    exit_code = main(["tui", "--screen", "replay-debug", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert payload["error"] == "missing_run_id"


def test_cli_tui_returns_nonzero_for_missing_run(capsys) -> None:
    exit_code = main(["tui", "--screen", "run-monitor", "--run-id", "missing_run", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["error"] == "run_not_found"


def _create_fixture_run(capsys) -> str:
    exit_code = main(
        [
            "run",
            "acquisition-memo",
            "--address",
            "example Miami-Dade fixture address",
            "--source-mode",
            "fixture",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    return payload["run_id"]


def _request_fixture_approval(capsys, run_id: str) -> str:
    exit_code = main(
        [
            "approvals",
            "request",
            "--run-id",
            run_id,
            "--action",
            "export_lender_package",
            "--risk-level",
            "high",
            "--reason",
            "Export requires analyst approval.",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    return payload["approval_id"]
