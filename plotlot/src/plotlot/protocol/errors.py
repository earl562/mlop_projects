from __future__ import annotations

from typing import Literal

from pydantic import Field, StrictBool

from plotlot.protocol.base import ProtocolModel


ProtocolErrorCode = Literal[
    "REQUEST_INVALID",
    "UNKNOWN_PROTOCOL_VERSION",
    "AUTH_CONTEXT_INVALID",
    "DEADLINE_EXCEEDED",
    "IDEMPOTENCY_BODY_CONFLICT",
    "STALE_REVISION",
    "RUN_NOT_FOUND",
    "REVISION_NOT_FOUND",
    "CURSOR_INVALID",
    "CANCELLATION_CONFLICT",
    "REPLAY_CONFLICT",
    "ENGINE_UNAVAILABLE",
    "INTERNAL_ERROR",
]
ProtocolErrorCategory = Literal[
    "validation", "authentication", "conflict", "not-found", "transient", "internal"
]


class ProtocolErrorV1(ProtocolModel):
    schema_version: Literal["ProtocolErrorV1"]
    code: ProtocolErrorCode
    category: ProtocolErrorCategory
    retryable: StrictBool
    http_status: Literal[400, 401, 404, 409, 422, 429, 500, 503, 504]
    message: str = Field(min_length=1)
    request_id: str = Field(pattern=r"^request_[A-Za-z0-9_-]+$")
    engine_run_id: str | None = Field(default=None, pattern=r"^engrun_[A-Za-z0-9_-]+$")
    engine_revision_id: str | None = Field(default=None, pattern=r"^engrev_[A-Za-z0-9_-]+$")
