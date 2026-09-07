from __future__ import annotations

from datetime import timedelta
from typing import Literal, Self

from pydantic import AwareDatetime, Field, model_validator
from pydantic_core import PydanticCustomError

from plotlot.protocol.base import ProtocolModel


class PlotLotHostContextV1(ProtocolModel):
    protocol_version: Literal["plotlot-byright.v1"]
    tenant_id: str = Field(pattern=r"^tenant_[A-Za-z0-9_-]+$")
    workspace_id: str = Field(pattern=r"^workspace_[A-Za-z0-9_-]+$")
    host_analysis_id: str = Field(pattern=r"^analysis_[A-Za-z0-9_-]+$")
    host_run_id: str = Field(pattern=r"^hostrun_[A-Za-z0-9_-]+$")
    request_id: str = Field(pattern=r"^request_[A-Za-z0-9_-]+$")
    idempotency_key: str = Field(min_length=16, max_length=200)
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    submitted_at: AwareDatetime
    deadline_at: AwareDatetime

    @model_validator(mode="after")
    def deadline_is_future_and_bounded(self) -> Self:
        duration = self.deadline_at - self.submitted_at
        if duration <= timedelta(0):
            raise PydanticCustomError(
                "protocol_deadline_expired",
                "deadline_at must follow submitted_at",
            )
        if duration > timedelta(minutes=30):
            raise PydanticCustomError(
                "protocol_deadline_unbounded",
                "protocol deadline cannot exceed thirty minutes",
            )
        return self


class ActorContextV1(ProtocolModel):
    actor_type: Literal["user", "service"]
    actor_id: str = Field(min_length=1)
    tenant_id: str = Field(pattern=r"^tenant_[A-Za-z0-9_-]+$")
    role: Literal["owner", "admin", "analyst", "reviewer", "viewer", "service"]
    capabilities: tuple[str, ...] = Field(min_length=1)
    verified_at: AwareDatetime
    token_id: str = Field(min_length=1)
