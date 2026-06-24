from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique

from plotlot.core.lookup_snapshot import EvidenceId, FieldKey, RunId
from plotlot.harness.context import ContextBroker, ContextBuildRequest, ContextPacket
from plotlot.harness.planner import HarnessPlanner
from plotlot.harness.planner_types import HarnessPlan, SpecialistLane


@unique
class AgentRunStatus(StrEnum):
    READY_FOR_SYNTHESIS = "ready_for_synthesis"
    REQUIRES_REVIEW = "requires_review"


@unique
class RunTraceStepKind(StrEnum):
    RUN_STARTED = "run_started"
    CONTEXT_BUILT = "context_built"
    PLAN_CREATED = "plan_created"
    LANE_ASSIGNED = "lane_assigned"
    ESCALATION_RECORDED = "escalation_recorded"
    RUN_COMPLETED = "run_completed"


@dataclass(frozen=True, slots=True)
class AgentRunRequest:
    run_id: RunId
    context_request: ContextBuildRequest


@dataclass(frozen=True, slots=True)
class RunTraceStep:
    sequence: int
    kind: RunTraceStepKind
    summary: str
    lane: SpecialistLane | None = None
    field_keys: tuple[FieldKey, ...] = ()
    evidence_ids: tuple[EvidenceId, ...] = ()
    calculation_outputs: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    escalation_required: bool = False


@dataclass(frozen=True, slots=True)
class AgentRunRecord:
    run_id: RunId
    workspace_id: str
    objective: str
    context_packet: ContextPacket
    plan: HarnessPlan
    status: AgentRunStatus
    trace_steps: tuple[RunTraceStep, ...]
    evidence_ids: tuple[EvidenceId, ...]
    warnings: tuple[str, ...]
    open_questions: tuple[str, ...]
    project_id: str | None = None
    site_id: str | None = None


class AgentRunRuntime:
    def __init__(
        self,
        *,
        context_broker: ContextBroker | None = None,
        planner: HarnessPlanner | None = None,
    ) -> None:
        self._context_broker = context_broker or ContextBroker()
        self._planner = planner or HarnessPlanner()

    def start_run(self, request: AgentRunRequest) -> AgentRunRecord:
        packet = self._context_broker.build_packet(request.context_request)
        plan = self._planner.plan(packet)
        status = AgentRunStatus.READY_FOR_SYNTHESIS
        if not plan.ready_for_synthesis:
            status = AgentRunStatus.REQUIRES_REVIEW

        steps: list[RunTraceStep] = [
            RunTraceStep(
                sequence=1,
                kind=RunTraceStepKind.RUN_STARTED,
                summary=packet.objective,
                evidence_ids=packet.evidence_ids,
            ),
            RunTraceStep(
                sequence=2,
                kind=RunTraceStepKind.CONTEXT_BUILT,
                summary="Context packet built from recorded lookup evidence.",
                field_keys=tuple(field.key for field in packet.fields),
                evidence_ids=packet.evidence_ids,
                warnings=packet.warnings,
            ),
            RunTraceStep(
                sequence=3,
                kind=RunTraceStepKind.PLAN_CREATED,
                summary="Specialist lane plan created before synthesis.",
                evidence_ids=plan.evidence_ids,
                calculation_outputs=tuple(
                    output
                    for assignment in plan.assignments
                    for output in assignment.calculation_outputs
                ),
                escalation_required=bool(plan.escalations),
            ),
        ]

        for assignment in plan.assignments:
            steps.append(
                RunTraceStep(
                    sequence=len(steps) + 1,
                    kind=RunTraceStepKind.LANE_ASSIGNED,
                    summary=assignment.objective,
                    lane=assignment.lane,
                    field_keys=assignment.field_keys,
                    evidence_ids=assignment.evidence_ids,
                    calculation_outputs=assignment.calculation_outputs,
                    warnings=assignment.warnings,
                    escalation_required=assignment.escalation_required,
                )
            )

        for escalation in plan.escalations:
            field_keys = () if escalation.field_key is None else (escalation.field_key,)
            steps.append(
                RunTraceStep(
                    sequence=len(steps) + 1,
                    kind=RunTraceStepKind.ESCALATION_RECORDED,
                    summary=f"{escalation.reason} {escalation.required_action}",
                    field_keys=field_keys,
                    escalation_required=True,
                )
            )

        steps.append(
            RunTraceStep(
                sequence=len(steps) + 1,
                kind=RunTraceStepKind.RUN_COMPLETED,
                summary=status.value,
                evidence_ids=plan.evidence_ids,
                warnings=packet.warnings,
                escalation_required=status is AgentRunStatus.REQUIRES_REVIEW,
            )
        )

        return AgentRunRecord(
            run_id=request.run_id,
            workspace_id=packet.workspace_id,
            project_id=packet.project_id,
            site_id=packet.site_id,
            objective=packet.objective,
            context_packet=packet,
            plan=plan,
            status=status,
            trace_steps=tuple(steps),
            evidence_ids=plan.evidence_ids,
            warnings=packet.warnings,
            open_questions=packet.open_questions,
        )
