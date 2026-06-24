from __future__ import annotations

from plotlot.core.lookup_snapshot import LookupSnapshot
from plotlot.pipeline.lookup_snapshot_json import JsonValue
from plotlot.pipeline.lookup_snapshot_serialization import lookup_snapshot_to_dict
from plotlot.pipeline.lookup_snapshot_store import (
    StoredLookupSnapshot,
    evidence_records_to_dicts,
    trace_record_to_dict,
)
from plotlot.pipeline.lookup_snapshot_repository_types import PersistedLookupSnapshotRecord


def analysis_run_output(
    snapshot: LookupSnapshot,
    stored: StoredLookupSnapshot,
) -> dict[str, JsonValue]:
    evidence_records: list[JsonValue] = []
    for record in evidence_records_to_dicts(stored.evidence_records):
        evidence_records.append(record)
    return {
        "lookup_snapshot_id": str(snapshot.lookup_snapshot_id),
        "run_id": str(snapshot.run_id),
        "lookup_snapshot": lookup_snapshot_to_dict(snapshot),
        "evidence_records": evidence_records,
        "trace_record": trace_record_to_dict(stored.trace_record),
    }


def persisted_record_from_payload(
    payload: JsonValue,
) -> PersistedLookupSnapshotRecord | None:
    snapshot_json = json_object(payload, "lookup_snapshot")
    evidence_records = json_objects(payload, "evidence_records")
    trace_record = json_object(payload, "trace_record")
    if snapshot_json is None or trace_record is None:
        return None
    return PersistedLookupSnapshotRecord(
        snapshot_json=snapshot_json,
        evidence_records=evidence_records,
        trace_record=trace_record,
    )


def json_object(payload: JsonValue, key: str) -> dict[str, JsonValue] | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get(key)
    if not isinstance(value, dict):
        return None
    return value


def json_objects(payload: JsonValue, key: str) -> tuple[dict[str, JsonValue], ...]:
    if not isinstance(payload, dict):
        return ()
    value = payload.get(key)
    if not isinstance(value, list):
        return ()
    records: list[dict[str, JsonValue]] = []
    for item in value:
        if isinstance(item, dict):
            records.append(item)
    return tuple(records)
