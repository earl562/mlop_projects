from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from plotlot.harness.contracts import (
    PlotLotEvent,
    PlotLotEventError,
    PlotLotEventSource,
    PlotLotEventStatus,
    PlotLotEventType,
)
from plotlot.harness.contracts.base import utc_now
from plotlot.harness.fixture_runs import (
    FixtureDealRunRequest,
    FixtureDealRunResult,
    run_fixture_deal_analysis,
    run_fixture_deal_analysis_async,
)
from plotlot.harness.job_models import HarnessJob, HarnessJobStatus
from plotlot.harness.job_queue_events import JobEventInput, job_event


@dataclass(frozen=True, slots=True)
class JobExecutionFailure:
    code: str
    message: str

    def summary(self) -> str:
        return f"{self.code}: {self.message}"


type JobExecutionResult = FixtureDealRunResult | JobExecutionFailure


@dataclass(frozen=True, slots=True)
class StaticJobFailureRunner:
    failure: JobExecutionFailure

    def __call__(self, request: FixtureDealRunRequest) -> JobExecutionResult:
        del request
        return self.failure


class AnalysisJobRunner(Protocol):
    def __call__(self, request: FixtureDealRunRequest) -> JobExecutionResult: ...


def default_analysis_job_runner(request: FixtureDealRunRequest) -> JobExecutionResult:
    return run_fixture_deal_analysis(request)


class AsyncAnalysisJobRunner(Protocol):
    async def __call__(self, request: FixtureDealRunRequest) -> JobExecutionResult: ...


async def default_analysis_job_runner_async(request: FixtureDealRunRequest) -> JobExecutionResult:
    return await run_fixture_deal_analysis_async(request)


def job_failure_event(
    job: HarnessJob,
    failure: JobExecutionFailure,
    *,
    sequence: int,
) -> PlotLotEvent:
    return _failure_lifecycle_event(
        job,
        failure,
        sequence=sequence,
        event_type=PlotLotEventType.JOB_FAILED,
        event_status=PlotLotEventStatus.FAILED,
    )


def job_retry_scheduled_event(
    job: HarnessJob,
    failure: JobExecutionFailure,
    *,
    sequence: int,
) -> PlotLotEvent:
    return _failure_lifecycle_event(
        job,
        failure,
        sequence=sequence,
        event_type=PlotLotEventType.JOB_RETRY_SCHEDULED,
        event_status=PlotLotEventStatus.COMPLETED,
    )


def job_dead_lettered_event(
    job: HarnessJob,
    failure: JobExecutionFailure,
    *,
    sequence: int,
) -> PlotLotEvent:
    return _failure_lifecycle_event(
        job,
        failure,
        sequence=sequence,
        event_type=PlotLotEventType.JOB_DEAD_LETTERED,
        event_status=PlotLotEventStatus.FAILED,
    )


def job_with_failure_events(job: HarnessJob, failure: JobExecutionFailure) -> HarnessJob:
    failed_event = job_failure_event(job, failure, sequence=len(job.events) + 1)
    failed_job = job.model_copy(
        update={
            "status": HarnessJobStatus.FAILED,
            "events": [*job.events, failed_event],
            "error": failure.summary(),
            "updated_at": utc_now(),
        }
    )
    if failed_job.attempts >= failed_job.max_attempts:
        terminal_event = job_dead_lettered_event(
            failed_job,
            failure,
            sequence=len(failed_job.events) + 1,
        )
        terminal_status = HarnessJobStatus.DEAD_LETTERED
    else:
        terminal_event = job_retry_scheduled_event(
            failed_job,
            failure,
            sequence=len(failed_job.events) + 1,
        )
        terminal_status = HarnessJobStatus.QUEUED
    return failed_job.model_copy(
        update={
            "status": terminal_status,
            "events": [*failed_job.events, terminal_event],
            "updated_at": utc_now(),
        }
    )


def _failure_lifecycle_event(
    job: HarnessJob,
    failure: JobExecutionFailure,
    *,
    sequence: int,
    event_type: PlotLotEventType,
    event_status: PlotLotEventStatus,
) -> PlotLotEvent:
    event = job_event(
        JobEventInput(
            run_id=job.run_id,
            sequence=sequence,
            event_type=event_type,
            source=PlotLotEventSource.WORKER,
            source_mode=job.request.source_mode,
            job_id=job.job_id,
            idempotency_key=job.idempotency_key,
        )
    )
    return event.model_copy(
        update={
            "status": event_status,
            "payload": {
                "job_id": str(job.job_id),
                "error_code": failure.code,
                "error_message": failure.message,
                "attempts": job.attempts,
                "max_attempts": job.max_attempts,
            },
            "error": PlotLotEventError(
                code=failure.code,
                message=failure.message,
                details={"job_id": str(job.job_id)},
            ),
        }
    )
