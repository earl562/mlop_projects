from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique

from plotlot.core.lookup_snapshot import EvidenceId, FieldKey


@unique
class SpecialistLane(StrEnum):
    PARCEL_ANALYST = "parcel_analyst"
    ZONING_CODE_ANALYST = "zoning_code_analyst"
    GIS_LAYER_ANALYST = "gis_layer_analyst"
    ENTITLEMENT_RISK_ANALYST = "entitlement_risk_analyst"
    UNDERWRITING_ANALYST = "underwriting_analyst"
    EVIDENCE_REVIEWER = "evidence_reviewer"
    REPORT_DOCUMENT_ANALYST = "report_document_analyst"
    LEAD_DEVELOPER_CONSULTANT = "lead_developer_consultant"


@dataclass(frozen=True, slots=True)
class PlanEscalation:
    field_key: FieldKey | None
    reason: str
    required_action: str


@dataclass(frozen=True, slots=True)
class LaneAssignment:
    lane: SpecialistLane
    objective: str
    field_keys: tuple[FieldKey, ...]
    evidence_ids: tuple[EvidenceId, ...]
    calculation_outputs: tuple[str, ...]
    warnings: tuple[str, ...]
    escalation_required: bool


@dataclass(frozen=True, slots=True)
class MissingLaneAssignmentError(Exception):
    lane: SpecialistLane

    def __str__(self) -> str:
        return f"missing planner lane assignment: {self.lane.value}"


@dataclass(frozen=True, slots=True)
class HarnessPlan:
    objective: str
    evidence_ids: tuple[EvidenceId, ...]
    assignments: tuple[LaneAssignment, ...]
    escalations: tuple[PlanEscalation, ...]
    ready_for_synthesis: bool

    def assignment_for(self, lane: SpecialistLane) -> LaneAssignment:
        for assignment in self.assignments:
            if assignment.lane is lane:
                return assignment
        raise MissingLaneAssignmentError(lane)
