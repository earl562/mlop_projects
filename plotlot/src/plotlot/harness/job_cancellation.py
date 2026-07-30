from __future__ import annotations

from dataclasses import dataclass
from typing import assert_never

from pydantic import Field

from plotlot.harness.contracts import (
    ExecutionMode,
    JobId,
    PlotLotEvent,
    PlotLotEventError,
    PlotLotEventSource,
    PlotLotEventStatus,
    PlotLotEventType,
)
from plotlot.harness.contracts.base import HarnessContract
from plotlot.harness.job_models import HarnessJob, HarnessJobStatus


@dataclass(frozen=True, slots=True)
class JobCancellationBlockedError(Exception):
    job_id: JobId
    current_status: str
    reason: str

    def __str__(self) -> str:
        return f"Harness job cancellation blocked for {self.job_id}: {self.reason}"


class HarnessJobCancellationRequest(HarnessContract):
    job_id: JobId
    actor_user_id: str = Field(min_length=1)
    reason: str = Field(default="Cancellation requested.", min_length=1)
    execution_mode: ExecutionMode = ExecutionMode.LOCAL


def transition_job_to_cancelled(current: HarnessJobStatus, *, job_id: JobId) -> HarnessJobStatus:
    match current:
        case HarnessJobStatus.QUEUED | HarnessJobStatus.RUNNING:
            return HarnessJobStatus.CANCELLED
        case (
            HarnessJobStatus.COMPLETED
            | HarnessJobStatus.FAILED
            | HarnessJobStatus.CANCELLED
            | HarnessJobStatus.DEAD_LETTERED
        ):
            raise JobCancellationBlockedError(
                job_id=job_id,
                current_status=current.value,
                reason=f"Invalid job transition: {current.value} -> cancelled",
            )
        case unreachable:
            assert_never(unreachable)


def job_cancelled_event(
    request: HarnessJobCancellationRequest,
    job: HarnessJob,
    *,
    sequence: int,
    previous_status: HarnessJobStatus,
) -> PlotLotEvent:
    return _job_cancellation_event(
        request,
        job,
        sequence=sequence,
        status=PlotLotEventStatus.COMPLETED,
        previous_status=previous_status.value,
        current_status=HarnessJobStatus.CANCELLED.value,
        error=None,
    )


def blocked_job_cancellation_event(
    request: HarnessJobCancellationRequest,
    job: HarnessJob,
    *,
    sequence: int,
    error: JobCancellationBlockedError,
) -> PlotLotEvent:
    return _job_cancellation_event(
        request,
        job,
        sequence=sequence,
        status=PlotLotEventStatus.FAILED,
        previous_status=error.current_status,
        current_status=error.current_status,
        error=PlotLotEventError(
            code="invalid_job_transition",
            message=error.reason,
            details={"current_status": error.current_status},
        ),
    )


def _job_cancellation_event(
    request: HarnessJobCancellationRequest,
    job: HarnessJob,
    *,
    sequence: int,
    status: PlotLotEventStatus,
    previous_status: str,
    current_status: str,
    error: PlotLotEventError | None,
) -> PlotLotEvent:
    return PlotLotEvent(
        run_id=job.run_id,
        sequence=sequence,
        type=PlotLotEventType.JOB_CANCELLED,
        source=_event_source_for_execution_mode(request.execution_mode),
        status=status,
        source_mode=job.request.source_mode,
        execution_mode=request.execution_mode,
        idempotency_key=job.idempotency_key,
        payload={
            "job_id": str(job.job_id),
            "actor_user_id": request.actor_user_id,
            "reason": request.reason,
            "previous_status": previous_status,
            "current_status": current_status,
        },
        error=error,
    )


def _event_source_for_execution_mode(execution_mode: ExecutionMode) -> PlotLotEventSource:
    match execution_mode:
        case ExecutionMode.CLI:
            return PlotLotEventSource.CLI
        case ExecutionMode.TUI:
            return PlotLotEventSource.TUI
        case ExecutionMode.WORKER:
            return PlotLotEventSource.WORKER
        case ExecutionMode.API | ExecutionMode.LOCAL:
            return PlotLotEventSource.SYSTEM
        case unreachable:
            assert_never(unreachable)
