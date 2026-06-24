from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from plotlot.harness.agent_run_responses import AgentRunEvidencePacketResponse


class AgentRunSourceRetrievalTraceResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    evidence_id: str
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
    referenced_field_keys: tuple[str, ...]
    calculation_outputs: tuple[str, ...]
    lineage: tuple[str, ...]
    quality_score: float
    quality_flags: tuple[str, ...]
    warnings: tuple[str, ...]


def source_retrieval_trace(
    packet: AgentRunEvidencePacketResponse,
) -> AgentRunSourceRetrievalTraceResponse:
    return AgentRunSourceRetrievalTraceResponse(
        evidence_id=packet.evidence_id,
        source_type=packet.source_type,
        source_authority=packet.source_authority,
        publisher=packet.publisher,
        source_title=packet.source_title,
        source_url=packet.source_url,
        retrieved_at=packet.retrieved_at,
        effective_date=packet.effective_date,
        parser_version=packet.parser_version,
        schema_version=packet.schema_version,
        raw_artifact_ref=packet.raw_artifact_ref,
        query_parameters=packet.query_parameters,
        referenced_field_keys=packet.referenced_field_keys,
        calculation_outputs=packet.calculation_outputs,
        lineage=packet.lineage,
        quality_score=packet.quality_score,
        quality_flags=packet.quality_flags,
        warnings=packet.warnings,
    )
