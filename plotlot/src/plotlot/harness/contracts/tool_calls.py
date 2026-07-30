from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from plotlot.harness.contracts.base import (
    EventId,
    EvidenceId,
    HarnessContract,
    JsonObject,
    RunId,
    ToolCallId,
    utc_now,
)
from plotlot.harness.contracts.events import PlotLotEventError


class ToolCall(HarnessContract):
    tool_call_id: ToolCallId
    run_id: RunId
    event_id: EventId | None = None
    tool_name: str = Field(min_length=1)
    args: JsonObject = Field(default_factory=dict)
    result_summary: str | None = None
    result_payload: JsonObject = Field(default_factory=dict)
    status: str = Field(min_length=1)
    permission_decision: JsonObject = Field(default_factory=dict)
    started_at: datetime | None = None
    completed_at: datetime = Field(default_factory=utc_now)
    error: PlotLotEventError | None = None
    linked_evidence_ids: list[EvidenceId] = Field(default_factory=list)

    @field_validator("started_at", "completed_at")
    @classmethod
    def _tool_call_timestamps_must_be_timezone_aware(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("tool call timestamps must be timezone-aware")
        return value
