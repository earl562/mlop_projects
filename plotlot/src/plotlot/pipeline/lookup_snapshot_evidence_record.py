from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from plotlot.core.lookup_snapshot import EvidenceId, FieldKey
from plotlot.pipeline.lookup_snapshot_json import JsonValue
from plotlot.pipeline.lookup_snapshot_trace import TraceSourceRetrieval


@dataclass(frozen=True, slots=True)
class LookupSnapshotEvidenceRecord:
    evidence_id: EvidenceId
    source_type: str
    source_authority: str
    publisher: str
    source_url: str
    source_title: str
    retrieved_at: str
    effective_date: str
    parser_version: str
    schema_version: str
    raw_artifact_ref: str
    query_parameters: tuple[str, ...]
    normalized_fields: tuple[FieldKey, ...]
    calculation_outputs: tuple[str, ...]
    lineage: tuple[str, ...]
    confidence: float
    quality_score: float
    quality_flags: tuple[str, ...]
    warnings: tuple[str, ...]


def evidence_records_to_dicts(
    records: Iterable[LookupSnapshotEvidenceRecord],
) -> list[dict[str, JsonValue]]:
    return [_evidence_record_to_dict(record) for record in records]


def trace_source_retrievals(
    evidence_records: tuple[LookupSnapshotEvidenceRecord, ...],
) -> tuple[TraceSourceRetrieval, ...]:
    return tuple(
        TraceSourceRetrieval(
            evidence_id=record.evidence_id,
            source_type=record.source_type,
            source_authority=record.source_authority,
            publisher=record.publisher,
            source_url=record.source_url,
            source_title=record.source_title,
            retrieved_at=record.retrieved_at,
            effective_date=record.effective_date,
            parser_version=record.parser_version,
            schema_version=record.schema_version,
            raw_artifact_ref=record.raw_artifact_ref,
            query_parameters=record.query_parameters,
            lineage=record.lineage,
            quality_score=record.quality_score,
            quality_flags=record.quality_flags,
            warnings=record.warnings,
        )
        for record in evidence_records
    )


def _evidence_record_to_dict(record: LookupSnapshotEvidenceRecord) -> dict[str, JsonValue]:
    return {
        "evidence_id": str(record.evidence_id),
        "source_type": record.source_type,
        "source_authority": record.source_authority,
        "publisher": record.publisher,
        "source_url": record.source_url,
        "source_title": record.source_title,
        "retrieved_at": record.retrieved_at,
        "effective_date": record.effective_date,
        "parser_version": record.parser_version,
        "schema_version": record.schema_version,
        "raw_artifact_ref": record.raw_artifact_ref,
        "query_parameters": _string_list(record.query_parameters),
        "normalized_fields": _string_list(record.normalized_fields),
        "calculation_outputs": _string_list(record.calculation_outputs),
        "lineage": _string_list(record.lineage),
        "confidence": record.confidence,
        "quality_score": record.quality_score,
        "quality_flags": _string_list(record.quality_flags),
        "warnings": _string_list(record.warnings),
    }


def _string_list(values: Iterable[str]) -> list[JsonValue]:
    return [str(value) for value in values]
