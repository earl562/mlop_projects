from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from pydantic import Field, field_validator

from plotlot.harness.contracts import JobId, PlotLotEvent, PlotLotEventSource, PlotLotEventType, RunId
from plotlot.harness.contracts.base import HarnessContract, utc_now
from plotlot.harness.fixture_runs import FixtureDealRunRequest


class HarnessJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DEAD_LETTERED = "dead_lettered"


class HarnessJobType(StrEnum):
    ANALYSIS_RUN = "analysis_run"


@dataclass(frozen=True, slots=True)
class HarnessJobNotFoundError(Exception):
    job_id: JobId

    def __str__(self) -> str:
        return f"Harness job not found: {self.job_id}"


@dataclass(frozen=True, slots=True)
class JobUpdate:
    status: HarnessJobStatus
    event_type: PlotLotEventType
    source: PlotLotEventSource
    attempts: int | None = None
    run_id: RunId | None = None


class HarnessJob(HarnessContract):
    job_id: JobId
    job_type: HarnessJobType
    status: HarnessJobStatus
    request: FixtureDealRunRequest
    run_id: RunId
    idempotency_key: str | None = None
    attempts: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=3, ge=1)
    events: list[PlotLotEvent]
    error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("created_at", "updated_at")
    @classmethod
    def _timestamps_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("job timestamps must be timezone-aware")
        return value


class HarnessJobQueueSnapshot(HarnessContract):
    jobs: dict[str, HarnessJob] = Field(default_factory=dict)
