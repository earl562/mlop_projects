from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from plotlot.harness.events import HarnessEvent
from plotlot.land_use.models import PolicyDecision


def event_dicts(events: Sequence[HarnessEvent]) -> list[dict[str, Any]]:
    return [{"kind": event.kind, "id": event.id, "payload": event.payload} for event in events]


def tool_run_output_json(
    *,
    run_id: str,
    tool_run_id: str,
    status: str,
    decision: PolicyDecision,
    result_payload: dict[str, Any] | None,
    message: str | None,
    evidence_ids: Sequence[str],
    artifact_ids: Mapping[str, str],
    events: Sequence[HarnessEvent],
) -> dict[str, Any]:
    output = dict(result_payload or {})
    output["tool_run_trace"] = {
        "run_id": run_id,
        "tool_run_id": tool_run_id,
        "status": status,
        "decision": decision.model_dump(),
        "message": message,
        "evidence_ids": list(evidence_ids),
        "artifact_ids": dict(artifact_ids),
        "events": event_dicts(events),
    }
    return output
