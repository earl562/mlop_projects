from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from plotlot.harness.contracts.base import HarnessContract


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    WAITING_FOR_SOURCE = "waiting_for_source"
    VERIFYING = "verifying"
    GENERATING_REPORT = "generating_report"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunTransitionResult(HarnessContract):
    previous: RunStatus
    current: RunStatus


@dataclass(frozen=True, slots=True)
class InvalidRunTransitionError(Exception):
    current: RunStatus
    target: RunStatus

    def __str__(self) -> str:
        return f"Invalid analysis run transition: {self.current.value} -> {self.target.value}"


ALLOWED_RUN_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.QUEUED: frozenset({RunStatus.RUNNING, RunStatus.CANCELLED}),
    RunStatus.RUNNING: frozenset(
        {
            RunStatus.WAITING_FOR_APPROVAL,
            RunStatus.WAITING_FOR_SOURCE,
            RunStatus.VERIFYING,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }
    ),
    RunStatus.WAITING_FOR_APPROVAL: frozenset({RunStatus.RUNNING, RunStatus.CANCELLED}),
    RunStatus.WAITING_FOR_SOURCE: frozenset({RunStatus.RUNNING}),
    RunStatus.VERIFYING: frozenset({RunStatus.GENERATING_REPORT, RunStatus.FAILED}),
    RunStatus.GENERATING_REPORT: frozenset({RunStatus.COMPLETED, RunStatus.FAILED}),
    RunStatus.COMPLETED: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.CANCELLED: frozenset(),
}


def transition_run_status(current: RunStatus, target: RunStatus) -> RunTransitionResult:
    allowed = ALLOWED_RUN_TRANSITIONS[current]
    if target in allowed:
        return RunTransitionResult(previous=current, current=target)
    raise InvalidRunTransitionError(current=current, target=target)
