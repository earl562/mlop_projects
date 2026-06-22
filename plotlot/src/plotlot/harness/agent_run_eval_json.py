from __future__ import annotations

from plotlot.harness.agent_run_eval import AgentRunEvalMetrics, AgentRunEvalResult
from plotlot.pipeline.lookup_snapshot_json import JsonValue


def metrics_to_json(metrics: AgentRunEvalMetrics) -> dict[str, JsonValue]:
    return {
        "evidence_coverage": metrics.evidence_coverage,
        "source_quality_traceability": metrics.source_quality_traceability,
        "calculation_lineage_traceability": metrics.calculation_lineage_traceability,
        "trace_replayability": metrics.trace_replayability,
        "specialist_lane_coverage": metrics.specialist_lane_coverage,
        "artifact_citation_coverage": metrics.artifact_citation_coverage,
        "opportunity_hypothesis_completeness": (metrics.opportunity_hypothesis_completeness),
        "assumption_label_coverage": metrics.assumption_label_coverage,
        "escalation_visibility": metrics.escalation_visibility,
        "ready_for_synthesis_gate": metrics.ready_for_synthesis_gate,
        "unsupported_claim_rate": metrics.unsupported_claim_rate,
    }


def diffs_to_json(result: AgentRunEvalResult) -> dict[str, JsonValue]:
    return {
        "run_id": result.run_id,
        "lookup_snapshot_id": result.lookup_snapshot_id,
        "missing_required_lanes": list(result.missing_required_lanes),
        "missing_trace_requirements": list(result.missing_trace_requirements),
        "missing_evidence_packet_ids": list(result.missing_evidence_packet_ids),
        "incomplete_evidence_packet_ids": list(result.incomplete_evidence_packet_ids),
        "missing_calculation_outputs": list(result.missing_calculation_outputs),
        "unsupported_claim_keys": list(result.unsupported_claim_keys),
        "incomplete_opportunity_keys": list(result.incomplete_opportunity_keys),
        "missing_assumption_keys": list(result.missing_assumption_keys),
    }


def response_to_json(
    result: AgentRunEvalResult,
    eval_run_id: str,
    eval_case_result_id: str,
) -> dict[str, JsonValue]:
    return {
        "run_id": result.run_id,
        "lookup_snapshot_id": result.lookup_snapshot_id,
        "status": result.status,
        "metrics": metrics_to_json(result.metrics),
        "diffs": diffs_to_json(result),
        "eval_run_id": eval_run_id,
        "eval_case_result_id": eval_case_result_id,
    }
