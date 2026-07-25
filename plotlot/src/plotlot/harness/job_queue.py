from __future__ import annotations

from pathlib import Path
from typing import assert_never

from plotlot.harness.contracts import (
    ExecutionMode,
    JobId,
    PlotLotEvent,
    PlotLotEventSource,
    PlotLotEventType,
)
from plotlot.harness.contracts.base import utc_now
from plotlot.harness.fixture_runs import (
    FixtureDealRunRequest,
    FixtureDealRunResult,
    fixture_run_id_for_address,
)
from plotlot.harness.job_execution import (
    AnalysisJobRunner,
    AsyncAnalysisJobRunner,
    JobExecutionFailure,
    default_analysis_job_runner,
    default_analysis_job_runner_async,
    job_with_failure_events,
)
from plotlot.harness.job_cancellation import (
    HarnessJobCancellationRequest,
    JobCancellationBlockedError,
    blocked_job_cancellation_event,
    job_cancelled_event,
    transition_job_to_cancelled,
)
from plotlot.harness.job_models import (
    HarnessJob,
    HarnessJobNotFoundError,
    HarnessJobStatus,
    HarnessJobType,
    JobUpdate,
)
from plotlot.harness.job_queue_storage import (
    LocalHarnessJobQueueStorage,
    default_harness_job_store_path,
    find_job_by_idempotency_key,
    new_job_id,
)
from plotlot.harness.job_queue_events import JobEventInput, job_event
from plotlot.harness.run_persistence import FixtureRunPersistenceStores, persist_fixture_run_result


class LocalHarnessJobQueue:
    def __init__(self, path: Path) -> None:
        self._storage = LocalHarnessJobQueueStorage(path)

    def create_analysis_job(
        self,
        request: FixtureDealRunRequest,
        *,
        idempotency_key: str | None = None,
        max_attempts: int = 3,
    ) -> HarnessJob:
        snapshot = self._storage.read_snapshot()
        if idempotency_key is not None:
            existing = find_job_by_idempotency_key(snapshot, idempotency_key)
            if existing is not None:
                return existing
        run_id = fixture_run_id_for_address(request.address)
        job_id = new_job_id(request, idempotency_key)
        events = [
            job_event(
                JobEventInput(
                    run_id=run_id,
                    sequence=1,
                    event_type=PlotLotEventType.JOB_CREATED,
                    source=PlotLotEventSource.SYSTEM,
                    source_mode=request.source_mode,
                    job_id=job_id,
                    idempotency_key=idempotency_key,
                )
            ),
            job_event(
                JobEventInput(
                    run_id=run_id,
                    sequence=2,
                    event_type=PlotLotEventType.JOB_QUEUED,
                    source=PlotLotEventSource.SYSTEM,
                    source_mode=request.source_mode,
                    job_id=job_id,
                    idempotency_key=idempotency_key,
                )
            ),
        ]
        job = HarnessJob(
            job_id=job_id,
            job_type=HarnessJobType.ANALYSIS_RUN,
            status=HarnessJobStatus.QUEUED,
            request=request,
            run_id=run_id,
            idempotency_key=idempotency_key,
            max_attempts=max_attempts,
            events=events,
        )
        self._storage.save_job(snapshot, job)
        return job

    def list_jobs(self) -> list[HarnessJob]:
        snapshot = self._storage.read_snapshot()
        return sorted(snapshot.jobs.values(), key=lambda job: job.created_at)

    def get_job(self, job_id: JobId) -> HarnessJob:
        snapshot = self._storage.read_snapshot()
        job = snapshot.jobs.get(str(job_id))
        if job is None:
            raise HarnessJobNotFoundError(job_id=job_id)
        return job

    def get_events(self, job_id: JobId) -> list[PlotLotEvent]:
        return self.get_job(job_id).events

    def cancel_job(self, request: HarnessJobCancellationRequest) -> HarnessJob:
        snapshot = self._storage.read_snapshot()
        job = snapshot.jobs.get(str(request.job_id))
        if job is None:
            raise HarnessJobNotFoundError(job_id=request.job_id)
        existing_events = list(job.events)
        try:
            target_status = transition_job_to_cancelled(job.status, job_id=request.job_id)
        except JobCancellationBlockedError as exc:
            failed_event = blocked_job_cancellation_event(
                request,
                job,
                sequence=len(existing_events) + 1,
                error=exc,
            )
            updated_job = job.model_copy(update={"events": [*existing_events, failed_event]})
            self._storage.save_job(snapshot, updated_job)
            raise
        cancel_event = job_cancelled_event(
            request,
            job,
            sequence=len(existing_events) + 1,
            previous_status=job.status,
        )
        updated_job = job.model_copy(
            update={
                "status": target_status,
                "events": [*existing_events, cancel_event],
                "updated_at": utc_now(),
            }
        )
        self._storage.save_job(snapshot, updated_job)
        return updated_job

    def run_next(
        self,
        stores: FixtureRunPersistenceStores,
        *,
        runner: AnalysisJobRunner = default_analysis_job_runner,
    ) -> HarnessJob | None:
        queued = next((job for job in self.list_jobs() if job.status == HarnessJobStatus.QUEUED), None)
        if queued is None:
            return None
        running = _with_event(
            queued,
            JobUpdate(
                status=HarnessJobStatus.RUNNING,
                event_type=PlotLotEventType.JOB_STARTED,
                source=PlotLotEventSource.WORKER,
                attempts=queued.attempts + 1,
            ),
        )
        self._storage.save_job(self._storage.read_snapshot(), running)
        worker_request = running.request.model_copy(update={"execution_mode": ExecutionMode.WORKER})
        result = runner(worker_request)
        match result:
            case FixtureDealRunResult() as completed_run:
                persist_fixture_run_result(completed_run, stores)
                completed = _with_event(
                    running,
                    JobUpdate(
                        status=HarnessJobStatus.COMPLETED,
                        event_type=PlotLotEventType.JOB_COMPLETED,
                        source=PlotLotEventSource.WORKER,
                        run_id=completed_run.run_id,
                    ),
                )
                self._storage.save_job(self._storage.read_snapshot(), completed)
                return completed
            case JobExecutionFailure() as failure:
                failed = job_with_failure_events(running, failure)
                self._storage.save_job(self._storage.read_snapshot(), failed)
                return failed
            case unreachable:
                assert_never(unreachable)

    async def run_next_async(
        self,
        stores: FixtureRunPersistenceStores,
        *,
        runner: AsyncAnalysisJobRunner = default_analysis_job_runner_async,
    ) -> HarnessJob | None:
        queued = next((job for job in self.list_jobs() if job.status == HarnessJobStatus.QUEUED), None)
        if queued is None:
            return None
        running = _with_event(
            queued,
            JobUpdate(
                status=HarnessJobStatus.RUNNING,
                event_type=PlotLotEventType.JOB_STARTED,
                source=PlotLotEventSource.WORKER,
                attempts=queued.attempts + 1,
            ),
        )
        self._storage.save_job(self._storage.read_snapshot(), running)
        worker_request = running.request.model_copy(update={"execution_mode": ExecutionMode.WORKER})
        result = await runner(worker_request)
        match result:
            case FixtureDealRunResult() as completed_run:
                persist_fixture_run_result(completed_run, stores)
                completed = _with_event(
                    running,
                    JobUpdate(
                        status=HarnessJobStatus.COMPLETED,
                        event_type=PlotLotEventType.JOB_COMPLETED,
                        source=PlotLotEventSource.WORKER,
                        run_id=completed_run.run_id,
                    ),
                )
                self._storage.save_job(self._storage.read_snapshot(), completed)
                return completed
            case JobExecutionFailure() as failure:
                failed = job_with_failure_events(running, failure)
                self._storage.save_job(self._storage.read_snapshot(), failed)
                return failed
            case unreachable:
                assert_never(unreachable)


def _with_event(
    job: HarnessJob,
    update: JobUpdate,
) -> HarnessJob:
    event = job_event(
        JobEventInput(
            run_id=job.run_id,
            sequence=len(job.events) + 1,
            event_type=update.event_type,
            source=update.source,
            source_mode=job.request.source_mode,
            job_id=job.job_id,
            idempotency_key=job.idempotency_key,
        )
    )
    return job.model_copy(
        update={
            "status": update.status,
            "attempts": update.attempts if update.attempts is not None else job.attempts,
            "run_id": update.run_id if update.run_id is not None else job.run_id,
            "events": [*job.events, event],
            "updated_at": utc_now(),
        }
    )


def default_harness_job_queue() -> LocalHarnessJobQueue:
    return LocalHarnessJobQueue(default_harness_job_store_path())
