from __future__ import annotations

import json

from pytest import MonkeyPatch

from plotlot.cli_harness import main


def test_harness_approval_cli_requests_lists_shows_and_approves(
    tmp_path,
    monkeypatch: MonkeyPatch,
    capsys,
) -> None:
    monkeypatch.setenv(
        "PLOTLOT_HARNESS_APPROVAL_STORE_PATH",
        str(tmp_path / "harness-approvals.json"),
    )

    request_code = main(
        [
            "approvals",
            "request",
            "--run-id",
            "run_fixture_cli_approval",
            "--action",
            "export_lender_package",
            "--risk-level",
            "high",
            "--reason",
            "Exporting a lender package requires analyst approval.",
        ]
    )
    request_payload = json.loads(capsys.readouterr().out)
    approval_id = request_payload["approval_id"]

    list_code = main(["approvals", "list", "--run-id", "run_fixture_cli_approval"])
    list_payload = json.loads(capsys.readouterr().out)
    show_code = main(["approvals", "show", approval_id])
    show_payload = json.loads(capsys.readouterr().out)
    approve_code = main(
        [
            "approvals",
            "approve",
            approval_id,
            "--resolved-by",
            "analyst@example.test",
        ]
    )
    approve_payload = json.loads(capsys.readouterr().out)

    assert request_code == 0
    assert list_code == 0
    assert show_code == 0
    assert approve_code == 0
    assert list_payload["approvals"][0]["approval_id"] == approval_id
    assert show_payload["requested_action"] == "export_lender_package"
    assert approve_payload["status"] == "approved"
    assert approve_payload["resolved_by"] == "analyst@example.test"


def test_harness_approval_cli_denies_pending_request(
    tmp_path,
    monkeypatch: MonkeyPatch,
    capsys,
) -> None:
    monkeypatch.setenv(
        "PLOTLOT_HARNESS_APPROVAL_STORE_PATH",
        str(tmp_path / "harness-approvals.json"),
    )
    main(
        [
            "approvals",
            "request",
            "--run-id",
            "run_fixture_cli_deny",
            "--action",
            "transcribe_user_media",
            "--risk-level",
            "critical",
            "--reason",
            "Transcription requires explicit permission.",
        ]
    )
    approval_id = json.loads(capsys.readouterr().out)["approval_id"]

    deny_code = main(
        [
            "approvals",
            "deny",
            approval_id,
            "--resolved-by",
            "analyst@example.test",
        ]
    )
    deny_payload = json.loads(capsys.readouterr().out)

    assert deny_code == 0
    assert deny_payload["status"] == "denied"
