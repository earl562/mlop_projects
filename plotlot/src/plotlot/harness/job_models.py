from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import NewType

from pydantic import BaseModel, ConfigDict, Field, JsonValue


JobId = NewType("JobId", str)
LeaseToken = NewType("LeaseToken", str)
OutboxId = NewType("OutboxId", str)


class JobStatus(StrEnum):
    QUEUED = "queued"
    LEASED = "leased"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    DEAD_LETTERED = "dead_lettered"


class OutboxStatus(StrEnum):
    PENDING = "pending"
    LEASED = "leased"
    RETRY_WAIT = "retry_wait"
    SENT = "sent"
    DEAD_LETTERED = "dead_lettered"


class JobCreate(BaseModel):
    model_config = ConfigDict(frozen=True)

    tenant_id: str = Field(min_length=1, max_length=120)
    idempotency_key: str = Field(min_length=1, max_length=200)
    body: dict[str, JsonValue]
    max_attempts: int = Field(default=3, ge=1, le=20)
    replay_of_job_id: JobId | None = None


class JobRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    tenant_id: str
    job_id: JobId
    idempotency_key: str
    body_sha256: str
    body: dict[str, JsonValue]
    status: JobStatus
    attempts: int
    max_attempts: int
    replay_of_job_id: JobId | None
    last_error: str | None
    lease_token: LeaseToken | None
    lease_expires_at: datetime | None
    available_at: datetime
    created_at: datetime
    updated_at: datetime


class JobEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    cursor: int
    tenant_id: str
    job_id: JobId
    event_type: str
    payload: dict[str, JsonValue]
    created_at: datetime


class OutboxRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    tenant_id: str
    outbox_id: OutboxId
    job_id: JobId
    receipt_key: str
    payload: dict[str, JsonValue]
    status: OutboxStatus
    attempts: int
    max_attempts: int
    lease_token: LeaseToken | None
    lease_expires_at: datetime | None
    last_error: str | None
    sent_at: datetime | None


@dataclass(frozen=True, slots=True)
class JobEnqueueResult:
    job: JobRecord
    reused: bool


@dataclass(frozen=True, slots=True)
class IdempotencyConflictError(Exception):
    tenant_id: str
    idempotency_key: str

    def __str__(self) -> str:
        return "idempotency key was already used with a different body"


@dataclass(frozen=True, slots=True)
class InvalidJobTransitionError(Exception):
    job_id: JobId
    expected: str

    def __str__(self) -> str:
        return f"job {self.job_id} is not in required state: {self.expected}"


@dataclass(frozen=True, slots=True)
class JobNotFoundError(Exception):
    tenant_id: str
    job_id: JobId

    def __str__(self) -> str:
        return f"job {self.job_id} was not found in tenant {self.tenant_id}"


@dataclass(frozen=True, slots=True)
class LeaseInvariantError(Exception):
    detail: str

    def __str__(self) -> str:
        return self.detail
