from __future__ import annotations

from pydantic import BaseModel, Field


class LookupFieldResponse(BaseModel):
    key: str
    label: str
    value: str | int | float | bool | None = None
    unit: str = ""
    display_state: str
    evidence_ids: list[str] = Field(default_factory=list)
    source_priority: list[str] = Field(default_factory=list)
    fallback_sources: list[str] = Field(default_factory=list)
    failure_behavior: str
    confidence: float
    freshness: str
    warnings: list[str] = Field(default_factory=list)


class CalculationTraceResponse(BaseModel):
    calculator_name: str
    calculator_version: str
    formula: str
    input_evidence_ids: list[str] = Field(default_factory=list)
    output_label: str
    warnings: list[str] = Field(default_factory=list)


class EvidenceSourceMetadataResponse(BaseModel):
    evidence_id: str
    source_url: str = ""
    source_title: str = ""
    source_type: str = ""
    source_authority: str = ""
    publisher: str = ""
    retrieved_at: str = ""
    effective_date: str = ""
    parser_version: str = ""
    schema_version: str = ""
    raw_artifact_ref: str = ""
    query_parameters: list[str] = Field(default_factory=list)


class LookupSnapshotResponse(BaseModel):
    lookup_snapshot_id: str
    site_id: str
    run_id: str
    fields: list[LookupFieldResponse] = Field(default_factory=list)
    calculations: list[CalculationTraceResponse] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_metadata: list[EvidenceSourceMetadataResponse] = Field(default_factory=list)
