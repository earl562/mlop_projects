from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic import Field, TypeAdapter, field_validator

from plotlot.harness.contracts import (
    EvidenceId,
    JsonObject,
    PlotLotEventType,
    RunId,
    ToolCall,
    ToolCallId,
)
from plotlot.harness.contracts.base import HarnessContract, utc_now
from plotlot.harness.tool_router import HarnessToolCallResult

TOOL_CALL_STORE_PATH_ENV = "PLOTLOT_HARNESS_TOOL_CALL_STORE_PATH"
JsonObjectAdapter = TypeAdapter(JsonObject)


@dataclass(frozen=True, slots=True)
class ToolCallNotFoundError(Exception):
    tool_call_id: ToolCallId

    def __str__(self) -> str:
        return f"Tool call not found: {self.tool_call_id}"


class StoredToolCall(HarnessContract):
    item: ToolCall
    saved_at: datetime = Field(default_factory=utc_now)

    @field_validator("saved_at")
    @classmethod
    def _saved_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("saved_at must be timezone-aware")
        return value


class ToolCallLedgerSnapshot(HarnessContract):
    tool_calls: dict[str, StoredToolCall] = Field(default_factory=dict)


class LocalToolCallLedger:
    def __init__(self, path: Path) -> None:
        self._path = path

    def save_tool_call(self, item: ToolCall) -> ToolCall:
        snapshot = self._read_snapshot()
        tool_calls = dict(snapshot.tool_calls)
        tool_calls[str(item.tool_call_id)] = StoredToolCall(item=item)
        self._write_snapshot(ToolCallLedgerSnapshot(tool_calls=tool_calls))
        return item

    def get_tool_call(self, tool_call_id: ToolCallId) -> ToolCall:
        snapshot = self._read_snapshot()
        stored = snapshot.tool_calls.get(str(tool_call_id))
        if stored is None:
            raise ToolCallNotFoundError(tool_call_id=tool_call_id)
        return stored.item

    def list_tool_calls(self, run_id: RunId | str | None = None) -> list[ToolCall]:
        snapshot = self._read_snapshot()
        records = sorted(snapshot.tool_calls.values(), key=lambda item: item.saved_at, reverse=True)
        if run_id is None:
            return [record.item for record in records]
        run = RunId(str(run_id))
        return [record.item for record in records if record.item.run_id == run]

    def _read_snapshot(self) -> ToolCallLedgerSnapshot:
        if not self._path.exists():
            return ToolCallLedgerSnapshot()
        raw = self._path.read_text(encoding="utf-8")
        if not raw.strip():
            return ToolCallLedgerSnapshot()
        return ToolCallLedgerSnapshot.model_validate_json(raw)

    def _write_snapshot(self, snapshot: ToolCallLedgerSnapshot) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")


def tool_call_from_result(result: HarnessToolCallResult) -> ToolCall:
    return ToolCall(
        tool_call_id=result.tool_call_id,
        run_id=result.run_id,
        event_id=result.events[0].event_id if result.events else None,
        tool_name=result.tool_name,
        args=result.args,
        result_summary=_result_summary(result),
        result_payload=result.payload,
        status=result.status.value,
        permission_decision=JsonObjectAdapter.validate_python(
            result.policy_decision.model_dump(mode="json")
        ),
        started_at=_event_time(result, PlotLotEventType.TOOL_STARTED),
        completed_at=result.events[-1].created_at if result.events else utc_now(),
        error=result.error,
        linked_evidence_ids=[EvidenceId(value) for value in result.evidence_ids],
    )


def default_tool_call_ledger_path() -> Path:
    configured = os.environ.get(TOOL_CALL_STORE_PATH_ENV)
    if configured:
        return Path(configured).expanduser()
    state_home = os.environ.get("XDG_STATE_HOME")
    base = Path(state_home).expanduser() if state_home else Path.home() / ".local" / "state"
    return base / "plotlot" / "harness-tool-calls.json"


def default_tool_call_ledger() -> LocalToolCallLedger:
    return LocalToolCallLedger(default_tool_call_ledger_path())


def _event_time(result: HarnessToolCallResult, event_type: PlotLotEventType) -> datetime | None:
    event = next((item for item in result.events if item.type == event_type), None)
    return None if event is None else event.created_at


def _result_summary(result: HarnessToolCallResult) -> str:
    if result.error is not None:
        return result.error.message
    return f"{result.tool_name} {result.status.value}"
