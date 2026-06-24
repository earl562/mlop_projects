from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict

from plotlot.harness.agent_run_eval_rules import (
    incomplete_evidence_packet_ids,
    missing_calculation_outputs,
    missing_evidence_packet_ids,
)
from plotlot.harness.agent_run_eval_history import (
    AgentRunImprovementStatus,
    AgentRunImprovementSummary,
    StoredAgentRunEvalRecord,
)
from plotlot.harness.agent_run_improvement_log import (
    AgentRunImprovementDirection,
    AgentRunImprovementLogEntry,
)
from plotlot.harness.agent_run_responses import (
    AgentRunAssignmentResponse,
    AgentRunEscalationResponse,
    AgentRunEvidencePacketResponse,
    AgentRunResponse,
    AgentRunTraceStepResponse,
)
from plotlot.harness.agent_run_summary import AgentRunSummaryArtifact
from plotlot.harness.agent_run_trace_artifact import (
    AgentRunArtifactTraceResponse,
    artifact_trace,
)
from plotlot.harness.agent_run_trace_sources import (
    AgentRunSourceRetrievalTraceResponse,
    source_retrieval_trace,
)

AgentRunTraceBaselineStatus = Literal["available", "missing"]


@dataclass(frozen=True, slots=True)
class AgentRunReplayTraceInput:
    response: AgentRunResponse
    artifact: AgentRunSummaryArtifact
    latest_eval: StoredAgentRunEvalRecord | None
    improvement_summary: AgentRunImprovementSummary | None


class AgentRunEvalTraceResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    eval_run_id: str
    eval_case_result_id: str
    gold_set_case_id: str
    status: str
    metric_keys: tuple[str, ...]
    evidence_metric_keys: tuple[str, ...]
    trajectory_metric_keys: tuple[str, ...]


class AgentRunImprovementLogTraceResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: str
    researched_input: str
    changed_rule: str
    metric: str
    direction: AgentRunImprovementDirection
    reason: str
    affected_golden_cases: tuple[str, ...]
    before_score: float
    after_score: float
    delta: float
    gate_blocking: bool
    unresolved_risk: str | None


class AgentRunImprovementTraceResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    baseline_status: AgentRunTraceBaselineStatus
    improvement_status: AgentRunImprovementStatus
    release_blocked: bool
    improved_metric_keys: tuple[str, ...]
    regressed_metric_keys: tuple[str, ...]
    improvement_log: tuple[AgentRunImprovementLogTraceResponse, ...]


class AgentRunReplayTraceResponse(BaseModel):
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
    evidence_packets: tuple[AgentRunEvidencePacketResponse, ...]
    source_retrievals: tuple[AgentRunSourceRetrievalTraceResponse, ...]
    warnings: tuple[str, ...]
    open_questions: tuple[str, ...]
    assignments: tuple[AgentRunAssignmentResponse, ...]
    escalations: tuple[AgentRunEscalationResponse, ...]
    trace_steps: tuple[AgentRunTraceStepResponse, ...]
    artifact: AgentRunArtifactTraceResponse
    latest_eval: AgentRunEvalTraceResponse | None
    improvement: AgentRunImprovementTraceResponse | None
    replay_ready: bool
    missing_replay_requirements: tuple[str, ...]


def build_agent_run_replay_trace(
    trace_input: AgentRunReplayTraceInput,
) -> AgentRunReplayTraceResponse:
    missing_requirements = _missing_replay_requirements(
        trace_input.response,
        trace_input.artifact,
    )
    return AgentRunReplayTraceResponse(
        run_id=trace_input.response.run_id,
        lookup_snapshot_id=trace_input.response.lookup_snapshot_id,
        workspace_id=trace_input.response.workspace_id,
        project_id=trace_input.response.project_id,
        site_id=trace_input.response.site_id,
        objective=trace_input.response.objective,
        status=trace_input.response.status,
        ready_for_synthesis=trace_input.response.ready_for_synthesis,
        evidence_ids=trace_input.response.evidence_ids,
        evidence_packets=trace_input.response.evidence_packets,
        source_retrievals=tuple(
            source_retrieval_trace(packet) for packet in trace_input.response.evidence_packets
        ),
        warnings=trace_input.response.warnings,
        open_questions=trace_input.response.open_questions,
        assignments=trace_input.response.assignments,
        escalations=trace_input.response.escalations,
        trace_steps=trace_input.response.trace_steps,
        artifact=artifact_trace(trace_input.artifact),
        latest_eval=_eval_trace(trace_input.latest_eval),
        improvement=_improvement_trace(trace_input.improvement_summary),
        replay_ready=not missing_requirements,
        missing_replay_requirements=missing_requirements,
    )


def _missing_replay_requirements(
    response: AgentRunResponse,
    artifact: AgentRunSummaryArtifact,
) -> tuple[str, ...]:
    missing: list[str] = []
    if not response.trace_steps:
        missing.append("trace_steps")
    if not response.evidence_ids:
        missing.append("run_evidence_ids")
    if not artifact.evidence_ids:
        missing.append("artifact_evidence_ids")
    if artifact.report_id is None:
        missing.append("report_id")
    if artifact.document_id is None:
        missing.append("document_id")
    missing.extend(
        f"evidence_packet:{evidence_id}" for evidence_id in missing_evidence_packet_ids(response)
    )
    missing.extend(
        f"traceable_evidence_packet:{evidence_id}"
        for evidence_id in incomplete_evidence_packet_ids(response)
    )
    missing.extend(
        f"calculation_lineage:{output}" for output in missing_calculation_outputs(response)
    )
    return tuple(missing)


def _eval_trace(record: StoredAgentRunEvalRecord | None) -> AgentRunEvalTraceResponse | None:
    if record is None:
        return None
    return AgentRunEvalTraceResponse(
        eval_run_id=record.eval_run_id,
        eval_case_result_id=record.eval_case_result_id,
        gold_set_case_id=record.gold_set_case_id,
        status=record.status,
        metric_keys=tuple(record.metrics),
        evidence_metric_keys=tuple(record.evidence_metrics),
        trajectory_metric_keys=tuple(record.trajectory_metrics),
    )


def _improvement_trace(
    summary: AgentRunImprovementSummary | None,
) -> AgentRunImprovementTraceResponse | None:
    if summary is None:
        return None
    return AgentRunImprovementTraceResponse(
        baseline_status=_baseline_status(summary),
        improvement_status=summary.improvement_status,
        release_blocked=summary.release_blocked,
        improved_metric_keys=summary.improved_metric_keys,
        regressed_metric_keys=summary.regressed_metric_keys,
        improvement_log=tuple(
            _improvement_log_entry_trace(entry) for entry in summary.improvement_log
        ),
    )


def _improvement_log_entry_trace(
    entry: AgentRunImprovementLogEntry,
) -> AgentRunImprovementLogTraceResponse:
    return AgentRunImprovementLogTraceResponse(
        source=entry.source,
        researched_input=entry.researched_input,
        changed_rule=entry.changed_rule,
        metric=entry.metric,
        direction=entry.direction,
        reason=entry.reason,
        affected_golden_cases=entry.affected_golden_cases,
        before_score=entry.before_score,
        after_score=entry.after_score,
        delta=entry.delta,
        gate_blocking=entry.gate_blocking,
        unresolved_risk=entry.unresolved_risk,
    )


def _baseline_status(
    summary: AgentRunImprovementSummary,
) -> AgentRunTraceBaselineStatus:
    if summary.previous is None:
        return "missing"
    return "available"
