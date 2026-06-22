from __future__ import annotations

import pytest

from plotlot.core.lookup_snapshot import RunId
from plotlot.harness import AgentRunRequest, AgentRunRuntime, ContextBuildRequest
from plotlot.harness.agent_run_eval import score_agent_run
from plotlot.harness.agent_run_eval_history import load_agent_run_improvement_summary
from plotlot.harness.agent_run_eval_repository import persist_agent_run_eval_result
from plotlot.harness.agent_run_responses import agent_run_response
from plotlot.harness.agent_run_summary import (
    AgentRunSummaryArtifact,
    build_agent_run_summary_from_response,
)
from plotlot.pipeline.lookup_snapshot import build_lookup_snapshot
from plotlot.pipeline.lookup_snapshot_json import JsonValue
from plotlot.storage.db import get_session
from tests.unit.lookup_snapshot_repository_fixtures import report


def test_score_agent_run_passes_for_replayable_evidence_backed_run() -> None:
    # Given: a replayable agent run with lookup evidence and a cited summary artifact.
    response = _agent_run_response()
    artifact = build_agent_run_summary_from_response(
        response,
        report_id="report_agent_eval",
        document_id="document_agent_eval",
    )

    # When: the run is scored against agent-run correctness gates.
    result = score_agent_run(response, artifact)

    # Then: evidence, trajectory, lane, and artifact citation gates pass.
    assert result.status == "passed"
    assert result.metrics.evidence_coverage == 1.0
    assert result.metrics.trace_replayability == 1.0
    assert result.metrics.specialist_lane_coverage == 1.0
    assert result.metrics.source_quality_traceability == 1.0
    assert result.metrics.calculation_lineage_traceability == 1.0
    assert result.metrics.artifact_citation_coverage == 1.0
    assert result.metrics.opportunity_hypothesis_completeness == 1.0
    assert result.metrics.assumption_label_coverage == 1.0
    assert result.missing_evidence_packet_ids == ()
    assert result.incomplete_evidence_packet_ids == ()
    assert result.missing_calculation_outputs == ()
    assert result.unsupported_claim_keys == ()
    assert result.incomplete_opportunity_keys == ()
    assert result.missing_assumption_keys == ()


def test_score_agent_run_fails_when_evidence_packets_are_missing_from_trace() -> None:
    # Given: a run has evidence IDs but its source-quality evidence packets are absent.
    response = _agent_run_response().model_copy(update={"evidence_packets": ()})
    artifact = build_agent_run_summary_from_response(response)

    # When: the run is scored against source-quality traceability gates.
    result = score_agent_run(response, artifact)

    # Then: the eval fails because evidence quality cannot be replayed from the trace.
    assert result.status == "failed"
    assert result.metrics.source_quality_traceability == 0.0
    assert set(result.missing_evidence_packet_ids) == set(response.evidence_ids)


def test_score_agent_run_fails_when_calculations_lack_evidence_packet_lineage() -> None:
    # Given: a run records calculation outputs, but packets no longer tie them to evidence.
    response = _agent_run_response()
    response = response.model_copy(
        update={
            "evidence_packets": tuple(
                packet.model_copy(update={"calculation_outputs": ()})
                for packet in response.evidence_packets
            )
        }
    )
    artifact = build_agent_run_summary_from_response(response)

    # When: the run is scored against deterministic calculation replayability gates.
    result = score_agent_run(response, artifact)

    # Then: the eval fails because max-units cannot be replayed from evidence packet lineage.
    assert result.status == "failed"
    assert result.metrics.calculation_lineage_traceability == 0.0
    assert result.missing_calculation_outputs == ("max_units=2",)


def test_score_agent_run_fails_when_material_artifact_claim_lacks_evidence() -> None:
    # Given: an otherwise replayable run with a material uncited report claim.
    response = _agent_run_response()
    report_json: dict[str, JsonValue] = {
        "title": "Unsupported summary",
        "generated_by": "test",
        "run_id": response.run_id,
        "lookup_snapshot_id": response.lookup_snapshot_id,
        "sections": [
            {
                "id": "unsupported",
                "title": "Unsupported",
                "evidence_ids": list(response.evidence_ids),
                "claims": [
                    {
                        "key": "unsupported.value",
                        "text": "This claim has no supporting evidence.",
                        "material": True,
                        "evidence_ids": [],
                    }
                ],
            }
        ],
    }
    artifact = AgentRunSummaryArtifact(
        status="draft",
        run_id=response.run_id,
        lookup_snapshot_id=response.lookup_snapshot_id,
        evidence_ids=response.evidence_ids,
        report_json=report_json,
    )

    # When: the run is scored.
    result = score_agent_run(response, artifact)

    # Then: unsupported material claims fail the agent-run eval gate.
    assert result.status == "failed"
    assert result.metrics.artifact_citation_coverage == 0.0
    assert result.unsupported_claim_keys == ("unsupported.value",)


def test_score_agent_run_fails_when_value_hypothesis_lacks_evidence() -> None:
    # Given: an otherwise replayable run with an uncited developer-value hypothesis.
    response = _agent_run_response()
    artifact = build_agent_run_summary_from_response(response).model_copy(
        update={
            "report_json": {
                "title": "Unsupported value hypothesis",
                "generated_by": "test",
                "run_id": response.run_id,
                "lookup_snapshot_id": response.lookup_snapshot_id,
                "sections": [],
                "opportunities": [
                    {
                        "key": "opportunity.free_land",
                        "status": "hypothesis",
                        "current_verified_condition": "Recorded parcel facts exist.",
                        "proposed_scenario": "Test instant-equity logic.",
                        "required_zoning_entitlement_path": "unknown",
                        "calculation_outputs": ["max_units=2"],
                        "upside_mechanism": "Land basis may be covered by created value.",
                        "blocking_constraints": ["Market assumptions are unverified."],
                        "evidence_ids": [],
                        "assumptions": ["Rental income is assumed."],
                        "confidence": 0.2,
                        "next_verification_step": "Retrieve market and lender evidence.",
                    }
                ],
            }
        }
    )

    # When: the run is scored.
    result = score_agent_run(response, artifact)

    # Then: uncited value hypotheses fail the artifact citation gate.
    assert result.status == "failed"
    assert result.metrics.artifact_citation_coverage == 0.0
    assert result.unsupported_claim_keys == ("opportunity.free_land",)


def test_score_agent_run_fails_when_value_hypothesis_lacks_required_fields() -> None:
    # Given: a cited developer-value hypothesis is missing the next verification step.
    response = _agent_run_response()
    artifact = build_agent_run_summary_from_response(response)
    opportunity = artifact.report_json["opportunities"][0]
    assert isinstance(opportunity, dict)
    incomplete_opportunity = dict(opportunity)
    incomplete_opportunity.pop("next_verification_step")
    artifact = artifact.model_copy(
        update={
            "report_json": {
                **artifact.report_json,
                "opportunities": [incomplete_opportunity],
            }
        }
    )

    # When: the run is scored.
    result = score_agent_run(response, artifact)

    # Then: incomplete value hypotheses fail the value-discovery eval gate.
    assert result.status == "failed"
    assert result.metrics.opportunity_hypothesis_completeness == 0.0
    assert result.incomplete_opportunity_keys == ("opportunity.by_right_capacity",)


@pytest.mark.asyncio
async def test_agent_run_improvement_summary_compares_against_previous_baseline() -> None:
    # Given: two persisted agent-run evals in the deterministic eval suite.
    previous_response = _agent_run_response("run_agent_eval_previous")
    previous_artifact = build_agent_run_summary_from_response(previous_response)
    previous_result = score_agent_run(previous_response, previous_artifact)
    current_response = _agent_run_response("run_agent_eval_current")
    current_artifact = build_agent_run_summary_from_response(current_response)
    current_result = score_agent_run(current_response, current_artifact)

    session = await get_session()
    try:
        await persist_agent_run_eval_result(session, previous_result)
        await persist_agent_run_eval_result(session, current_result)

        # When: the improvement summary is loaded for the latest run.
        summary = await load_agent_run_improvement_summary(
            session,
            current_result.run_id,
        )
    finally:
        await session.close()

    # Then: the summary compares the current eval with the previous baseline.
    assert summary is not None
    assert summary.current.run_id == current_result.run_id
    assert summary.previous is not None
    assert summary.previous.run_id == previous_result.run_id
    assert summary.improvement_status == "flat"
    assert summary.release_blocked is False
    assert summary.deltas["evidence_coverage"] == 0.0
    assert summary.regressed_metric_keys == ()


@pytest.mark.asyncio
async def test_agent_run_improvement_summary_records_regression_log() -> None:
    # Given: a current agent-run eval regresses from a previous evidence-backed baseline.
    previous_response = _agent_run_response("run_agent_eval_log_previous")
    previous_artifact = build_agent_run_summary_from_response(previous_response)
    previous_result = score_agent_run(previous_response, previous_artifact)
    current_response = _agent_run_response("run_agent_eval_log_current").model_copy(
        update={"evidence_packets": ()}
    )
    current_artifact = build_agent_run_summary_from_response(current_response)
    current_result = score_agent_run(current_response, current_artifact)

    session = await get_session()
    try:
        await persist_agent_run_eval_result(session, previous_result)
        await persist_agent_run_eval_result(session, current_result)

        # When: the improvement summary is loaded for the regressed run.
        summary = await load_agent_run_improvement_summary(
            session,
            current_result.run_id,
        )
    finally:
        await session.close()

    # Then: the summary records a release-blocking before/after improvement log.
    assert summary is not None
    assert summary.improvement_status == "regressed"
    assert summary.release_blocked is True
    source_quality_entry = next(
        entry for entry in summary.improvement_log if entry.metric == "source_quality_traceability"
    )
    assert source_quality_entry.source == "agent_run_eval"
    assert source_quality_entry.researched_input == current_result.run_id
    assert source_quality_entry.changed_rule == "eval_metric:source_quality_traceability"
    assert source_quality_entry.direction == "regressed"
    assert source_quality_entry.reason == "baseline_delta"
    assert source_quality_entry.affected_golden_cases == (summary.current.gold_set_case_id,)
    assert source_quality_entry.before_score == 1.0
    assert source_quality_entry.after_score == 0.0
    assert source_quality_entry.delta == -1.0
    assert source_quality_entry.gate_blocking is True
    assert source_quality_entry.unresolved_risk == "agent_run_regression_requires_review"


def _agent_run_response(run_id: str = "run_agent_eval"):
    snapshot = build_lookup_snapshot(report(with_density_analysis=True))
    record = AgentRunRuntime().start_run(
        AgentRunRequest(
            run_id=RunId(run_id),
            context_request=ContextBuildRequest(
                workspace_id="ws_agent_eval",
                project_id="project_agent_eval",
                objective="Find verified development value.",
                lookup_snapshot=snapshot,
            ),
        )
    )
    return agent_run_response(record, str(snapshot.lookup_snapshot_id))
