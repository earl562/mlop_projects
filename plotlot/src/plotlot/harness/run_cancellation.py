from __future__ import annotations

from dataclasses import dataclass
from typing import assert_never

from pydantic import Field

from plotlot.harness.contracts import (
    ExecutionMode,
    PlotLotEvent,
    PlotLotEventError,
    PlotLotEventSource,
    PlotLotEventStatus,
    PlotLotEventType,
)
from plotlot.harness.contracts.base import HarnessContract, RunId
from plotlot.harness.contracts.run_state import (
    InvalidRunTransitionError,
    RunStatus,
    transition_run_status,
)
from plotlot.harness.fixture_runs import FixtureDealRunResult


@dataclass(frozen=True, slots=True)
class RunCancellationBlockedError(Exception):
    run_id: RunId
    current_status: str
    reason: str

    def __str__(self) -> str:
        return f"Run cancellation blocked for {self.run_id}: {self.reason}"


class HarnessRunCancellationRequest(HarnessContract):
    run_id: RunId
    actor_user_id: str = Field(min_length=1)
    reason: str = Field(default="Cancellation requested.", min_length=1)
    execution_mode: ExecutionMode = ExecutionMode.LOCAL


def run_status(value: str, *, run_id: RunId) -> RunStatus:
    try:
        return RunStatus(value)
    except ValueError as exc:
        raise RunCancellationBlockedError(
            run_id=run_id,
            current_status=value,
            reason=f"Unknown run status: {value}",
        ) from exc


def transition_to_cancelled(current: RunStatus, *, run_id: RunId) -> RunStatus:
    try:
        return transition_run_status(current, RunStatus.CANCELLED).current
    except InvalidRunTransitionError as exc:
        raise RunCancellationBlockedError(
            run_id=run_id,
            current_status=current.value,
            reason=str(exc),
        ) from exc


def cancelled_event(
    request: HarnessRunCancellationRequest,
    result: FixtureDealRunResult,
    *,
    sequence: int,
    previous_status: RunStatus,
) -> PlotLotEvent:
    return _cancellation_event(
        request,
        result,
        sequence=sequence,
        status=PlotLotEventStatus.COMPLETED,
        previous_status=previous_status.value,
        error=None,
    )


def blocked_cancellation_event(
    request: HarnessRunCancellationRequest,
    result: FixtureDealRunResult,
    *,
    sequence: int,
    error: RunCancellationBlockedError,
) -> PlotLotEvent:
    return _cancellation_event(
        request,
        result,
        sequence=sequence,
        status=PlotLotEventStatus.FAILED,
        previous_status=error.current_status,
        error=PlotLotEventError(
            code="invalid_run_transition",
            message=error.reason,
            details={"current_status": error.current_status},
        ),
    )


def _cancellation_event(
    request: HarnessRunCancellationRequest,
    result: FixtureDealRunResult,
    *,
    sequence: int,
    status: PlotLotEventStatus,
    previous_status: str,
    error: PlotLotEventError | None,
) -> PlotLotEvent:
    return PlotLotEvent(
        run_id=request.run_id,
        sequence=sequence,
        type=PlotLotEventType.RUN_CANCELLED,
        source=_event_source_for_execution_mode(request.execution_mode),
        status=status,
        source_mode=result.source_mode,
        execution_mode=request.execution_mode,
        payload={
            "actor_user_id": request.actor_user_id,
            "reason": request.reason,
            "previous_status": previous_status,
            "current_status": RunStatus.CANCELLED.value,
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
