from __future__ import annotations

from plotlot.core.lookup_snapshot import RunId
from plotlot.harness import AgentRunRequest, AgentRunRuntime, ContextBuildRequest
from plotlot.harness.agent_run_eval import score_agent_run
from plotlot.harness.agent_run_responses import agent_run_response
from plotlot.harness.agent_run_summary import build_agent_run_summary_from_response
from plotlot.pipeline.lookup_snapshot import build_lookup_snapshot
from tests.unit.lookup_snapshot_repository_fixtures import report


def test_score_agent_run_fails_when_review_items_are_missing_assumptions() -> None:
    # Given: a review-blocked run has a report artifact without labeled assumptions.
    response = _agent_run_response()
    artifact = build_agent_run_summary_from_response(response)
    artifact = artifact.model_copy(
        update={"report_json": {**artifact.report_json, "assumptions": []}}
    )

    # When: the run is scored against report assumption labeling requirements.
    result = score_agent_run(response, artifact)

    # Then: eval fails because reports must separate assumptions from verified facts.
    assert result.status == "failed"
    assert result.metrics.assumption_label_coverage == 0.0
    assert "open_question.1" in result.missing_assumption_keys
    assert "escalation.1" in result.missing_assumption_keys
    assert "warning.1" in result.missing_assumption_keys


def _agent_run_response():
    snapshot = build_lookup_snapshot(report(with_density_analysis=True))
    record = AgentRunRuntime().start_run(
        AgentRunRequest(
            run_id=RunId("run_agent_eval_assumption_labels"),
            context_request=ContextBuildRequest(
                workspace_id="ws_agent_eval_assumptions",
                project_id="project_agent_eval_assumptions",
                objective="Find verified development value.",
                lookup_snapshot=snapshot,
            ),
        )
    )
    return agent_run_response(record, str(snapshot.lookup_snapshot_id))
