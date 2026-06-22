from __future__ import annotations

from typing import assert_never

from plotlot.core.lookup_snapshot import DisplayState, EvidenceId, FieldKey
from plotlot.harness.context import ContextFieldPacket, ContextPacket
from plotlot.harness.planner_support import (
    global_evidence_lanes,
    unique_escalations,
    unique_evidence,
)
from plotlot.harness.planner_types import LaneAssignment, PlanEscalation, SpecialistLane


def build_assignments(
    packet: ContextPacket,
    escalations: tuple[PlanEscalation, ...],
) -> tuple[LaneAssignment, ...]:
    outputs = tuple(calculation.output_label for calculation in packet.calculations)
    return tuple(_assignment(packet, lane, escalations, outputs) for lane in SpecialistLane)


def build_escalations(packet: ContextPacket) -> tuple[PlanEscalation, ...]:
    field_escalations = tuple(
        escalation
        for field in packet.fields
        for escalation in (_field_escalation(field),)
        if escalation is not None
    )
    calculation_escalations = tuple(
        PlanEscalation(
            field_key=None,
            reason=f"{calculation.calculator_name} is not reproducible",
            required_action="Capture input evidence IDs before using the calculation.",
        )
        for calculation in packet.calculations
        if not calculation.is_reproducible
    )
    packet_escalations = _packet_question_escalations(packet)
    return unique_escalations((*field_escalations, *calculation_escalations, *packet_escalations))


def _assignment(
    packet: ContextPacket,
    lane: SpecialistLane,
    escalations: tuple[PlanEscalation, ...],
    calculation_outputs: tuple[str, ...],
) -> LaneAssignment:
    match lane:
        case SpecialistLane.PARCEL_ANALYST:
            return _lane_assignment(
                packet,
                lane,
                "Verify parcel identity, APN, address, and lot area from parcel evidence.",
                _field_keys_with_prefix(packet, ("parcel.",)),
                (),
                False,
            )
        case SpecialistLane.ZONING_CODE_ANALYST:
            field_keys = _field_keys_with_prefix(
                packet, ("zoning.", "uses.", "standards.", "jurisdiction.")
            )
            return _lane_assignment(
                packet,
                lane,
                "Verify zoning district, allowed uses, dimensional standards, and jurisdiction.",
                field_keys,
                (),
                _has_escalation_for_fields(escalations, field_keys),
            )
        case SpecialistLane.GIS_LAYER_ANALYST:
            field_keys = _field_keys_for_names(
                packet,
                (
                    FieldKey("parcel.lot_area_sqft"),
                    FieldKey("jurisdiction.municipality"),
                    FieldKey("jurisdiction.county"),
                    FieldKey("zoning.district"),
                ),
            )
            return _lane_assignment(
                packet,
                lane,
                "Check parcel geometry, jurisdiction, zoning map, and layer-derived facts.",
                field_keys,
                (),
                _has_escalation_for_fields(escalations, field_keys),
            )
        case SpecialistLane.ENTITLEMENT_RISK_ANALYST:
            return _lane_assignment(
                packet,
                lane,
                "Surface entitlement, contradiction, freshness, and missing-evidence risks.",
                _unresolved_field_keys(packet),
                (),
                bool(escalations),
            )
        case SpecialistLane.UNDERWRITING_ANALYST:
            return _lane_assignment(
                packet,
                lane,
                "Review deterministic development-capacity calculations before value synthesis.",
                _field_keys_with_prefix(packet, ("calc.",)),
                calculation_outputs,
                _has_calculation_escalation(packet),
            )
        case (
            SpecialistLane.EVIDENCE_REVIEWER
            | SpecialistLane.REPORT_DOCUMENT_ANALYST
            | SpecialistLane.LEAD_DEVELOPER_CONSULTANT
        ):
            return _global_assignment(packet, lane, calculation_outputs, bool(escalations))
        case unreachable:
            assert_never(unreachable)


def _global_assignment(
    packet: ContextPacket,
    lane: SpecialistLane,
    calculation_outputs: tuple[str, ...],
    escalation_required: bool,
) -> LaneAssignment:
    match lane:
        case SpecialistLane.EVIDENCE_REVIEWER:
            objective = "Confirm each specialist output is backed by evidence IDs or calculations."
        case SpecialistLane.REPORT_DOCUMENT_ANALYST:
            objective = (
                "Prepare report-ready claims only from evidence IDs and labeled assumptions."
            )
        case SpecialistLane.LEAD_DEVELOPER_CONSULTANT:
            objective = (
                "Synthesize opportunity and risk only after unresolved evidence is escalated."
            )
        case (
            SpecialistLane.PARCEL_ANALYST
            | SpecialistLane.ZONING_CODE_ANALYST
            | SpecialistLane.GIS_LAYER_ANALYST
            | SpecialistLane.ENTITLEMENT_RISK_ANALYST
            | SpecialistLane.UNDERWRITING_ANALYST
        ):
            objective = ""
        case unreachable:
            assert_never(unreachable)
    return _lane_assignment(
        packet,
        lane,
        objective,
        tuple(field.key for field in packet.fields),
        calculation_outputs,
        escalation_required,
    )


def _lane_assignment(
    packet: ContextPacket,
    lane: SpecialistLane,
    objective: str,
    field_keys: tuple[FieldKey, ...],
    calculation_outputs: tuple[str, ...],
    escalation_required: bool,
) -> LaneAssignment:
    evidence_ids = _evidence_ids_for_fields(packet, field_keys)
    if not evidence_ids and lane in global_evidence_lanes():
        evidence_ids = packet.evidence_ids
    return LaneAssignment(
        lane=lane,
        objective=objective,
        field_keys=field_keys,
        evidence_ids=evidence_ids,
        calculation_outputs=calculation_outputs,
        warnings=packet.warnings,
        escalation_required=escalation_required,
    )


def _field_escalation(field: ContextFieldPacket) -> PlanEscalation | None:
    match field.display_state:
        case DisplayState.VERIFIED:
            return None
        case DisplayState.ASSUMED:
            action = "Keep assumption labeled and excluded from verified lookup facts."
        case DisplayState.STALE:
            action = "Refresh authoritative source evidence before relying on this field."
        case DisplayState.CONTRADICTED:
            action = "Surface contradictory evidence for human review before use."
        case DisplayState.UNKNOWN:
            action = "Retrieve authoritative evidence or keep the field unknown."
        case DisplayState.REQUIRES_HUMAN_REVIEW:
            action = "Route the field to human review before use."
        case unreachable:
            assert_never(unreachable)
    return PlanEscalation(
        field_key=field.key,
        reason=f"{field.key} is {field.display_state.value}",
        required_action=action,
    )


def _packet_question_escalations(packet: ContextPacket) -> tuple[PlanEscalation, ...]:
    return tuple(
        PlanEscalation(
            field_key=None,
            reason=question,
            required_action="Resolve open context question before final synthesis.",
        )
        for question in packet.open_questions
        if question and not _is_field_question(packet, question)
    )


def _is_field_question(packet: ContextPacket, question: str) -> bool:
    return any(question.startswith(f"{field.key} ") for field in packet.fields)


def _field_keys_with_prefix(
    packet: ContextPacket,
    prefixes: tuple[str, ...],
) -> tuple[FieldKey, ...]:
    return tuple(
        field.key
        for field in packet.fields
        if any(str(field.key).startswith(prefix) for prefix in prefixes)
    )


def _field_keys_for_names(
    packet: ContextPacket,
    names: tuple[FieldKey, ...],
) -> tuple[FieldKey, ...]:
    return tuple(field.key for field in packet.fields if field.key in names)


def _unresolved_field_keys(packet: ContextPacket) -> tuple[FieldKey, ...]:
    return tuple(
        field.key for field in packet.fields if field.display_state is not DisplayState.VERIFIED
    )


def _evidence_ids_for_fields(
    packet: ContextPacket,
    field_keys: tuple[FieldKey, ...],
) -> tuple[EvidenceId, ...]:
    return unique_evidence(
        tuple(
            evidence_id
            for field in packet.fields
            if field.key in field_keys
            for evidence_id in field.evidence_ids
        )
    )


def _has_escalation_for_fields(
    escalations: tuple[PlanEscalation, ...],
    field_keys: tuple[FieldKey, ...],
) -> bool:
    return any(escalation.field_key in field_keys for escalation in escalations)


def _has_calculation_escalation(packet: ContextPacket) -> bool:
    return any(not calculation.is_reproducible for calculation in packet.calculations)
