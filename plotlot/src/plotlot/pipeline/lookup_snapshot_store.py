from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from plotlot.core.lookup_snapshot import EvidenceId, FieldKey, LookupSnapshot
from plotlot.pipeline.lookup_snapshot_display_quality import apply_source_quality_to_snapshot
from plotlot.pipeline.lookup_snapshot_evidence_record import (
    LookupSnapshotEvidenceRecord,
    evidence_records_to_dicts as evidence_records_to_dicts,
    trace_source_retrievals,
)
from plotlot.pipeline.lookup_snapshot_source_quality import (
    SourceMetadataQualityInput,
    score_source_metadata,
)
from plotlot.pipeline.lookup_snapshot_trace import (
    LookupSnapshotTraceRecord,
    build_trace_record,
    snapshot_evidence_ids,
    trace_record_to_dict as trace_record_to_dict,
)

PARSER_VERSION = "lookup_snapshot_store.v1"
SCHEMA_VERSION = "lookup_snapshot_record.v1"

__all__ = (
    "LookupSnapshotEvidenceRecord",
    "StoredLookupSnapshot",
    "build_lookup_snapshot_evidence_records",
    "build_stored_lookup_snapshot",
    "clear_lookup_snapshot_store",
    "evidence_records_to_dicts",
    "get_lookup_snapshot",
    "save_lookup_snapshot",
    "trace_record_to_dict",
)


@dataclass(frozen=True, slots=True)
class StoredLookupSnapshot:
    snapshot: LookupSnapshot
    evidence_records: tuple[LookupSnapshotEvidenceRecord, ...]
    trace_record: LookupSnapshotTraceRecord


_SNAPSHOTS: dict[str, StoredLookupSnapshot] = {}


def save_lookup_snapshot(snapshot: LookupSnapshot) -> StoredLookupSnapshot:
    stored = build_stored_lookup_snapshot(snapshot)
    _SNAPSHOTS[str(snapshot.lookup_snapshot_id)] = stored
    return stored


def build_stored_lookup_snapshot(snapshot: LookupSnapshot) -> StoredLookupSnapshot:
    evidence_records = build_lookup_snapshot_evidence_records(snapshot)
    display_snapshot = apply_source_quality_to_snapshot(snapshot, evidence_records)
    return StoredLookupSnapshot(
        snapshot=display_snapshot,
        evidence_records=evidence_records,
        trace_record=build_trace_record(
            display_snapshot,
            _ingestion_quality_flags(display_snapshot, evidence_records),
            trace_source_retrievals(evidence_records),
        ),
    )


def get_lookup_snapshot(snapshot_id: str) -> StoredLookupSnapshot | None:
    return _SNAPSHOTS.get(snapshot_id)


def clear_lookup_snapshot_store() -> None:
    _SNAPSHOTS.clear()


def build_lookup_snapshot_evidence_records(
    snapshot: LookupSnapshot,
) -> tuple[LookupSnapshotEvidenceRecord, ...]:
    default_retrieved_at = datetime.now(UTC).isoformat()
    records: list[LookupSnapshotEvidenceRecord] = []
    for evidence_id in snapshot_evidence_ids(snapshot):
        fields = tuple(field.key for field in snapshot.fields if evidence_id in field.evidence_ids)
        calculation_outputs = _calculation_outputs(snapshot, evidence_id)
        source_metadata = snapshot.source_metadata_for(evidence_id)
        source_url = source_metadata.source_url if source_metadata is not None else ""
        source_type = (
            source_metadata.source_type
            if source_metadata is not None and source_metadata.source_type
            else _source_type(evidence_id)
        )
        source_authority = (
            source_metadata.source_authority
            if source_metadata is not None and source_metadata.source_authority
            else _source_authority(evidence_id)
        )
        source_title = (
            source_metadata.source_title
            if source_metadata is not None and source_metadata.source_title
            else str(evidence_id)
        )
        publisher = source_metadata.publisher if source_metadata is not None else ""
        retrieved_at = (
            source_metadata.retrieved_at
            if source_metadata is not None and source_metadata.retrieved_at
            else default_retrieved_at
        )
        effective_date = source_metadata.effective_date if source_metadata is not None else ""
        parser_version = (
            source_metadata.parser_version
            if source_metadata is not None and source_metadata.parser_version
            else PARSER_VERSION
        )
        schema_version = (
            source_metadata.schema_version
            if source_metadata is not None and source_metadata.schema_version
            else SCHEMA_VERSION
        )
        raw_artifact_ref = (
            source_metadata.raw_artifact_ref
            if source_metadata is not None and source_metadata.raw_artifact_ref
            else source_url or str(evidence_id)
        )
        query_parameters = source_metadata.query_parameters if source_metadata is not None else ()
        confidence = _evidence_confidence(snapshot, evidence_id)
        source_quality = score_source_metadata(
            SourceMetadataQualityInput(
                source_url=source_url,
                source_authority=source_authority,
                retrieved_at=retrieved_at,
                effective_date=effective_date,
                parser_version=parser_version,
                schema_version=schema_version,
                confidence=confidence,
            )
        )
        field_warnings = tuple(
            warning
            for field in snapshot.fields
            if evidence_id in field.evidence_ids
            for warning in field.warnings
        )
        warnings = _unique_strings((*field_warnings, *source_quality.flags))
        records.append(
            LookupSnapshotEvidenceRecord(
                evidence_id=evidence_id,
                source_type=source_type,
                source_authority=source_authority,
                publisher=publisher,
                source_url=source_url,
                source_title=source_title,
                retrieved_at=retrieved_at,
                effective_date=effective_date,
                parser_version=parser_version,
                schema_version=schema_version,
                raw_artifact_ref=raw_artifact_ref,
                query_parameters=query_parameters,
                normalized_fields=fields,
                calculation_outputs=calculation_outputs,
                lineage=_lineage(fields, calculation_outputs),
                confidence=confidence,
                quality_score=source_quality.score,
                quality_flags=source_quality.flags,
                warnings=warnings,
            )
        )
    return tuple(records)


def _ingestion_quality_flags(
    snapshot: LookupSnapshot,
    evidence_records: tuple[LookupSnapshotEvidenceRecord, ...],
) -> tuple[str, ...]:
    return _unique_strings(
        (
            *snapshot.warnings,
            *(warning for field in snapshot.fields for warning in field.warnings),
            *(flag for record in evidence_records for flag in record.quality_flags),
        )
    )


def _unique_strings(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return tuple(unique)


def _evidence_confidence(snapshot: LookupSnapshot, evidence_id: EvidenceId) -> float:
    confidences = [
        field.confidence for field in snapshot.fields if evidence_id in field.evidence_ids
    ]
    if not confidences:
        return 0.0
    return min(confidences)


def _calculation_outputs(snapshot: LookupSnapshot, evidence_id: EvidenceId) -> tuple[str, ...]:
    return tuple(
        calculation.output_label
        for calculation in snapshot.calculations
        if evidence_id in calculation.input_evidence_ids
    )


def _source_type(evidence_id: EvidenceId) -> str:
    value = str(evidence_id)
    if value.startswith("ev_parcel_"):
        return "authoritative_public_record"
    if value.startswith("ev_ordinance_"):
        return "authoritative_code_text"
    return "source_reference"


def _source_authority(evidence_id: EvidenceId) -> str:
    value = str(evidence_id)
    if value.startswith("ev_parcel_"):
        return "official_assessor"
    if value.startswith("ev_ordinance_"):
        return "official_zoning_ordinance"
    return "captured_lookup_source"


def _lineage(
    fields: tuple[FieldKey, ...],
    calculation_outputs: tuple[str, ...],
) -> tuple[str, ...]:
    field_lineage = tuple(
        f"source -> normalized evidence -> displayed field:{field}" for field in fields
    )
    calculation_lineage = tuple(
        f"source -> normalized evidence -> calculation output:{output}"
        for output in calculation_outputs
    )
    return (*field_lineage, *calculation_lineage)
