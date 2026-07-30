from __future__ import annotations

import fcntl
import json
import logging
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

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
logger = logging.getLogger(__name__)


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
        with self._locked():
            snapshot = self._read_snapshot_unlocked()
            tool_calls = dict(snapshot.tool_calls)
            tool_calls[str(item.tool_call_id)] = StoredToolCall(item=item)
            self._write_snapshot_unlocked(ToolCallLedgerSnapshot(tool_calls=tool_calls))
        return item

    def get_tool_call(self, tool_call_id: ToolCallId) -> ToolCall:
        with self._locked():
            snapshot = self._read_snapshot_unlocked()
            stored = snapshot.tool_calls.get(str(tool_call_id))
        if stored is None:
            raise ToolCallNotFoundError(tool_call_id=tool_call_id)
        return stored.item

    def list_tool_calls(self, run_id: RunId | str | None = None) -> list[ToolCall]:
        with self._locked():
            snapshot = self._read_snapshot_unlocked()
        records = sorted(snapshot.tool_calls.values(), key=lambda item: item.saved_at, reverse=True)
        if run_id is None:
            return [record.item for record in records]
        run = RunId(str(run_id))
        return [record.item for record in records if record.item.run_id == run]

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self._path.with_name(f"{self._path.name}.lock")
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _read_snapshot_unlocked(self) -> ToolCallLedgerSnapshot:
        if not self._path.exists():
            return ToolCallLedgerSnapshot()
        raw = self._path.read_text(encoding="utf-8")
        if not raw.strip():
            return ToolCallLedgerSnapshot()
        try:
            return ToolCallLedgerSnapshot.model_validate_json(raw)
        except ValueError:
            recovered = self._recover_concatenated_snapshots(raw)
            if recovered is None:
                raise
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
            backup_path = self._path.with_name(f"{self._path.name}.corrupt-{timestamp}")
            backup_path.write_text(raw, encoding="utf-8")
            self._write_snapshot_unlocked(recovered)
            logger.warning(
                "Recovered concatenated tool-call snapshots; original preserved at %s",
                backup_path,
            )
            return recovered

    def _recover_concatenated_snapshots(self, raw: str) -> ToolCallLedgerSnapshot | None:
        decoder = json.JSONDecoder()
        offset = 0
        snapshots: list[ToolCallLedgerSnapshot] = []
        try:
            while offset < len(raw):
                while offset < len(raw) and raw[offset].isspace():
                    offset += 1
                if offset >= len(raw):
                    break
                value, offset = decoder.raw_decode(raw, offset)
                snapshots.append(ToolCallLedgerSnapshot.model_validate(value))
        except (json.JSONDecodeError, ValueError):
            return None
        if len(snapshots) < 2:
            return None
        merged: dict[str, StoredToolCall] = {}
        for snapshot in snapshots:
            merged.update(snapshot.tool_calls)
        return ToolCallLedgerSnapshot(tool_calls=merged)

    def _write_snapshot_unlocked(self, snapshot: ToolCallLedgerSnapshot) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temporary_name = tempfile.mkstemp(
            dir=self._path.parent,
            prefix=f".{self._path.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as temporary_file:
                temporary_file.write(snapshot.model_dump_json(indent=2))
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, self._path)
        finally:
            temporary_path.unlink(missing_ok=True)


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
