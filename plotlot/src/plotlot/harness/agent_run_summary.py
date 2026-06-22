from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from plotlot.harness.agent_run_responses import (
    AgentRunAssignmentResponse,
    AgentRunEscalationResponse,
    AgentRunResponse,
    agent_run_response,
)
from plotlot.harness.agent_run_opportunities import AgentRunOpportunityHypothesis
from plotlot.harness.agent_run_store import StoredAgentRun
from plotlot.land_use.models import EvidenceBackedReportSection, ReportClaim
from plotlot.pipeline.lookup_snapshot_json import JsonValue


class AgentRunSummaryArtifact(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    run_id: str
    lookup_snapshot_id: str
    evidence_ids: tuple[str, ...]
    report_json: dict[str, JsonValue]
    report_id: str | None = None
    document_id: str | None = None
    message: str | None = None


def build_agent_run_summary_artifact(stored: StoredAgentRun) -> AgentRunSummaryArtifact:
    return build_agent_run_summary_from_response(
        agent_run_response(stored.record, stored.lookup_snapshot_id)
    )


def build_agent_run_summary_from_response(
    response: AgentRunResponse,
    report_id: str | None = None,
    document_id: str | None = None,
) -> AgentRunSummaryArtifact:
    evidence_ids = response.evidence_ids
    if not evidence_ids:
        return AgentRunSummaryArtifact(
            status="blocked",
            run_id=response.run_id,
            lookup_snapshot_id=response.lookup_snapshot_id,
            evidence_ids=(),
            report_json={},
            report_id=report_id,
            document_id=document_id,
            message="Agent run summary requires recorded evidence IDs.",
        )

    report_json: dict[str, JsonValue] = {
        "title": f"Agent run summary: {response.run_id}",
        "generated_by": "agent_run_summary",
        "run_id": response.run_id,
        "lookup_snapshot_id": response.lookup_snapshot_id,
        "workspace_id": response.workspace_id,
        "project_id": response.project_id,
        "site_id": response.site_id,
        "objective": response.objective,
        "status": response.status,
        "ready_for_synthesis": response.ready_for_synthesis,
        "evidence_ids": list(evidence_ids),
        "sections": [
            section.model_dump(mode="json") for section in _sections(response, evidence_ids)
        ],
        "opportunities": [
            opportunity.model_dump(mode="json") for opportunity in _opportunities(response)
        ],
        "specialist_lanes": _specialist_lanes(response),
        "assumptions": _assumptions(response),
        "review_items": _review_items(response),
        "warnings": list(response.warnings),
    }
    return AgentRunSummaryArtifact(
        status="draft",
        run_id=response.run_id,
        lookup_snapshot_id=response.lookup_snapshot_id,
        evidence_ids=evidence_ids,
        report_json=report_json,
        report_id=report_id,
        document_id=document_id,
    )


def _sections(
    response: AgentRunResponse,
    evidence_ids: tuple[str, ...],
) -> tuple[EvidenceBackedReportSection, ...]:
    sections = [
        EvidenceBackedReportSection(
            id="evidence_scope",
            title="Evidence Scope",
            evidence_ids=list(evidence_ids),
            claims=[
                ReportClaim(
                    key="evidence.scope",
                    text=(
                        "The run summary is limited to recorded lookup evidence, "
                        f"covering {len(evidence_ids)} evidence item(s)."
                    ),
                    evidence_ids=list(evidence_ids),
                )
            ],
        )
    ]
    calculation_claims = _calculation_claims(response)
    if calculation_claims:
        sections.append(
            EvidenceBackedReportSection(
                id="deterministic_calculations",
                title="Deterministic Calculations",
                evidence_ids=list(evidence_ids),
                claims=calculation_claims,
            )
        )
    return tuple(sections)


def _calculation_claims(response: AgentRunResponse) -> list[ReportClaim]:
    claims: list[ReportClaim] = []
    for assignment in response.assignments:
        assignment_evidence_ids = list(assignment.evidence_ids)
        if not assignment_evidence_ids:
            continue
        for index, output in enumerate(assignment.calculation_outputs, start=1):
            claims.append(
                ReportClaim(
                    key=f"calculation.{assignment.lane}.{index}",
                    text=f"Deterministic calculation output from {assignment.lane}: {output}.",
                    evidence_ids=assignment_evidence_ids,
                )
            )
    return claims


def _opportunities(response: AgentRunResponse) -> tuple[AgentRunOpportunityHypothesis, ...]:
    max_units_output = _first_max_units_output(response)
    if max_units_output is None:
        return ()
    calculation_evidence_ids = _calculation_evidence_ids(response, max_units_output)
    if not calculation_evidence_ids:
        return ()
    return (
        AgentRunOpportunityHypothesis(
            key="opportunity.by_right_capacity",
            status="hypothesis",
            current_verified_condition=f"Recorded lookup evidence supports {max_units_output}.",
            proposed_scenario="Test by-right development capacity using recorded zoning evidence.",
            required_zoning_entitlement_path=(
                "By-right scenario only; entitlement upside remains unverified until official "
                "local evidence is retrieved."
            ),
            calculation_outputs=[max_units_output],
            upside_mechanism=(
                "Developer value may exist if the by-right unit yield exceeds the current use."
            ),
            blocking_constraints=_opportunity_blockers(response),
            evidence_ids=list(calculation_evidence_ids),
            assumptions=[
                "Market rents, costs, financing terms, exit values, and lender terms remain underwriting assumptions until sourced."
            ],
            confidence=0.6,
            next_verification_step=(
                "Confirm market rents, costs, financing terms, and any missing dimensional "
                "standards before underwriting value."
            ),
        ),
    )


def _first_max_units_output(response: AgentRunResponse) -> str | None:
    for assignment in response.assignments:
        for output in assignment.calculation_outputs:
            if output.startswith("max_units="):
                return output
    return None


def _calculation_evidence_ids(
    response: AgentRunResponse,
    calculation_output: str,
) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            evidence_id
            for assignment in response.assignments
            if calculation_output in assignment.calculation_outputs
            for evidence_id in assignment.evidence_ids
        )
    )


def _opportunity_blockers(response: AgentRunResponse) -> list[str]:
    blockers = [
        *response.open_questions,
        *response.warnings,
        "Market rents, costs, financing terms, and entitlement outcomes are not verified by the lookup snapshot.",
    ]
    return list(dict.fromkeys(blocker for blocker in blockers if blocker))


def _specialist_lanes(response: AgentRunResponse) -> list[JsonValue]:
    return [_assignment_json(assignment) for assignment in response.assignments]


def _assumptions(response: AgentRunResponse) -> list[JsonValue]:
    assumptions: list[JsonValue] = []
    for index, question in enumerate(response.open_questions, start=1):
        assumptions.append(
            {
                "key": f"open_question.{index}",
                "text": question,
                "status": "requires_human_review",
                "source": "agent_run.open_question",
            }
        )
    for index, escalation in enumerate(response.escalations, start=1):
        assumptions.append(_escalation_assumption_json(index, escalation))
    for index, warning in enumerate(response.warnings, start=1):
        assumptions.append(
            {
                "key": f"warning.{index}",
                "text": warning,
                "status": "warning",
                "source": "agent_run.warning",
            }
        )
    return assumptions


def _assignment_json(assignment: AgentRunAssignmentResponse) -> dict[str, JsonValue]:
    return {
        "lane": assignment.lane,
        "objective": assignment.objective,
        "field_keys": list(assignment.field_keys),
        "evidence_ids": list(assignment.evidence_ids),
        "calculation_outputs": list(assignment.calculation_outputs),
        "warnings": list(assignment.warnings),
        "escalation_required": assignment.escalation_required,
    }


def _review_items(response: AgentRunResponse) -> list[JsonValue]:
    items: list[JsonValue] = []
    for index, question in enumerate(response.open_questions, start=1):
        items.append({"key": f"open_question.{index}", "text": question})
    for index, escalation in enumerate(response.escalations, start=1):
        items.append(_escalation_json(index, escalation))
    return items


def _escalation_assumption_json(
    index: int,
    escalation: AgentRunEscalationResponse,
) -> dict[str, JsonValue]:
    return {
        "key": f"escalation.{index}",
        "field_key": escalation.field_key,
        "text": f"{escalation.reason} Required action: {escalation.required_action}",
        "status": "requires_human_review",
        "source": "agent_run.escalation",
    }


def _escalation_json(
    index: int,
    escalation: AgentRunEscalationResponse,
) -> dict[str, JsonValue]:
    return {
        "key": f"escalation.{index}",
        "field_key": escalation.field_key,
        "reason": escalation.reason,
        "required_action": escalation.required_action,
    }
