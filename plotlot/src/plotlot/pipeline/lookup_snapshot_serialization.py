from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict

from plotlot.core.lookup_snapshot import (
    CalculationTrace,
    DisplayState,
    EvidenceSourceMetadata,
    EvidenceId,
    FailureBehavior,
    FieldKey,
    FieldScalar,
    FreshnessStatus,
    LookupField,
    LookupSnapshot,
    LookupSnapshotId,
    RunId,
    SiteId,
)
from plotlot.pipeline.lookup_snapshot_json import JsonValue


class _LookupFieldPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    label: str
    value: FieldScalar
    unit: str
    display_state: DisplayState
    evidence_ids: tuple[str, ...]
    source_priority: tuple[str, ...]
    fallback_sources: tuple[str, ...]
    failure_behavior: FailureBehavior
    confidence: float
    freshness: FreshnessStatus
    warnings: tuple[str, ...]


class _CalculationPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    calculator_name: str
    calculator_version: str
    formula: str
    input_evidence_ids: tuple[str, ...]
    output_label: str
    warnings: tuple[str, ...]


class _EvidenceSourceMetadataPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    evidence_id: str
    source_url: str
    source_title: str
    source_type: str = ""
    source_authority: str = ""
    publisher: str = ""
    retrieved_at: str = ""
    effective_date: str = ""
    parser_version: str = ""
    schema_version: str = ""
    raw_artifact_ref: str = ""
    query_parameters: tuple[str, ...] = ()


class _LookupSnapshotPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    lookup_snapshot_id: str
    site_id: str
    run_id: str
    fields: tuple[_LookupFieldPayload, ...]
    calculations: tuple[_CalculationPayload, ...]
    warnings: tuple[str, ...]
    source_metadata: tuple[_EvidenceSourceMetadataPayload, ...] = ()


def lookup_snapshot_to_dict(snapshot: LookupSnapshot) -> dict[str, JsonValue]:
    fields: list[JsonValue] = []
    for field in snapshot.fields:
        fields.append(_field_to_dict(field))

    calculations: list[JsonValue] = []
    for calculation in snapshot.calculations:
        calculations.append(_calculation_to_dict(calculation))

    source_metadata: list[JsonValue] = []
    for metadata in snapshot.source_metadata:
        source_metadata.append(_source_metadata_to_dict(metadata))

    return {
        "lookup_snapshot_id": str(snapshot.lookup_snapshot_id),
        "site_id": str(snapshot.site_id),
        "run_id": str(snapshot.run_id),
        "fields": fields,
        "calculations": calculations,
        "warnings": _json_string_list(snapshot.warnings),
        "source_metadata": source_metadata,
    }


def lookup_snapshot_from_dict(payload: dict[str, JsonValue]) -> LookupSnapshot:
    parsed = _LookupSnapshotPayload.model_validate(payload)
    return LookupSnapshot(
        lookup_snapshot_id=LookupSnapshotId(parsed.lookup_snapshot_id),
        site_id=SiteId(parsed.site_id),
        run_id=RunId(parsed.run_id),
        fields=tuple(_field_from_payload(field) for field in parsed.fields),
        calculations=tuple(
            _calculation_from_payload(calculation) for calculation in parsed.calculations
        ),
        warnings=parsed.warnings,
        source_metadata=tuple(
            _source_metadata_from_payload(metadata) for metadata in parsed.source_metadata
        ),
    )


def _field_to_dict(field: LookupField) -> dict[str, JsonValue]:
    return {
        "key": str(field.key),
        "label": field.label,
        "value": field.value,
        "unit": field.unit,
        "display_state": field.display_state.value,
        "evidence_ids": _json_string_list(field.evidence_ids),
        "source_priority": _json_string_list(field.source_priority),
        "fallback_sources": _json_string_list(field.fallback_sources),
        "failure_behavior": field.failure_behavior.value,
        "confidence": field.confidence,
        "freshness": field.freshness.value,
        "warnings": _json_string_list(field.warnings),
    }


def _field_from_payload(payload: _LookupFieldPayload) -> LookupField:
    return LookupField(
        key=FieldKey(payload.key),
        label=payload.label,
        value=payload.value,
        unit=payload.unit,
        display_state=payload.display_state,
        evidence_ids=tuple(EvidenceId(evidence_id) for evidence_id in payload.evidence_ids),
        source_priority=payload.source_priority,
        fallback_sources=payload.fallback_sources,
        failure_behavior=payload.failure_behavior,
        confidence=payload.confidence,
        freshness=payload.freshness,
        warnings=payload.warnings,
    )


def _calculation_to_dict(calculation: CalculationTrace) -> dict[str, JsonValue]:
    return {
        "calculator_name": calculation.calculator_name,
        "calculator_version": calculation.calculator_version,
        "formula": calculation.formula,
        "input_evidence_ids": _json_string_list(calculation.input_evidence_ids),
        "output_label": calculation.output_label,
        "warnings": _json_string_list(calculation.warnings),
    }


def _calculation_from_payload(payload: _CalculationPayload) -> CalculationTrace:
    return CalculationTrace(
        calculator_name=payload.calculator_name,
        calculator_version=payload.calculator_version,
        formula=payload.formula,
        input_evidence_ids=tuple(
            EvidenceId(evidence_id) for evidence_id in payload.input_evidence_ids
        ),
        output_label=payload.output_label,
        warnings=payload.warnings,
    )


def _source_metadata_to_dict(metadata: EvidenceSourceMetadata) -> dict[str, JsonValue]:
    return {
        "evidence_id": str(metadata.evidence_id),
        "source_url": metadata.source_url,
        "source_title": metadata.source_title,
        "source_type": metadata.source_type,
        "source_authority": metadata.source_authority,
        "publisher": metadata.publisher,
        "retrieved_at": metadata.retrieved_at,
        "effective_date": metadata.effective_date,
        "parser_version": metadata.parser_version,
        "schema_version": metadata.schema_version,
        "raw_artifact_ref": metadata.raw_artifact_ref,
        "query_parameters": _json_string_list(metadata.query_parameters),
    }


def _source_metadata_from_payload(
    payload: _EvidenceSourceMetadataPayload,
) -> EvidenceSourceMetadata:
    return EvidenceSourceMetadata(
        evidence_id=EvidenceId(payload.evidence_id),
        source_url=payload.source_url,
        source_title=payload.source_title,
        source_type=payload.source_type,
        source_authority=payload.source_authority,
        publisher=payload.publisher,
        retrieved_at=payload.retrieved_at,
        effective_date=payload.effective_date,
        parser_version=payload.parser_version,
        schema_version=payload.schema_version,
        raw_artifact_ref=payload.raw_artifact_ref,
        query_parameters=payload.query_parameters,
    )


def _json_string_list(values: Iterable[str]) -> list[JsonValue]:
    items: list[JsonValue] = []
    for value in values:
        items.append(str(value))
    return items
