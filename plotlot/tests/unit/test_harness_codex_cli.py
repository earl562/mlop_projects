from __future__ import annotations

import json
import subprocess

from plotlot.cli_harness import main
from plotlot.harness.codex_reference import CodexDoctorResult


def test_cli_codex_goal_generate_and_print(tmp_path, capsys) -> None:
    goal_path = tmp_path / "full-harness.goal.md"

    generate_exit = main(["codex", "goal", "generate", "--path", str(goal_path)])
    generate_payload = json.loads(capsys.readouterr().out)
    print_exit = main(["codex", "goal", "print", "--path", str(goal_path)])
    print_payload = json.loads(capsys.readouterr().out)

    assert generate_exit == 0
    assert generate_payload["created"] is True
    assert generate_payload["goal_path"] == str(goal_path)
    assert print_exit == 0
    assert "PlotLot Full Harness Goal" in print_payload["content"]


def test_cli_codex_doctor_reports_optional_cli_status(capsys) -> None:
    exit_code = main(["codex", "doctor"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["production_dependency"] is False
    assert payload["status"] in {"available", "optional_missing"}


def test_cli_codex_inspect_reference_checks_external_checkout(tmp_path, capsys) -> None:
    checkout = tmp_path / "codex"
    checkout.mkdir()
    (checkout / "README.md").write_text("Codex CLI", encoding="utf-8")

    exit_code = main(["codex", "inspect-reference", "--path", str(checkout)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["exists"] is True
    assert payload["status"] == "reference_available"
    assert payload["production_dependency"] is False


def test_cli_codex_run_is_explicit_and_fails_when_binary_missing(tmp_path, monkeypatch, capsys) -> None:
    goal_path = tmp_path / "goal.md"
    goal_path.write_text("Goal", encoding="utf-8")
    monkeypatch.setenv("PATH", str(tmp_path / "no-bin"))

    exit_code = main(["codex", "run", "--goal", str(goal_path)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["error"] == "codex_cli_unavailable"
    assert payload["production_dependency"] is False


def test_cli_codex_run_passes_selected_legacy_model_to_codex_exec(
    tmp_path, monkeypatch, capsys
) -> None:
    goal_path = tmp_path / "goal.md"
    goal_path.write_text("Goal", encoding="utf-8")
    captured_command: list[str] = []

    def fake_run(
        command: list[str],
        *,
        input: str,
        text: bool,
        capture_output: bool,
        timeout: int,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        captured_command.extend(command)
        assert input == "Goal"
        assert text is True
        assert capture_output is True
        assert timeout == 600
        assert check is False
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(
        "plotlot.cli_harness_codex.codex_doctor",
        lambda: CodexDoctorResult(
            status="available",
            codex_path="/tmp/codex",
            guidance="available for local operator workflows",
        ),
    )
    monkeypatch.setattr("plotlot.cli_harness_codex.subprocess.run", fake_run)

    exit_code = main(["codex", "run", "--goal", str(goal_path), "-m", "gpt-5.2"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert captured_command == [
        "/tmp/codex",
        "-m",
        "gpt-5.2",
        "exec",
        "--cd",
        str(goal_path.cwd()),
        "-",
    ]
    assert payload["status"] == "completed"
    assert payload["exit_code"] == 0
