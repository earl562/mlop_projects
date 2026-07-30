from __future__ import annotations

import json

from plotlot.cli_harness import main


def test_cli_scaffold_tool_creates_files_under_requested_root(tmp_path, capsys) -> None:
    exit_code = main(["scaffold", "tool", "demo_tool", "--root", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["scaffold"]["name"] == "demo_tool"
    assert payload["scaffold"]["files"][0]["status"] == "created"
    assert (tmp_path / "src/plotlot/harness/generated_tools/demo_tool/handler.py").exists()


def test_cli_scaffold_tool_refuses_overwrite_without_force(tmp_path, capsys) -> None:
    create_exit = main(["scaffold", "tool", "demo_tool", "--root", str(tmp_path)])
    create_payload = json.loads(capsys.readouterr().out)
    repeat_exit = main(["scaffold", "tool", "demo_tool", "--root", str(tmp_path)])
    repeat_payload = json.loads(capsys.readouterr().out)

    assert create_exit == 0
    assert create_payload["scaffold"]["name"] == "demo_tool"
    assert repeat_exit == 1
    assert repeat_payload["error"] == "scaffold_target_exists"


def test_cli_scaffold_tool_force_overwrites_existing_files(tmp_path, capsys) -> None:
    main(["scaffold", "tool", "demo_tool", "--root", str(tmp_path)])
    capsys.readouterr()

    exit_code = main(["scaffold", "tool", "demo_tool", "--root", str(tmp_path), "--force"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["scaffold"]["force"] is True
    assert payload["scaffold"]["files"][0]["status"] == "overwritten"
