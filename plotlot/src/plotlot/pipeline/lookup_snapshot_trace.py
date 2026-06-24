from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from plotlot.core.lookup_snapshot import (
    EvidenceId,
    FieldKey,
    FieldScalar,
    LookupSnapshot,
    LookupSnapshotId,
)
from plotlot.pipeline.lookup_snapshot_json import JsonValue


@dataclass(frozen=True, slots=True)
class TraceFieldEvidence:
    field_key: FieldKey
    value: FieldScalar
    display_state: str
    evidence_ids: tuple[EvidenceId, ...]
    confidence: float
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TraceCalculation:
    calculator_name: str
    calculator_version: str
    formula: str
    input_evidence_ids: tuple[EvidenceId, ...]
    output_label: str
    warnings: tuple[str, ...]
    is_reproducible: bool


@dataclass(frozen=True, slots=True)
class TraceSourceRetrieval:
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
    lineage: tuple[str, ...]
    quality_score: float
    quality_flags: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LookupSnapshotTraceRecord:
    lookup_snapshot_id: LookupSnapshotId
    run_id: str
    plan: str
    tool_calls: tuple[str, ...]
    source_retrievals: tuple[TraceSourceRetrieval, ...]
    evidence_ids: tuple[EvidenceId, ...]
    ingestion_quality_flags: tuple[str, ...]
    field_count: int
    field_evidence: tuple[TraceFieldEvidence, ...]
    calculator_outputs: tuple[str, ...]
    calculation_traces: tuple[TraceCalculation, ...]
    warnings: tuple[str, ...]


def build_trace_record(
    snapshot: LookupSnapshot,
    ingestion_quality_flags: tuple[str, ...],
    source_retrievals: tuple[TraceSourceRetrieval, ...],
) -> LookupSnapshotTraceRecord:
    evidence_ids = snapshot_evidence_ids(snapshot)
    calculations = _trace_calculations(snapshot)
    return LookupSnapshotTraceRecord(
        lookup_snapshot_id=snapshot.lookup_snapshot_id,
        run_id=str(snapshot.run_id),
        plan="resolve parcel and zoning facts before calculating display-ready fields",
        tool_calls=("lookup_address", "build_lookup_snapshot"),
        source_retrievals=source_retrievals,
        evidence_ids=evidence_ids,
        ingestion_quality_flags=ingestion_quality_flags,
        field_count=len(snapshot.fields),
        field_evidence=_trace_field_evidence(snapshot),
        calculator_outputs=tuple(trace.output_label for trace in calculations),
        calculation_traces=calculations,
        warnings=snapshot.warnings,
    )


def snapshot_evidence_ids(snapshot: LookupSnapshot) -> tuple[EvidenceId, ...]:
    seen: set[str] = set()
    evidence_ids: list[EvidenceId] = []
    for field in snapshot.fields:
        for evidence_id in field.evidence_ids:
            value = str(evidence_id)
            if value in seen:
                continue
            seen.add(value)
            evidence_ids.append(evidence_id)
    for calculation in snapshot.calculations:
        for evidence_id in calculation.input_evidence_ids:
            value = str(evidence_id)
            if value in seen:
                continue
            seen.add(value)
            evidence_ids.append(evidence_id)
    return tuple(evidence_ids)


def trace_record_to_dict(record: LookupSnapshotTraceRecord) -> dict[str, JsonValue]:
    return {
        "lookup_snapshot_id": str(record.lookup_snapshot_id),
        "run_id": record.run_id,
        "plan": record.plan,
        "tool_calls": _string_list(record.tool_calls),
        "source_retrievals": [_source_retrieval_to_dict(item) for item in record.source_retrievals],
        "evidence_ids": _string_list(record.evidence_ids),
        "ingestion_quality_flags": _string_list(record.ingestion_quality_flags),
        "field_count": record.field_count,
        "field_evidence": [_field_evidence_to_dict(item) for item in record.field_evidence],
        "calculator_outputs": _string_list(record.calculator_outputs),
        "calculation_traces": [
            _calculation_trace_to_dict(item) for item in record.calculation_traces
        ],
        "warnings": _string_list(record.warnings),
    }


def _trace_field_evidence(snapshot: LookupSnapshot) -> tuple[TraceFieldEvidence, ...]:
    return tuple(
        TraceFieldEvidence(
            field_key=field.key,
            value=field.value,
            display_state=field.display_state.value,
            evidence_ids=field.evidence_ids,
            confidence=field.confidence,
            warnings=field.warnings,
        )
        for field in snapshot.fields
    )


def _trace_calculations(snapshot: LookupSnapshot) -> tuple[TraceCalculation, ...]:
    return tuple(
        TraceCalculation(
            calculator_name=calculation.calculator_name,
            calculator_version=calculation.calculator_version,
            formula=calculation.formula,
            input_evidence_ids=calculation.input_evidence_ids,
            output_label=calculation.output_label,
            warnings=calculation.warnings,
            is_reproducible=calculation.is_reproducible,
        )
        for calculation in snapshot.calculations
    )


def _field_evidence_to_dict(field: TraceFieldEvidence) -> dict[str, JsonValue]:
    return {
        "field_key": str(field.field_key),
        "value": field.value,
        "display_state": field.display_state,
        "evidence_ids": _string_list(field.evidence_ids),
        "confidence": field.confidence,
        "warnings": _string_list(field.warnings),
    }


def _calculation_trace_to_dict(calculation: TraceCalculation) -> dict[str, JsonValue]:
    return {
        "calculator_name": calculation.calculator_name,
        "calculator_version": calculation.calculator_version,
        "formula": calculation.formula,
        "input_evidence_ids": _string_list(calculation.input_evidence_ids),
        "output_label": calculation.output_label,
        "warnings": _string_list(calculation.warnings),
        "is_reproducible": calculation.is_reproducible,
    }


def _source_retrieval_to_dict(retrieval: TraceSourceRetrieval) -> dict[str, JsonValue]:
    return {
        "evidence_id": str(retrieval.evidence_id),
        "source_type": retrieval.source_type,
        "source_authority": retrieval.source_authority,
        "publisher": retrieval.publisher,
        "source_url": retrieval.source_url,
        "source_title": retrieval.source_title,
        "retrieved_at": retrieval.retrieved_at,
        "effective_date": retrieval.effective_date,
        "parser_version": retrieval.parser_version,
        "schema_version": retrieval.schema_version,
        "raw_artifact_ref": retrieval.raw_artifact_ref,
        "query_parameters": _string_list(retrieval.query_parameters),
        "lineage": _string_list(retrieval.lineage),
        "quality_score": retrieval.quality_score,
        "quality_flags": _string_list(retrieval.quality_flags),
        "warnings": _string_list(retrieval.warnings),
    }


def _string_list(values: Iterable[str]) -> list[JsonValue]:
    return [str(value) for value in values]
