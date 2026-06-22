from __future__ import annotations

import pytest

from plotlot.core.lookup_snapshot import RunId
from plotlot.harness import AgentRunRequest, AgentRunRuntime, ContextBuildRequest
from plotlot.harness.agent_run_responses import AgentRunResponse
from plotlot.harness.agent_run_responses import agent_run_response
from plotlot.harness.agent_run_summary import build_agent_run_summary_from_response
from plotlot.harness.agent_run_trace import (
    AgentRunReplayTraceInput,
    build_agent_run_replay_trace,
)
from plotlot.pipeline.lookup_snapshot import build_lookup_snapshot
from tests.unit.lookup_snapshot_repository_fixtures import report


def test_agent_run_trace_is_not_replay_ready_without_evidence_packets() -> None:
    # Given: a run records evidence IDs but lost the source-quality evidence packets.
    snapshot = build_lookup_snapshot(report(with_density_analysis=True))
    record = AgentRunRuntime().start_run(
        AgentRunRequest(
            run_id=RunId("run_trace_missing_packets"),
            context_request=ContextBuildRequest(
                workspace_id="ws_trace_missing_packets",
                project_id="project_trace_missing_packets",
                objective="Replay verified development capacity.",
                lookup_snapshot=snapshot,
            ),
        )
    )
    response = agent_run_response(record, str(snapshot.lookup_snapshot_id)).model_copy(
        update={"evidence_packets": ()}
    )
    artifact = build_agent_run_summary_from_response(
        response,
        report_id="report_trace_missing_packets",
        document_id="document_trace_missing_packets",
    )

    # When: the replay package is built from the incomplete run trace.
    trace = build_agent_run_replay_trace(
        AgentRunReplayTraceInput(
            response=response,
            artifact=artifact,
            latest_eval=None,
            improvement_summary=None,
        )
    )

    # Then: replay readiness blocks on the missing source-quality packets.
    assert trace.replay_ready is False
    assert set(trace.missing_replay_requirements) == {
        f"evidence_packet:{evidence_id}" for evidence_id in response.evidence_ids
    } | {"calculation_lineage:max_units=2"}


def test_agent_run_trace_artifact_exposes_typed_assumption_sources() -> None:
    response = _agent_run_response(
        "run_trace_assumptions",
        warnings=("Manual reviewer must confirm parking count.",),
    )
    artifact = build_agent_run_summary_from_response(
        response,
        report_id="report_trace_assumptions",
        document_id="document_trace_assumptions",
    )

    trace = build_agent_run_replay_trace(
        AgentRunReplayTraceInput(
            response=response,
            artifact=artifact,
            latest_eval=None,
            improvement_summary=None,
        )
    )

    assumption_sources = {assumption.source for assumption in trace.artifact.assumptions}
    assert assumption_sources == {
        "agent_run.open_question",
        "agent_run.escalation",
        "agent_run.warning",
    }
    assert any(
        assumption.field_key == "standards.setbacks.front"
        and assumption.status == "requires_human_review"
        for assumption in trace.artifact.assumptions
    )
    assert any(
        assumption.source == "agent_run.warning"
        and assumption.text == "Manual reviewer must confirm parking count."
        for assumption in trace.artifact.assumptions
    )
    assert all(
        "evidence_ids" not in assumption.model_dump() for assumption in trace.artifact.assumptions
    )


def test_agent_run_trace_rejects_malformed_artifact_assumption_shape() -> None:
    response = _agent_run_response("run_trace_bad_assumption")
    artifact = build_agent_run_summary_from_response(response).model_copy(
        update={
            "report_json": {
                "lookup_snapshot_id": response.lookup_snapshot_id,
                "assumptions": [
                    {
                        "key": "open_question.1",
                        "text": "This assumption has an invalid status.",
                        "status": "verified",
                        "source": "agent_run.open_question",
                    }
                ],
            }
        }
    )

    with pytest.raises(ValueError, match="artifact assumptions failed schema validation"):
        build_agent_run_replay_trace(
            AgentRunReplayTraceInput(
                response=response,
                artifact=artifact,
                latest_eval=None,
                improvement_summary=None,
            )
        )


def test_agent_run_trace_rejects_non_list_artifact_assumptions() -> None:
    response = _agent_run_response("run_trace_non_list_assumption")
    artifact = build_agent_run_summary_from_response(response).model_copy(
        update={
            "report_json": {
                "lookup_snapshot_id": response.lookup_snapshot_id,
                "assumptions": {
                    "key": "open_question.1",
                    "text": "Not a list.",
                    "status": "requires_human_review",
                    "source": "agent_run.open_question",
                },
            }
        }
    )

    with pytest.raises(ValueError, match="artifact assumptions must be a list"):
        build_agent_run_replay_trace(
            AgentRunReplayTraceInput(
                response=response,
                artifact=artifact,
                latest_eval=None,
                improvement_summary=None,
            )
        )


def _agent_run_response(
    run_id: str,
    *,
    warnings: tuple[str, ...] = (),
) -> AgentRunResponse:
    snapshot = build_lookup_snapshot(report(with_density_analysis=True))
    record = AgentRunRuntime().start_run(
        AgentRunRequest(
            run_id=RunId(run_id),
            context_request=ContextBuildRequest(
                workspace_id="ws_trace",
                project_id="project_trace",
                objective="Replay verified development capacity.",
                lookup_snapshot=snapshot,
                warnings=warnings,
            ),
        )
    )
    return agent_run_response(record, str(snapshot.lookup_snapshot_id))
