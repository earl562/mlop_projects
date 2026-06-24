from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from plotlot.harness.agent_run import AgentRunRecord, RunTraceStep
from plotlot.harness.context import ContextEvidencePacket
from plotlot.harness.planner_types import LaneAssignment, PlanEscalation
from plotlot.pipeline.lookup_snapshot_json import JsonValue


class AgentRunAssignmentResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    lane: str
    objective: str
    field_keys: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    calculation_outputs: tuple[str, ...]
    warnings: tuple[str, ...]
    escalation_required: bool


class AgentRunEscalationResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    field_key: str | None
    reason: str
    required_action: str


class AgentRunTraceStepResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    sequence: int
    kind: str
    summary: str
    lane: str | None
    field_keys: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    calculation_outputs: tuple[str, ...]
    warnings: tuple[str, ...]
    escalation_required: bool


class AgentRunEvidencePacketResponse(BaseModel):
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
    confidence: float
    quality_score: float
    quality_flags: tuple[str, ...]
    warnings: tuple[str, ...]


class AgentRunResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    lookup_snapshot_id: str
    workspace_id: str
    project_id: str | None
    site_id: str | None
    objective: str
    status: str
    ready_for_synthesis: bool
    evidence_ids: tuple[str, ...]
    evidence_packets: tuple[AgentRunEvidencePacketResponse, ...] = ()
    warnings: tuple[str, ...]
    open_questions: tuple[str, ...]
    assignments: tuple[AgentRunAssignmentResponse, ...]
    escalations: tuple[AgentRunEscalationResponse, ...]
    trace_steps: tuple[AgentRunTraceStepResponse, ...]


def agent_run_response(record: AgentRunRecord, lookup_snapshot_id: str) -> AgentRunResponse:
    return AgentRunResponse(
        run_id=str(record.run_id),
        lookup_snapshot_id=lookup_snapshot_id,
        workspace_id=record.workspace_id,
        project_id=record.project_id,
        site_id=record.site_id,
        objective=record.objective,
        status=record.status.value,
        ready_for_synthesis=record.plan.ready_for_synthesis,
        evidence_ids=tuple(str(evidence_id) for evidence_id in record.evidence_ids),
        evidence_packets=tuple(
            _evidence_packet_response(item) for item in record.context_packet.evidence_packets
        ),
        warnings=record.warnings,
        open_questions=record.open_questions,
        assignments=tuple(_assignment_response(item) for item in record.plan.assignments),
        escalations=tuple(_escalation_response(item) for item in record.plan.escalations),
        trace_steps=tuple(_trace_step_response(item) for item in record.trace_steps),
    )


def agent_run_evidence_packets_json(response: AgentRunResponse) -> list[JsonValue]:
    return [_evidence_packet_json(packet) for packet in response.evidence_packets]


def _evidence_packet_json(packet: AgentRunEvidencePacketResponse) -> dict[str, JsonValue]:
    return {
        "evidence_id": packet.evidence_id,
        "source_type": packet.source_type,
        "source_authority": packet.source_authority,
        "publisher": packet.publisher,
        "source_title": packet.source_title,
        "source_url": packet.source_url,
        "retrieved_at": packet.retrieved_at,
        "effective_date": packet.effective_date,
        "parser_version": packet.parser_version,
        "schema_version": packet.schema_version,
        "raw_artifact_ref": packet.raw_artifact_ref,
        "query_parameters": list(packet.query_parameters),
        "referenced_field_keys": list(packet.referenced_field_keys),
        "calculation_outputs": list(packet.calculation_outputs),
        "lineage": list(packet.lineage),
        "confidence": packet.confidence,
        "quality_score": packet.quality_score,
        "quality_flags": list(packet.quality_flags),
        "warnings": list(packet.warnings),
    }


def _evidence_packet_response(packet: ContextEvidencePacket) -> AgentRunEvidencePacketResponse:
    return AgentRunEvidencePacketResponse(
        evidence_id=str(packet.evidence_id),
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
        referenced_field_keys=tuple(str(field_key) for field_key in packet.referenced_field_keys),
        calculation_outputs=packet.calculation_outputs,
        lineage=packet.lineage,
        confidence=packet.confidence,
        quality_score=packet.quality_score,
        quality_flags=packet.quality_flags,
        warnings=packet.warnings,
    )


def _assignment_response(assignment: LaneAssignment) -> AgentRunAssignmentResponse:
    return AgentRunAssignmentResponse(
        lane=assignment.lane.value,
        objective=assignment.objective,
        field_keys=tuple(str(field_key) for field_key in assignment.field_keys),
        evidence_ids=tuple(str(evidence_id) for evidence_id in assignment.evidence_ids),
        calculation_outputs=assignment.calculation_outputs,
        warnings=assignment.warnings,
        escalation_required=assignment.escalation_required,
    )


def _escalation_response(escalation: PlanEscalation) -> AgentRunEscalationResponse:
    field_key = None if escalation.field_key is None else str(escalation.field_key)
    return AgentRunEscalationResponse(
        field_key=field_key,
        reason=escalation.reason,
        required_action=escalation.required_action,
    )


def _trace_step_response(step: RunTraceStep) -> AgentRunTraceStepResponse:
    lane = None if step.lane is None else step.lane.value
    return AgentRunTraceStepResponse(
        sequence=step.sequence,
        kind=step.kind.value,
        summary=step.summary,
        lane=lane,
        field_keys=tuple(str(field_key) for field_key in step.field_keys),
        evidence_ids=tuple(str(evidence_id) for evidence_id in step.evidence_ids),
        calculation_outputs=step.calculation_outputs,
        warnings=step.warnings,
        escalation_required=step.escalation_required,
    )
