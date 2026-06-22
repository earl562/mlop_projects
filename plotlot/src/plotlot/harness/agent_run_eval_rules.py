from __future__ import annotations

from math import isfinite
from typing import Final

from plotlot.harness.agent_run_responses import (
    AgentRunEvidencePacketResponse,
    AgentRunResponse,
)

REQUIRED_SPECIALIST_LANES: Final = (
    "parcel_analyst",
    "zoning_code_analyst",
    "gis_layer_analyst",
    "entitlement_risk_analyst",
    "underwriting_analyst",
    "evidence_reviewer",
    "report_document_analyst",
    "lead_developer_consultant",
)


def evidence_coverage(response: AgentRunResponse) -> float:
    if not response.evidence_ids:
        return 0.0
    return ratio(
        sum(1 for assignment in response.assignments if assignment.evidence_ids),
        len(response.assignments),
    )


def missing_required_lanes(response: AgentRunResponse) -> tuple[str, ...]:
    actual = {assignment.lane for assignment in response.assignments}
    return tuple(lane for lane in REQUIRED_SPECIALIST_LANES if lane not in actual)


def missing_evidence_packet_ids(response: AgentRunResponse) -> tuple[str, ...]:
    packet_ids = {packet.evidence_id for packet in response.evidence_packets}
    return tuple(
        evidence_id for evidence_id in response.evidence_ids if evidence_id not in packet_ids
    )


def incomplete_evidence_packet_ids(response: AgentRunResponse) -> tuple[str, ...]:
    evidence_ids = set(response.evidence_ids)
    return tuple(
        packet.evidence_id
        for packet in response.evidence_packets
        if packet.evidence_id in evidence_ids and not evidence_packet_is_traceable(packet)
    )


def evidence_packet_is_traceable(packet: AgentRunEvidencePacketResponse) -> bool:
    if not (
        packet.source_type
        and packet.source_authority
        and packet.retrieved_at
        and packet.parser_version
        and packet.schema_version
        and packet.raw_artifact_ref
        and packet.lineage
    ):
        return False
    if not (score_is_bounded(packet.confidence) and score_is_bounded(packet.quality_score)):
        return False
    if not packet.source_url and "missing_source_url" not in packet.quality_flags:
        return False
    return bool(packet.effective_date or "missing_effective_date" in packet.quality_flags)


def source_quality_traceability(
    response: AgentRunResponse,
    missing_packet_ids: tuple[str, ...],
    incomplete_packet_ids: tuple[str, ...],
) -> float:
    if not response.evidence_ids:
        return 0.0
    untraceable_ids = {*missing_packet_ids, *incomplete_packet_ids}
    return ratio(len(response.evidence_ids) - len(untraceable_ids), len(response.evidence_ids))


def missing_calculation_outputs(response: AgentRunResponse) -> tuple[str, ...]:
    linked_outputs = packet_calculation_outputs(response)
    return tuple(
        output for output in required_calculation_outputs(response) if output not in linked_outputs
    )


def required_calculation_outputs(response: AgentRunResponse) -> tuple[str, ...]:
    return unique_strings(
        (
            *(
                output
                for assignment in response.assignments
                for output in assignment.calculation_outputs
            ),
            *(output for step in response.trace_steps for output in step.calculation_outputs),
        )
    )


def packet_calculation_outputs(response: AgentRunResponse) -> set[str]:
    outputs: set[str] = set()
    for packet in response.evidence_packets:
        lineage_outputs = {
            lineage.removeprefix("source -> normalized evidence -> calculation output:")
            for lineage in packet.lineage
            if lineage.startswith("source -> normalized evidence -> calculation output:")
        }
        outputs.update(output for output in packet.calculation_outputs if output in lineage_outputs)
    return outputs


def calculation_lineage_traceability(
    response: AgentRunResponse,
    missing_outputs: tuple[str, ...],
) -> float:
    calculation_outputs = required_calculation_outputs(response)
    if not calculation_outputs:
        return 1.0
    return ratio(
        len(calculation_outputs) - len(missing_outputs),
        len(calculation_outputs),
    )


def missing_trace_requirements(response: AgentRunResponse) -> tuple[str, ...]:
    missing: list[str] = []
    if not response.trace_steps:
        return ("trace_steps",)
    if response.trace_steps[0].kind != "run_started":
        missing.append("trace_starts_with_run_started")
    if response.trace_steps[-1].kind != "run_completed":
        missing.append("trace_ends_with_run_completed")
    expected_sequence = tuple(range(1, len(response.trace_steps) + 1))
    observed_sequence = tuple(step.sequence for step in response.trace_steps)
    if observed_sequence != expected_sequence:
        missing.append("trace_sequence_contiguous")
    traced_evidence_ids = {
        evidence_id for step in response.trace_steps for evidence_id in step.evidence_ids
    }
    if not set(response.evidence_ids).issubset(traced_evidence_ids):
        missing.append("trace_covers_run_evidence")
    traced_warnings = {warning for step in response.trace_steps for warning in step.warnings}
    if not set(response.warnings).issubset(traced_warnings):
        missing.append("trace_covers_run_warnings")
    if response.escalations and not any(step.escalation_required for step in response.trace_steps):
        missing.append("trace_covers_run_escalations")
    return tuple(missing)


def escalation_visibility(response: AgentRunResponse) -> float:
    if response.ready_for_synthesis:
        return 1.0
    if response.escalations or response.open_questions or response.warnings:
        return 1.0
    return 0.0


def ready_for_synthesis_gate(response: AgentRunResponse) -> float:
    blockers = bool(response.escalations or response.open_questions)
    if response.ready_for_synthesis == (not blockers):
        return 1.0
    return 0.0


def ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def score_is_bounded(value: float) -> bool:
    return isfinite(value) and 0 <= value <= 1


def unique_strings(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))
