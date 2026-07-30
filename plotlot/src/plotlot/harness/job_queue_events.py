from __future__ import annotations

from dataclasses import dataclass

from plotlot.harness.contracts import (
    ExecutionMode,
    JobId,
    PlotLotEvent,
    PlotLotEventSource,
    PlotLotEventStatus,
    PlotLotEventType,
    RunId,
    SourceMode,
)


@dataclass(frozen=True, slots=True)
class JobEventInput:
    run_id: RunId
    sequence: int
    event_type: PlotLotEventType
    source: PlotLotEventSource
    source_mode: SourceMode
    job_id: JobId
    idempotency_key: str | None


def job_event(input_data: JobEventInput) -> PlotLotEvent:
    return PlotLotEvent(
        run_id=input_data.run_id,
        sequence=input_data.sequence,
        type=input_data.event_type,
        source=input_data.source,
        status=PlotLotEventStatus.COMPLETED,
        source_mode=input_data.source_mode,
        execution_mode=ExecutionMode.WORKER,
        idempotency_key=input_data.idempotency_key,
        payload={"job_id": str(input_data.job_id)},
    )
