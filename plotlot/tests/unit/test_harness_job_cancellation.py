from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch

from plotlot.api.main import app
from plotlot.cli_harness import main
from plotlot.harness.contracts import ExecutionMode, SourceMode
from plotlot.harness.evidence_store import LocalEvidenceLedger
from plotlot.harness.fixture_runs import FixtureDealRunRequest
from plotlot.harness.job_queue import (
    HarnessJobCancellationRequest,
    JobCancellationBlockedError,
    LocalHarnessJobQueue,
)
from plotlot.harness.report_store import LocalReportLedger
from plotlot.harness.run_persistence import FixtureRunPersistenceStores
from plotlot.harness.run_store import LocalHarnessRunStore


@pytest.fixture(autouse=True)
def harness_store_path(tmp_path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("PLOTLOT_HARNESS_STORE_PATH", str(tmp_path / "harness-runs.json"))
    monkeypatch.setenv("PLOTLOT_HARNESS_JOB_STORE_PATH", str(tmp_path / "harness-jobs.json"))
    monkeypatch.setenv("PLOTLOT_HARNESS_REPORT_STORE_PATH", str(tmp_path / "harness-reports.json"))


@pytest.fixture
def transport() -> ASGITransport:
    return ASGITransport(app=app)


@pytest.fixture
async def client(transport: ASGITransport):
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def test_local_job_queue_cancels_queued_job_with_ordered_event(tmp_path) -> None:
    queue = LocalHarnessJobQueue(tmp_path / "jobs.json")
    job = queue.create_analysis_job(
        FixtureDealRunRequest(
            address="example cancellable job fixture address",
            analysis_type="acquisition_memo",
            source_mode=SourceMode.FIXTURE,
        )
    )

    cancelled = queue.cancel_job(
        HarnessJobCancellationRequest(
            job_id=job.job_id,
            actor_user_id="analyst_fixture",
            reason="Duplicate job.",
            execution_mode=ExecutionMode.CLI,
        )
    )

    assert cancelled.status == "cancelled"
    assert [event.sequence for event in cancelled.events] == [1, 2, 3]
    assert cancelled.events[-1].type == "job.cancelled"
    assert cancelled.events[-1].source == "cli"
    assert cancelled.events[-1].payload["actor_user_id"] == "analyst_fixture"


def test_local_job_queue_rejects_completed_job_cancellation(tmp_path) -> None:
    queue = LocalHarnessJobQueue(tmp_path / "jobs.json")
    job = queue.create_analysis_job(
        FixtureDealRunRequest(
            address="example completed job fixture address",
            analysis_type="acquisition_memo",
            source_mode=SourceMode.FIXTURE,
        )
    )
    stores = FixtureRunPersistenceStores(
        run_store=LocalHarnessRunStore(tmp_path / "runs.json"),
        evidence_ledger=LocalEvidenceLedger(tmp_path / "evidence.json"),
        report_ledger=LocalReportLedger(tmp_path / "reports.json"),
    )
    queue.run_next(stores)

    with pytest.raises(JobCancellationBlockedError) as exc_info:
        queue.cancel_job(
            HarnessJobCancellationRequest(
                job_id=job.job_id,
                actor_user_id="analyst_fixture",
                reason="Too late.",
                execution_mode=ExecutionMode.LOCAL,
            )
        )

    events = queue.get_events(job.job_id)
    assert exc_info.value.current_status == "completed"
    assert events[-1].type == "job.cancelled"
    assert events[-1].status == "failed"
    assert events[-1].payload["current_status"] == "completed"
    assert events[-1].error is not None
    assert events[-1].error.code == "invalid_job_transition"


def test_cli_jobs_cancel_updates_queued_job_and_emits_event(capsys) -> None:
    create_exit = main(
        [
            "jobs",
            "create",
            "--address",
            "example cancellable CLI job fixture address",
            "--analysis-type",
            "acquisition-memo",
            "--source-mode",
            "fixture",
        ]
    )
    created = json.loads(capsys.readouterr().out)

    cancel_exit = main(
        [
            "jobs",
            "cancel",
            created["job_id"],
            "--reason",
            "Manual CLI cancellation.",
            "--actor-user-id",
            "cli_fixture",
        ]
    )
    cancelled = json.loads(capsys.readouterr().out)
    events_exit = main(["jobs", "events", created["job_id"]])
    events = json.loads(capsys.readouterr().out)

    assert create_exit == 0
    assert cancel_exit == 0
    assert events_exit == 0
    assert cancelled["status"] == "cancelled"
    assert events["events"][-1]["type"] == "job.cancelled"
    assert events["events"][-1]["payload"]["reason"] == "Manual CLI cancellation."


@pytest.mark.asyncio
async def test_harness_job_cancel_api_updates_queued_job_and_emits_event(
    client: AsyncClient,
) -> None:
    queued_response = await client.post(
        "/api/v1/harness/jobs",
        json={
            "address": "example cancellable API job fixture address",
            "analysis_type": "acquisition_memo",
            "source_mode": "fixture",
        },
    )
    job_id = queued_response.json()["job_id"]

    cancel_response = await client.post(
        f"/api/v1/harness/jobs/{job_id}/cancel",
        json={"reason": "Manual API cancellation.", "actor_user_id": "api_fixture"},
    )
    events_response = await client.get(f"/api/v1/harness/jobs/{job_id}/events")

    assert queued_response.status_code == 200
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"
    assert events_response.json()["events"][-1]["type"] == "job.cancelled"
    assert events_response.json()["events"][-1]["payload"]["actor_user_id"] == "api_fixture"
