from __future__ import annotations

from dataclasses import dataclass

from plotlot.harness.agent_run import AgentRunRecord


@dataclass(frozen=True, slots=True)
class StoredAgentRun:
    lookup_snapshot_id: str
    record: AgentRunRecord


_AGENT_RUNS: dict[str, StoredAgentRun] = {}


def save_agent_run(record: AgentRunRecord, lookup_snapshot_id: str) -> StoredAgentRun:
    stored = StoredAgentRun(lookup_snapshot_id=lookup_snapshot_id, record=record)
    _AGENT_RUNS[str(record.run_id)] = stored
    return stored


def get_stored_agent_run(run_id: str, workspace_id: str | None = None) -> StoredAgentRun | None:
    stored = _AGENT_RUNS.get(run_id)
    if stored is None:
        return None
    if workspace_id is not None and stored.record.workspace_id != workspace_id:
        return None
    return stored


def clear_agent_run_store() -> None:
    _AGENT_RUNS.clear()
