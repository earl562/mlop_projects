from __future__ import annotations

from plotlot.core.lookup_snapshot import RunId
from plotlot.harness import AgentRunRequest, AgentRunRuntime, ContextBuildRequest
from plotlot.harness.agent_run_eval import score_agent_run
from plotlot.harness.agent_run_responses import agent_run_response
from plotlot.harness.agent_run_summary import build_agent_run_summary_from_response
from plotlot.pipeline.lookup_snapshot import build_lookup_snapshot
from tests.unit.lookup_snapshot_repository_fixtures import report


def test_score_agent_run_fails_when_escalations_are_missing_from_trace() -> None:
    # Given: an agent run has review escalations but trace steps omit escalation flags.
    snapshot = build_lookup_snapshot(report(with_density_analysis=True))
    record = AgentRunRuntime().start_run(
        AgentRunRequest(
            run_id=RunId("run_agent_eval_escalation_trace"),
            context_request=ContextBuildRequest(
                workspace_id="ws_agent_eval_escalation",
                project_id="project_agent_eval_escalation",
                objective="Find verified development value.",
                lookup_snapshot=snapshot,
            ),
        )
    )
    base_response = agent_run_response(record, str(snapshot.lookup_snapshot_id))
    trace_steps = tuple(
        step.model_copy(update={"escalation_required": False}) for step in base_response.trace_steps
    )
    response = base_response.model_copy(update={"trace_steps": trace_steps})
    artifact = build_agent_run_summary_from_response(response)

    # When: the run is scored against deterministic trace replay requirements.
    result = score_agent_run(response, artifact)

    # Then: eval fails because replay cannot prove the escalation was captured in trace.
    assert result.status == "failed"
    assert result.metrics.trace_replayability == 0.0
    assert "trace_covers_run_escalations" in result.missing_trace_requirements
