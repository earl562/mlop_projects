from __future__ import annotations

from plotlot.core.lookup_snapshot import EvidenceId
from plotlot.harness.planner_types import PlanEscalation, SpecialistLane


def global_evidence_lanes() -> tuple[SpecialistLane, ...]:
    return (
        SpecialistLane.ENTITLEMENT_RISK_ANALYST,
        SpecialistLane.EVIDENCE_REVIEWER,
        SpecialistLane.REPORT_DOCUMENT_ANALYST,
        SpecialistLane.LEAD_DEVELOPER_CONSULTANT,
    )


def unique_evidence(evidence_ids: tuple[EvidenceId, ...]) -> tuple[EvidenceId, ...]:
    seen: set[str] = set()
    unique: list[EvidenceId] = []
    for evidence_id in evidence_ids:
        value = str(evidence_id)
        if value in seen:
            continue
        seen.add(value)
        unique.append(evidence_id)
    return tuple(unique)


def unique_escalations(
    escalations: tuple[PlanEscalation, ...],
) -> tuple[PlanEscalation, ...]:
    seen: set[tuple[str, str]] = set()
    unique: list[PlanEscalation] = []
    for escalation in escalations:
        key = (str(escalation.field_key), escalation.reason)
        if key in seen:
            continue
        seen.add(key)
        unique.append(escalation)
    return tuple(unique)
