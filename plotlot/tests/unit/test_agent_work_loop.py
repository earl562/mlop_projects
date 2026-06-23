from pathlib import Path

from plotlot.dev import agent_loop


def test_full_profile_orders_plan_debug_test_review_phases(tmp_path: Path) -> None:
    # Given: a full local loop profile.
    config = agent_loop.LoopConfig(
        repo_root=tmp_path,
        app_root=tmp_path / "plotlot",
        report_dir=tmp_path / ".omo" / "evidence" / "agent-loop",
        phases=agent_loop.profile_phases("full"),
        stop_on_failure=True,
        plan_only=True,
    )

    # When: commands are built.
    command_names = [command.name for command in agent_loop.build_commands(config)]

    # Then: the loop has a deterministic planning/debug/testing/review order.
    assert command_names[:4] == [
        "git-status",
        "git-diff-stat",
        "python-version",
        "uv-version",
    ]
    assert command_names.index("backend-unit-tests") < command_names.index("frontend-build")
    assert command_names.index("lookup-eval-gates") < command_names.index("review-diff-check")


def test_plan_only_marks_commands_without_executing(tmp_path: Path) -> None:
    # Given: a smoke loop in plan-only mode.
    config = agent_loop.LoopConfig(
        repo_root=tmp_path,
        app_root=tmp_path / "plotlot",
        report_dir=tmp_path / "reports",
        phases=agent_loop.profile_phases("smoke"),
        stop_on_failure=True,
        plan_only=True,
    )

    # When: the loop executes.
    report = agent_loop.execute_loop(config)

    # Then: every command is planned, not reported as passing runtime evidence.
    assert report.status == agent_loop.RunStatus.PLANNED
    assert report.results
    assert {result.status for result in report.results} == {agent_loop.RunStatus.PLANNED}


def test_evidence_redaction_masks_secret_like_values() -> None:
    # Given: command output that accidentally includes credential-shaped values.
    raw = "DEEPSEEK_API_KEY=sk-live-secret Authorization: Bearer token-value ok"

    # When: the output is redacted for evidence storage.
    redacted = agent_loop.redact_text(raw)

    # Then: key names remain useful while raw credential values are removed.
    assert "DEEPSEEK_API_KEY=<redacted>" in redacted
    assert "Authorization: <redacted>" in redacted
    assert "sk-live-secret" not in redacted
    assert "token-value" not in redacted
