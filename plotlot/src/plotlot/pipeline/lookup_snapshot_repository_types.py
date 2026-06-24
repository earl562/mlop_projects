from __future__ import annotations

from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5

from plotlot.pipeline.lookup_snapshot_json import JsonValue

DEFAULT_LOOKUP_WORKSPACE_ID = "default-workspace"
DEFAULT_LOOKUP_PROJECT_ID = str(uuid5(NAMESPACE_URL, "plotlot:default-workspace:lookup-project"))
LOOKUP_SNAPSHOT_SKILL_NAME = "lookup_correctness_snapshot"
LOOKUP_TOOL_NAME = "lookup_address"


@dataclass(frozen=True, slots=True)
class LookupSnapshotPersistenceContext:
    request_address: str
    workspace_id: str = DEFAULT_LOOKUP_WORKSPACE_ID
    project_id: str | None = None
    site_id: str | None = None
    actor_user_id: str = "anonymous"


@dataclass(frozen=True, slots=True)
class PersistedLookupSnapshotRecord:
    snapshot_json: dict[str, JsonValue]
    evidence_records: tuple[dict[str, JsonValue], ...]
    trace_record: dict[str, JsonValue]
