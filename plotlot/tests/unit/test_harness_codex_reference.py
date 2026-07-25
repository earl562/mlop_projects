from __future__ import annotations

from plotlot.harness.codex_reference import (
    CodexReferenceConfig,
    generate_codex_goal,
    inspect_codex_reference,
)


def test_generate_codex_goal_writes_operator_prompt_without_runtime_dependency(tmp_path) -> None:
    target = tmp_path / "full-harness.goal.md"
    config = CodexReferenceConfig(goal_path=target)

    result = generate_codex_goal(config)

    assert result.goal_path == target
    assert result.created is True
    text = target.read_text(encoding="utf-8")
    assert "PlotLot Full Harness Goal" in text
    assert "Codex CLI is optional" in text
    assert "not a production runtime dependency" in text
    assert "gpt-5.2" in text
    assert "codex -m gpt-5.2" in text


def test_generate_codex_goal_refuses_overwrite_without_force(tmp_path) -> None:
    target = tmp_path / "existing.goal.md"
    target.write_text("existing", encoding="utf-8")

    result = generate_codex_goal(CodexReferenceConfig(goal_path=target))

    assert result.created is False
    assert result.skipped_reason == "target_exists"
    assert target.read_text(encoding="utf-8") == "existing"


def test_inspect_codex_reference_reports_missing_and_present_checkout(tmp_path) -> None:
    missing = inspect_codex_reference(tmp_path / "missing-codex")
    checkout = tmp_path / "codex"
    checkout.mkdir()
    (checkout / "package.json").write_text('{"name":"@openai/codex"}', encoding="utf-8")
    (checkout / "README.md").write_text("Codex CLI", encoding="utf-8")

    present = inspect_codex_reference(checkout)

    assert missing.exists is False
    assert missing.status == "missing"
    assert present.exists is True
    assert present.status == "reference_available"
    assert sorted(present.detected_files) == ["README.md", "package.json"]
