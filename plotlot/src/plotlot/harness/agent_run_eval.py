from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from plotlot.harness.agent_run_artifact_claims import (
    incomplete_opportunity_keys,
    material_claim_count,
    missing_assumption_keys,
    opportunity_hypothesis_count,
    required_assumption_keys,
    unsupported_claim_keys,
)
from plotlot.harness.agent_run_eval_rules import (
    REQUIRED_SPECIALIST_LANES,
    calculation_lineage_traceability,
    evidence_coverage,
    escalation_visibility,
    incomplete_evidence_packet_ids,
    missing_calculation_outputs,
    missing_evidence_packet_ids,
    missing_required_lanes,
    missing_trace_requirements,
    ready_for_synthesis_gate,
    ratio,
    source_quality_traceability,
)
from plotlot.harness.agent_run_responses import AgentRunResponse
from plotlot.harness.agent_run_summary import AgentRunSummaryArtifact

AgentRunEvalStatus = Literal["passed", "failed"]

AGENT_RUN_EVAL_SUITE: Final = "agent_run_lookup_correctness"
AGENT_RUN_EVAL_MODEL_PROFILE: Final = "deterministic_agent_run_eval"


@dataclass(frozen=True, slots=True)
class AgentRunEvalMetrics:
    evidence_coverage: float
    source_quality_traceability: float
    calculation_lineage_traceability: float
    trace_replayability: float
    specialist_lane_coverage: float
    artifact_citation_coverage: float
    opportunity_hypothesis_completeness: float
    assumption_label_coverage: float
    escalation_visibility: float
    ready_for_synthesis_gate: float
    unsupported_claim_rate: float


@dataclass(frozen=True, slots=True)
class AgentRunEvalResult:
    run_id: str
    lookup_snapshot_id: str
    status: AgentRunEvalStatus
    metrics: AgentRunEvalMetrics
    missing_required_lanes: tuple[str, ...]
    missing_trace_requirements: tuple[str, ...]
    missing_evidence_packet_ids: tuple[str, ...]
    incomplete_evidence_packet_ids: tuple[str, ...]
    missing_calculation_outputs: tuple[str, ...]
    unsupported_claim_keys: tuple[str, ...]
    incomplete_opportunity_keys: tuple[str, ...]
    missing_assumption_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AgentRunEvalFindings:
    missing_required_lanes: tuple[str, ...]
    missing_trace_requirements: tuple[str, ...]
    missing_evidence_packet_ids: tuple[str, ...]
    incomplete_evidence_packet_ids: tuple[str, ...]
    missing_calculation_outputs: tuple[str, ...]
    unsupported_claim_keys: tuple[str, ...]
    incomplete_opportunity_keys: tuple[str, ...]
    missing_assumption_keys: tuple[str, ...]


def score_agent_run(
    response: AgentRunResponse,
    artifact: AgentRunSummaryArtifact,
) -> AgentRunEvalResult:
    findings = AgentRunEvalFindings(
        missing_required_lanes=missing_required_lanes(response),
        missing_trace_requirements=missing_trace_requirements(response),
        missing_evidence_packet_ids=missing_evidence_packet_ids(response),
        incomplete_evidence_packet_ids=incomplete_evidence_packet_ids(response),
        missing_calculation_outputs=missing_calculation_outputs(response),
        unsupported_claim_keys=unsupported_claim_keys(artifact),
        incomplete_opportunity_keys=incomplete_opportunity_keys(artifact),
        missing_assumption_keys=missing_assumption_keys(response, artifact),
    )
    material_claims = material_claim_count(artifact)
    opportunity_hypotheses = opportunity_hypothesis_count(artifact)
    required_assumptions = required_assumption_keys(response)
    metrics = AgentRunEvalMetrics(
        evidence_coverage=evidence_coverage(response),
        source_quality_traceability=source_quality_traceability(
            response,
            findings.missing_evidence_packet_ids,
            findings.incomplete_evidence_packet_ids,
        ),
        calculation_lineage_traceability=calculation_lineage_traceability(
            response,
            findings.missing_calculation_outputs,
        ),
        trace_replayability=0.0 if findings.missing_trace_requirements else 1.0,
        specialist_lane_coverage=ratio(
            len(REQUIRED_SPECIALIST_LANES) - len(findings.missing_required_lanes),
            len(REQUIRED_SPECIALIST_LANES),
        ),
        artifact_citation_coverage=ratio(
            material_claims - len(findings.unsupported_claim_keys),
            material_claims,
        ),
        opportunity_hypothesis_completeness=ratio(
            opportunity_hypotheses - len(findings.incomplete_opportunity_keys),
            opportunity_hypotheses,
        ),
        assumption_label_coverage=ratio(
            len(required_assumptions) - len(findings.missing_assumption_keys),
            len(required_assumptions),
        ),
        escalation_visibility=escalation_visibility(response),
        ready_for_synthesis_gate=ready_for_synthesis_gate(response),
        unsupported_claim_rate=ratio(len(findings.unsupported_claim_keys), material_claims),
    )
    return AgentRunEvalResult(
        run_id=response.run_id,
        lookup_snapshot_id=response.lookup_snapshot_id,
        status=_eval_status(metrics, findings),
        metrics=metrics,
        missing_required_lanes=findings.missing_required_lanes,
        missing_trace_requirements=findings.missing_trace_requirements,
        missing_evidence_packet_ids=findings.missing_evidence_packet_ids,
        incomplete_evidence_packet_ids=findings.incomplete_evidence_packet_ids,
        missing_calculation_outputs=findings.missing_calculation_outputs,
        unsupported_claim_keys=findings.unsupported_claim_keys,
        incomplete_opportunity_keys=findings.incomplete_opportunity_keys,
        missing_assumption_keys=findings.missing_assumption_keys,
    )


def _eval_status(
    metrics: AgentRunEvalMetrics,
    findings: AgentRunEvalFindings,
) -> AgentRunEvalStatus:
    if (
        findings.missing_required_lanes
        or findings.missing_trace_requirements
        or findings.missing_evidence_packet_ids
        or findings.incomplete_evidence_packet_ids
        or findings.missing_calculation_outputs
        or findings.incomplete_opportunity_keys
        or findings.missing_assumption_keys
    ):
        return "failed"
    if metrics.unsupported_claim_rate > 0:
        return "failed"
    if (
        metrics.evidence_coverage < 1
        or metrics.source_quality_traceability < 1
        or metrics.calculation_lineage_traceability < 1
        or metrics.artifact_citation_coverage < 1
        or metrics.opportunity_hypothesis_completeness < 1
        or metrics.escalation_visibility < 1
        or metrics.ready_for_synthesis_gate < 1
    ):
        return "failed"
    return "passed"
