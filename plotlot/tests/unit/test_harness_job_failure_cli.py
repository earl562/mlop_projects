from __future__ import annotations

import json

import pytest
from pytest import MonkeyPatch

from plotlot.cli_harness import main


@pytest.fixture(autouse=True)
def harness_store_path(tmp_path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("PLOTLOT_HARNESS_STORE_PATH", str(tmp_path / "harness-runs.json"))
    monkeypatch.setenv("PLOTLOT_HARNESS_JOB_STORE_PATH", str(tmp_path / "harness-jobs.json"))
    monkeypatch.setenv("PLOTLOT_HARNESS_REPORT_STORE_PATH", str(tmp_path / "harness-reports.json"))


def test_cli_jobs_run_next_can_record_fixture_worker_failure(capsys) -> None:
    create_exit = main(
        [
            "jobs",
            "create",
            "--address",
            "example failed CLI job fixture address",
            "--analysis-type",
            "acquisition-memo",
            "--source-mode",
            "fixture",
        ]
    )
    created = json.loads(capsys.readouterr().out)

    run_exit = main(["jobs", "run-next", "--fixture-failure", "Synthetic worker failure."])
    retried = json.loads(capsys.readouterr().out)
    events_exit = main(["jobs", "events", created["job_id"]])
    events = json.loads(capsys.readouterr().out)

    assert create_exit == 0
    assert run_exit == 0
    assert events_exit == 0
    assert retried["status"] == "queued"
    assert retried["error"] == "fixture_failure: Synthetic worker failure."
    assert [event["type"] for event in events["events"]][-2:] == [
        "job.failed",
        "job.retry_scheduled",
    ]


def test_cli_jobs_run_next_dead_letters_after_configured_attempt_budget(capsys) -> None:
    create_exit = main(
        [
            "jobs",
            "create",
            "--address",
            "example dead letter CLI job fixture address",
            "--analysis-type",
            "acquisition-memo",
            "--source-mode",
            "fixture",
            "--max-attempts",
            "1",
        ]
    )
    created = json.loads(capsys.readouterr().out)

    run_exit = main(["jobs", "run-next", "--fixture-failure", "Synthetic terminal failure."])
    dead_lettered = json.loads(capsys.readouterr().out)
    events_exit = main(["jobs", "events", created["job_id"]])
    events = json.loads(capsys.readouterr().out)

    assert create_exit == 0
    assert run_exit == 0
    assert events_exit == 0
    assert dead_lettered["status"] == "dead_lettered"
    assert dead_lettered["attempts"] == 1
    assert dead_lettered["max_attempts"] == 1
    assert [event["type"] for event in events["events"]][-2:] == [
        "job.failed",
        "job.dead_lettered",
    ]
