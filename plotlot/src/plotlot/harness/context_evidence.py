from __future__ import annotations

from dataclasses import dataclass

from plotlot.core.lookup_snapshot import EvidenceId, FieldKey, LookupSnapshot
from plotlot.pipeline.lookup_snapshot_store import (
    LookupSnapshotEvidenceRecord,
    build_lookup_snapshot_evidence_records,
)


@dataclass(frozen=True, slots=True)
class ContextEvidencePacket:
    evidence_id: EvidenceId
    source_type: str
    source_authority: str
    publisher: str
    source_title: str
    source_url: str
    retrieved_at: str
    effective_date: str
    parser_version: str
    schema_version: str
    raw_artifact_ref: str
    query_parameters: tuple[str, ...]
    referenced_field_keys: tuple[FieldKey, ...]
    calculation_outputs: tuple[str, ...]
    lineage: tuple[str, ...]
    confidence: float
    quality_score: float
    quality_flags: tuple[str, ...]
    warnings: tuple[str, ...]


def context_evidence_packets(
    snapshot: LookupSnapshot | None,
    evidence_ids: tuple[EvidenceId, ...],
) -> tuple[ContextEvidencePacket, ...]:
    if snapshot is None:
        return tuple(_empty_evidence_packet(evidence_id) for evidence_id in evidence_ids)
    records = {
        str(record.evidence_id): record
        for record in build_lookup_snapshot_evidence_records(snapshot)
    }
    return tuple(
        _context_evidence_packet(record)
        if (record := records.get(str(evidence_id))) is not None
        else _empty_evidence_packet(evidence_id)
        for evidence_id in evidence_ids
    )


def _empty_evidence_packet(evidence_id: EvidenceId) -> ContextEvidencePacket:
    return ContextEvidencePacket(
        evidence_id=evidence_id,
        source_type="",
        source_authority="",
        publisher="",
        source_title="",
        source_url="",
        retrieved_at="",
        effective_date="",
        parser_version="",
        schema_version="",
        raw_artifact_ref="",
        query_parameters=(),
        referenced_field_keys=(),
        calculation_outputs=(),
        lineage=(),
        confidence=0.0,
        quality_score=0.0,
        quality_flags=("missing_lookup_snapshot",),
        warnings=("missing_lookup_snapshot",),
    )


def _context_evidence_packet(record: LookupSnapshotEvidenceRecord) -> ContextEvidencePacket:
    return ContextEvidencePacket(
        evidence_id=record.evidence_id,
        source_type=record.source_type,
        source_authority=record.source_authority,
        publisher=record.publisher,
        source_title=record.source_title,
        source_url=record.source_url,
        retrieved_at=record.retrieved_at,
        effective_date=record.effective_date,
        parser_version=record.parser_version,
        schema_version=record.schema_version,
        raw_artifact_ref=record.raw_artifact_ref,
        query_parameters=record.query_parameters,
        referenced_field_keys=record.normalized_fields,
        calculation_outputs=record.calculation_outputs,
        lineage=record.lineage,
        confidence=record.confidence,
        quality_score=record.quality_score,
        quality_flags=record.quality_flags,
        warnings=record.warnings,
    )
