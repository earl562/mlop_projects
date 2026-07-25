from __future__ import annotations

import json

import pytest
from pytest import MonkeyPatch

from plotlot.cli_harness import main


@pytest.fixture(autouse=True)
def memory_store_path(tmp_path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("PLOTLOT_HARNESS_MEMORY_STORE_PATH", str(tmp_path / "memory.json"))


def test_cli_memory_write_list_show_and_update(capsys) -> None:
    write_exit = main(
        [
            "memory",
            "write",
            "--workspace-id",
            "ws_fixture",
            "--project-id",
            "project_fixture",
            "--site-id",
            "site_fixture",
            "--memory-type",
            "site_assumption",
            "--content",
            "Use 850 sf average unit size until official plans are provided.",
            "--source-run-id",
            "run_fixture_001",
            "--evidence-id",
            "ev_fixture_001",
        ]
    )
    written = json.loads(capsys.readouterr().out)
    list_exit = main(["memory", "list", "--workspace-id", "ws_fixture"])
    listed = json.loads(capsys.readouterr().out)
    show_exit = main(["memory", "show", written["memory_id"]])
    shown = json.loads(capsys.readouterr().out)
    update_exit = main(
        [
            "memory",
            "update",
            written["memory_id"],
            "--content",
            "Use 900 sf average unit size from sponsor update.",
        ]
    )
    updated = json.loads(capsys.readouterr().out)

    assert write_exit == 0
    assert list_exit == 0
    assert show_exit == 0
    assert update_exit == 0
    assert written["metadata"]["is_evidence"] is False
    assert listed["memory"][0]["memory_id"] == written["memory_id"]
    assert shown["evidence_ids"] == ["ev_fixture_001"]
    assert updated["content"] == "Use 900 sf average unit size from sponsor update."


def test_cli_memory_missing_item_returns_nonzero(capsys) -> None:
    exit_code = main(["memory", "show", "mem_missing"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["error"] == "memory_not_found"
