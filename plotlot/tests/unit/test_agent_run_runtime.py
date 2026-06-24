from __future__ import annotations

from plotlot.core.lookup_snapshot import RunId
from plotlot.harness import (
    AgentRunRequest,
    AgentRunRuntime,
    AgentRunStatus,
    ContextBuildRequest,
    RunTraceStepKind,
    SpecialistLane,
)
from plotlot.pipeline.lookup_snapshot import build_lookup_snapshot
from tests.unit.lookup_snapshot_repository_fixtures import report


def test_agent_run_runtime_records_replayable_context_plan_trace() -> None:
    # Given: an evidence-backed lookup snapshot that should seed the agent run.
    snapshot = build_lookup_snapshot(report(with_density_analysis=True))
    request = AgentRunRequest(
        run_id=RunId("run_agent_trace_test"),
        context_request=ContextBuildRequest(
            workspace_id="ws_agent",
            project_id="project_agent",
            objective="Find verified by-right development capacity.",
            lookup_snapshot=snapshot,
        ),
    )

    # When: the run runtime builds context and a deterministic specialist plan.
    run_record = AgentRunRuntime().start_run(request)

    # Then: the run is replayable from recorded context, plan, and trace steps.
    assert run_record.run_id == RunId("run_agent_trace_test")
    assert run_record.context_packet.evidence_ids == run_record.evidence_ids
    assert run_record.plan.evidence_ids == run_record.evidence_ids
    assert tuple(step.sequence for step in run_record.trace_steps) == tuple(
        range(1, len(run_record.trace_steps) + 1)
    )
    assert run_record.trace_steps[0].kind is RunTraceStepKind.RUN_STARTED
    assert run_record.trace_steps[-1].kind is RunTraceStepKind.RUN_COMPLETED
    lane_steps = tuple(
        step for step in run_record.trace_steps if step.kind is RunTraceStepKind.LANE_ASSIGNED
    )
    assert tuple(step.lane for step in lane_steps) == tuple(SpecialistLane)
    assert all(
        step.evidence_ids or step.calculation_outputs or step.escalation_required
        for step in lane_steps
    )
    underwriting_step = next(
        step for step in lane_steps if step.lane is SpecialistLane.UNDERWRITING_ANALYST
    )
    assert underwriting_step.calculation_outputs == ("max_units=2",)
    assert run_record.status is AgentRunStatus.REQUIRES_REVIEW


def test_agent_run_runtime_blocks_synthesis_without_lookup_evidence() -> None:
    # Given: a run request with an open trust-critical question and no evidence.
    request = AgentRunRequest(
        run_id=RunId("run_agent_missing_evidence"),
        context_request=ContextBuildRequest(
            workspace_id="ws_agent",
            objective="Assess development capacity.",
            open_questions=("Retrieve the official parcel and zoning evidence first.",),
        ),
    )

    # When: the run runtime creates the initial plan.
    run_record = AgentRunRuntime().start_run(request)

    # Then: synthesis is blocked and the trace records the required escalation.
    assert run_record.status is AgentRunStatus.REQUIRES_REVIEW
    assert run_record.evidence_ids == ()
    assert run_record.plan.ready_for_synthesis is False
    assert any(
        step.kind is RunTraceStepKind.ESCALATION_RECORDED
        and "official parcel and zoning evidence" in step.summary
        for step in run_record.trace_steps
    )
    lead_step = next(
        step
        for step in run_record.trace_steps
        if step.lane is SpecialistLane.LEAD_DEVELOPER_CONSULTANT
    )
    assert lead_step.escalation_required is True
