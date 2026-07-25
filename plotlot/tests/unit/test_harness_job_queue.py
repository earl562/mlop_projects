from __future__ import annotations

from plotlot.harness.contracts import SourceMode
from plotlot.harness.evidence_store import LocalEvidenceLedger
from plotlot.harness.fixture_runs import FixtureDealRunRequest
from plotlot.harness.job_execution import JobExecutionFailure, JobExecutionResult
from plotlot.harness.job_queue import LocalHarnessJobQueue
from plotlot.harness.report_store import LocalReportLedger
from plotlot.harness.run_persistence import FixtureRunPersistenceStores
from plotlot.harness.run_store import LocalHarnessRunStore


def test_local_job_queue_persists_created_and_queued_events(tmp_path) -> None:
    queue = LocalHarnessJobQueue(tmp_path / "jobs.json")

    job = queue.create_analysis_job(
        FixtureDealRunRequest(
            address="example Broward fixture address",
            analysis_type="zoning_research",
            source_mode=SourceMode.FIXTURE,
        ),
        idempotency_key="broward-zoning",
    )
    loaded = LocalHarnessJobQueue(tmp_path / "jobs.json").get_job(job.job_id)

    assert loaded.status == "queued"
    assert [event.type.value for event in loaded.events] == ["job.created", "job.queued"]
    assert loaded.idempotency_key == "broward-zoning"


def test_local_job_queue_worker_executes_next_job_and_saves_run(tmp_path) -> None:
    queue = LocalHarnessJobQueue(tmp_path / "jobs.json")
    run_store = LocalHarnessRunStore(tmp_path / "runs.json")
    evidence_ledger = LocalEvidenceLedger(tmp_path / "evidence.json")
    report_ledger = LocalReportLedger(tmp_path / "reports.json")
    job = queue.create_analysis_job(
        FixtureDealRunRequest(
            address="example Miami-Dade fixture address",
            analysis_type="acquisition_memo",
            source_mode=SourceMode.FIXTURE,
        )
    )

    completed = queue.run_next(
        FixtureRunPersistenceStores(
            run_store=run_store,
            evidence_ledger=evidence_ledger,
            report_ledger=report_ledger,
        )
    )
    saved_run = run_store.get_run(completed.run_id)
    evidence = evidence_ledger.list_evidence(run_id=completed.run_id)
    reports = report_ledger.list_reports(run_id=completed.run_id)

    assert completed.job_id == job.job_id
    assert completed.status == "completed"
    assert saved_run.status == "completed"
    assert evidence[0].evidence_id in saved_run.evidence_ids
    assert reports[0].run_id == completed.run_id
    assert saved_run.events[0].execution_mode == "worker"
    assert [event.type.value for event in completed.events][-2:] == [
        "job.started",
        "job.completed",
    ]


def test_local_job_queue_idempotency_key_reuses_existing_job(tmp_path) -> None:
    queue = LocalHarnessJobQueue(tmp_path / "jobs.json")
    request = FixtureDealRunRequest(
        address="example duplicate fixture address",
        analysis_type="zoning_research",
        source_mode=SourceMode.FIXTURE,
    )

    first = queue.create_analysis_job(request, idempotency_key="same-input")
    second = queue.create_analysis_job(request, idempotency_key="same-input")

    assert second.job_id == first.job_id
    assert len(queue.list_jobs()) == 1


def test_local_job_queue_records_failure_and_schedules_retry(tmp_path) -> None:
    queue = LocalHarnessJobQueue(tmp_path / "jobs.json")
    stores = _persistence_stores(tmp_path)
    job = queue.create_analysis_job(
        FixtureDealRunRequest(
            address="example retry fixture address",
            analysis_type="acquisition_memo",
            source_mode=SourceMode.FIXTURE,
        )
    )

    retried = queue.run_next(stores, runner=_failing_runner)

    assert retried.job_id == job.job_id
    assert retried.status == "queued"
    assert retried.attempts == 1
    assert retried.error == "fixture_failure: synthetic worker failure"
    assert [event.type.value for event in retried.events][-2:] == [
        "job.failed",
        "job.retry_scheduled",
    ]
    assert retried.events[-2].status == "failed"
    assert stores.run_store.list_runs() == []


def test_local_job_queue_dead_letters_after_max_attempts(tmp_path) -> None:
    queue = LocalHarnessJobQueue(tmp_path / "jobs.json")
    job = queue.create_analysis_job(
        FixtureDealRunRequest(
            address="example dead letter fixture address",
            analysis_type="acquisition_memo",
            source_mode=SourceMode.FIXTURE,
        ),
        max_attempts=1,
    )

    dead_lettered = queue.run_next(_persistence_stores(tmp_path), runner=_failing_runner)

    assert dead_lettered.job_id == job.job_id
    assert dead_lettered.status == "dead_lettered"
    assert dead_lettered.attempts == 1
    assert [event.type.value for event in dead_lettered.events][-2:] == [
        "job.failed",
        "job.dead_lettered",
    ]
    assert dead_lettered.events[-1].payload["error_code"] == "fixture_failure"


def _failing_runner(_request: FixtureDealRunRequest) -> JobExecutionResult:
    return JobExecutionFailure(
        code="fixture_failure",
        message="synthetic worker failure",
    )


def _persistence_stores(tmp_path) -> FixtureRunPersistenceStores:
    return FixtureRunPersistenceStores(
        run_store=LocalHarnessRunStore(tmp_path / "runs.json"),
        evidence_ledger=LocalEvidenceLedger(tmp_path / "evidence.json"),
        report_ledger=LocalReportLedger(tmp_path / "reports.json"),
    )
