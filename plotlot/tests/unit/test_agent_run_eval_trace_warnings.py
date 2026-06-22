from __future__ import annotations

from plotlot.core.lookup_snapshot import RunId
from plotlot.harness import AgentRunRequest, AgentRunRuntime, ContextBuildRequest
from plotlot.harness.agent_run_eval import score_agent_run
from plotlot.harness.agent_run_responses import agent_run_response
from plotlot.harness.agent_run_summary import build_agent_run_summary_from_response
from plotlot.pipeline.lookup_snapshot import build_lookup_snapshot
from tests.unit.lookup_snapshot_repository_fixtures import report


def test_score_agent_run_fails_when_warnings_are_missing_from_trace() -> None:
    # Given: a replayable run exposes a user-visible warning not present in trace steps.
    snapshot = build_lookup_snapshot(report(with_density_analysis=True))
    record = AgentRunRuntime().start_run(
        AgentRunRequest(
            run_id=RunId("run_agent_eval_warning_trace"),
            context_request=ContextBuildRequest(
                workspace_id="ws_agent_eval_warning",
                project_id="project_agent_eval_warning",
                objective="Find verified development value.",
                lookup_snapshot=snapshot,
            ),
        )
    )
    response = agent_run_response(record, str(snapshot.lookup_snapshot_id)).model_copy(
        update={"warnings": ("stale_source",)}
    )
    artifact = build_agent_run_summary_from_response(response)

    # When: the run is scored against deterministic trace replay requirements.
    result = score_agent_run(response, artifact)

    # Then: eval fails because replay cannot prove the warning was captured in trace.
    assert result.status == "failed"
    assert result.metrics.trace_replayability == 0.0
    assert "trace_covers_run_warnings" in result.missing_trace_requirements
