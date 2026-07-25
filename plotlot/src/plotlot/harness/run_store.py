from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic import Field, field_validator

from plotlot.harness.contracts import PlotLotEvent, PlotLotEventStatus
from plotlot.harness.contracts.base import (
    HarnessContract,
    JsonObject,
    RunId,
    SourceMode,
    utc_now,
)
from plotlot.harness.run_cancellation import (
    HarnessRunCancellationRequest,
    RunCancellationBlockedError,
    blocked_cancellation_event,
    cancelled_event,
    run_status,
    transition_to_cancelled,
)
from plotlot.harness.fixture_runs import FixtureDealRunResult

STORE_PATH_ENV = "PLOTLOT_HARNESS_STORE_PATH"


@dataclass(frozen=True, slots=True)
class HarnessRunNotFoundError(Exception):
    run_id: RunId

    def __str__(self) -> str:
        return f"Harness run not found: {self.run_id}"


class StoredHarnessRun(HarnessContract):
    result: FixtureDealRunResult
    saved_at: datetime = Field(default_factory=utc_now)

    @field_validator("saved_at")
    @classmethod
    def _saved_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("saved_at must be timezone-aware")
        return value


class HarnessReplayTimelineItem(HarnessContract):
    sequence: int = Field(ge=1)
    type: str = Field(min_length=1)
    source: str = Field(min_length=1)
    status: str | None = None


class HarnessReplayBundle(HarnessContract):
    run_id: RunId
    status: str = Field(min_length=1)
    source_mode: SourceMode
    report_id: str = Field(min_length=1)
    evidence_ids: list[str]
    verification_status: str = Field(min_length=1)
    event_count: int = Field(ge=0)
    timeline: list[HarnessReplayTimelineItem]
    failed_event: PlotLotEvent | None = None
    metadata: JsonObject = Field(default_factory=dict)


class HarnessStoreSnapshot(HarnessContract):
    runs: dict[str, StoredHarnessRun] = Field(default_factory=dict)


class LocalHarnessRunStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def save_run(self, result: FixtureDealRunResult) -> StoredHarnessRun:
        snapshot = self._read_snapshot()
        stored = StoredHarnessRun(result=result)
        runs = dict(snapshot.runs)
        runs[str(result.run_id)] = stored
        self._write_snapshot(HarnessStoreSnapshot(runs=runs))
        return stored

    def get_run(self, run_id: RunId) -> FixtureDealRunResult:
        snapshot = self._read_snapshot()
        stored = snapshot.runs.get(str(run_id))
        if stored is None:
            raise HarnessRunNotFoundError(run_id=run_id)
        return stored.result

    def list_runs(self) -> list[FixtureDealRunResult]:
        snapshot = self._read_snapshot()
        ordered = sorted(snapshot.runs.values(), key=lambda run: run.saved_at)
        return [run.result for run in ordered]

    def get_events(self, run_id: RunId) -> list[PlotLotEvent]:
        return self.get_run(run_id).events

    def append_events(self, run_id: RunId, events: list[PlotLotEvent]) -> list[PlotLotEvent]:
        if not events:
            return []
        snapshot = self._read_snapshot()
        stored = snapshot.runs.get(str(run_id))
        if stored is None:
            raise HarnessRunNotFoundError(run_id=run_id)
        existing_events = list(stored.result.events)
        next_sequence = len(existing_events) + 1
        appended = [
            event.model_copy(update={"run_id": run_id, "sequence": next_sequence + index})
            for index, event in enumerate(events)
        ]
        updated_run = stored.result.model_copy(update={"events": [*existing_events, *appended]})
        runs = dict(snapshot.runs)
        runs[str(run_id)] = StoredHarnessRun(result=updated_run, saved_at=stored.saved_at)
        self._write_snapshot(HarnessStoreSnapshot(runs=runs))
        return appended

    def cancel_run(self, request: HarnessRunCancellationRequest) -> FixtureDealRunResult:
        snapshot = self._read_snapshot()
        stored = snapshot.runs.get(str(request.run_id))
        if stored is None:
            raise HarnessRunNotFoundError(run_id=request.run_id)
        existing_events = list(stored.result.events)
        try:
            previous_status = run_status(stored.result.status, run_id=request.run_id)
            target_status = transition_to_cancelled(previous_status, run_id=request.run_id)
        except RunCancellationBlockedError as exc:
            failed_event = blocked_cancellation_event(
                request,
                stored.result,
                sequence=len(existing_events) + 1,
                error=exc,
            )
            updated_run = stored.result.model_copy(update={"events": [*existing_events, failed_event]})
            runs = dict(snapshot.runs)
            runs[str(request.run_id)] = StoredHarnessRun(result=updated_run, saved_at=stored.saved_at)
            self._write_snapshot(HarnessStoreSnapshot(runs=runs))
            raise
        cancel_event = cancelled_event(
            request,
            stored.result,
            sequence=len(existing_events) + 1,
            previous_status=previous_status,
        )
        updated_run = stored.result.model_copy(
            update={"status": target_status.value, "events": [*existing_events, cancel_event]}
        )
        runs = dict(snapshot.runs)
        runs[str(request.run_id)] = StoredHarnessRun(result=updated_run, saved_at=stored.saved_at)
        self._write_snapshot(HarnessStoreSnapshot(runs=runs))
        return updated_run

    def replay_run(self, run_id: RunId) -> HarnessReplayBundle:
        result = self.get_run(run_id)
        failed = next(
            (event for event in result.events if event.status == PlotLotEventStatus.FAILED),
            None,
        )
        return HarnessReplayBundle(
            run_id=result.run_id,
            status=result.status,
            source_mode=result.source_mode,
            report_id=result.report_id,
            evidence_ids=result.evidence_ids,
            verification_status=result.verification_status,
            event_count=len(result.events),
            timeline=[
                HarnessReplayTimelineItem(
                    sequence=event.sequence,
                    type=event.type.value,
                    source=event.source.value,
                    status=event.status.value if event.status is not None else None,
                )
                for event in result.events
            ],
            failed_event=failed,
            metadata={"preliminary": result.preliminary},
        )

    def _read_snapshot(self) -> HarnessStoreSnapshot:
        if not self._path.exists():
            return HarnessStoreSnapshot()
        raw = self._path.read_text(encoding="utf-8")
        if not raw.strip():
            return HarnessStoreSnapshot()
        return HarnessStoreSnapshot.model_validate_json(raw)

    def _write_snapshot(self, snapshot: HarnessStoreSnapshot) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")


def default_harness_store_path() -> Path:
    configured = os.environ.get(STORE_PATH_ENV)
    if configured:
        return Path(configured).expanduser()
    state_home = os.environ.get("XDG_STATE_HOME")
    base = Path(state_home).expanduser() if state_home else Path.home() / ".local" / "state"
    return base / "plotlot" / "harness-runs.json"


def default_harness_run_store() -> LocalHarnessRunStore:
    return LocalHarnessRunStore(default_harness_store_path())
