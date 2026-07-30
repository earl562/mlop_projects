from __future__ import annotations

import json

import pytest
from pytest import MonkeyPatch

from plotlot.cli_harness import main


@pytest.fixture(autouse=True)
def harness_store_path(tmp_path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("PLOTLOT_HARNESS_STORE_PATH", str(tmp_path / "harness-runs.json"))
    monkeypatch.setenv("PLOTLOT_HARNESS_JOB_STORE_PATH", str(tmp_path / "harness-jobs.json"))
    monkeypatch.setenv(
        "PLOTLOT_HARNESS_EVIDENCE_STORE_PATH", str(tmp_path / "harness-evidence.json")
    )
    monkeypatch.setenv("PLOTLOT_HARNESS_REPORT_STORE_PATH", str(tmp_path / "harness-reports.json"))
    monkeypatch.setenv(
        "PLOTLOT_HARNESS_VERIFICATION_STORE_PATH",
        str(tmp_path / "harness-verifications.json"),
    )
    monkeypatch.setenv("PLOTLOT_HARNESS_TOOL_CALL_STORE_PATH", str(tmp_path / "tool-calls.json"))


def test_cli_tools_inspect_and_call_use_shared_tool_router(capsys) -> None:
    inspect_exit = main(["tools", "inspect", "search_municode"])
    inspected = json.loads(capsys.readouterr().out)
    call_exit = main(
        [
            "tools",
            "call",
            "search_municode",
            "--run-id",
            "run_fixture_cli_tool",
            "--workspace-id",
            "ws_fixture",
            "--json",
            '{"jurisdiction":"miami","query":"parking"}',
        ]
    )
    called = json.loads(capsys.readouterr().out)

    assert inspect_exit == 0
    assert call_exit == 0
    assert inspected["tool"]["name"] == "search_municode"
    assert called["ok"] is True
    assert called["events"][1]["type"] == "tool.policy_checked"
    assert called["payload"]["results"][0]["section_id"] == "municode_miami_parking_fixture"


def test_cli_tools_call_returns_nonzero_for_approval_required_tool(capsys) -> None:
    exit_code = main(
        [
            "tools",
            "call",
            "export_report",
            "--run-id",
            "run_fixture_cli_tool",
            "--workspace-id",
            "ws_fixture",
            "--json",
            '{"report_id":"report_fixture"}',
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["status"] == "approval_required"
    assert payload["policy_decision"]["approval_required"] is True


def test_cli_tools_call_persists_tool_call_and_appends_run_events(capsys) -> None:
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

    call_exit = main(
        [
            "tools",
            "call",
            "search_municode",
            "--run-id",
            run_id,
            "--workspace-id",
            "ws_fixture",
            "--json",
            '{"jurisdiction":"miami","query":"parking"}',
        ]
    )
    tool_payload = json.loads(capsys.readouterr().out)
    calls_exit = main(["tools", "calls", "--run-id", run_id])
    calls_payload = json.loads(capsys.readouterr().out)
    events_exit = main(["runs", "events", run_id])
    events_payload = json.loads(capsys.readouterr().out)

    assert run_exit == 0
    assert call_exit == 0
    assert calls_exit == 0
    assert events_exit == 0
    assert calls_payload["tool_calls"][0]["tool_call_id"] == tool_payload["tool_call_id"]
    assert events_payload["events"][-1]["type"] == "tool.completed"
