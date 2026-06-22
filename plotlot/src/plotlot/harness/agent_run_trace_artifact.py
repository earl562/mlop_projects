from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from plotlot.harness.agent_run_opportunities import AgentRunOpportunityHypothesis
from plotlot.harness.agent_run_summary import AgentRunSummaryArtifact
from plotlot.land_use.models import EvidenceBackedReportSection

AgentRunArtifactAssumptionSource = Literal[
    "agent_run.open_question",
    "agent_run.escalation",
    "agent_run.warning",
]
AgentRunArtifactAssumptionStatus = Literal["requires_human_review", "warning"]


class AgentRunArtifactAssumptionResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str
    text: str
    status: AgentRunArtifactAssumptionStatus
    source: AgentRunArtifactAssumptionSource
    field_key: str | None = None


class AgentRunArtifactTraceResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    report_id: str | None
    document_id: str | None
    evidence_ids: tuple[str, ...]
    sections: tuple[EvidenceBackedReportSection, ...]
    opportunities: tuple[AgentRunOpportunityHypothesis, ...]
    assumptions: tuple[AgentRunArtifactAssumptionResponse, ...]
    message: str | None


def artifact_trace(artifact: AgentRunSummaryArtifact) -> AgentRunArtifactTraceResponse:
    return AgentRunArtifactTraceResponse(
        status=artifact.status,
        report_id=artifact.report_id,
        document_id=artifact.document_id,
        evidence_ids=artifact.evidence_ids,
        sections=artifact_sections(artifact),
        opportunities=artifact_opportunities(artifact),
        assumptions=artifact_assumptions(artifact),
        message=artifact.message,
    )


def artifact_sections(
    artifact: AgentRunSummaryArtifact,
) -> tuple[EvidenceBackedReportSection, ...]:
    raw_sections = artifact.report_json.get("sections")
    if raw_sections is None:
        return ()
    if not isinstance(raw_sections, list):
        raise ValueError("artifact sections must be a list")
    try:
        return tuple(EvidenceBackedReportSection.model_validate(item) for item in raw_sections)
    except ValidationError as exc:
        raise ValueError("artifact sections failed schema validation") from exc


def artifact_opportunities(
    artifact: AgentRunSummaryArtifact,
) -> tuple[AgentRunOpportunityHypothesis, ...]:
    raw_opportunities = artifact.report_json.get("opportunities")
    if raw_opportunities is None:
        return ()
    if not isinstance(raw_opportunities, list):
        raise ValueError("artifact opportunities must be a list")
    try:
        return tuple(
            AgentRunOpportunityHypothesis.model_validate(item) for item in raw_opportunities
        )
    except ValidationError as exc:
        raise ValueError("artifact opportunities failed schema validation") from exc


def artifact_assumptions(
    artifact: AgentRunSummaryArtifact,
) -> tuple[AgentRunArtifactAssumptionResponse, ...]:
    raw_assumptions = artifact.report_json.get("assumptions")
    if raw_assumptions is None:
        return ()
    if not isinstance(raw_assumptions, list):
        raise ValueError("artifact assumptions must be a list")
    try:
        return tuple(
            AgentRunArtifactAssumptionResponse.model_validate(item) for item in raw_assumptions
        )
    except ValidationError as exc:
        raise ValueError("artifact assumptions failed schema validation") from exc
