from __future__ import annotations

from plotlot.core.lookup_snapshot import (
    ContradictionStatus,
    EvidenceId,
    FieldKey,
    FieldQuality,
    FreshnessStatus,
    LookupField,
    LookupFieldSpec,
    LookupSnapshot,
    LookupSnapshotId,
    RunId,
    SiteId,
)
from plotlot.harness import (
    ContextBroker,
    ContextBuildRequest,
    HarnessPlanner,
    SpecialistLane,
)
from plotlot.pipeline.lookup_snapshot import build_lookup_snapshot
from tests.unit.lookup_snapshot_repository_fixtures import report


def test_harness_planner_assigns_required_specialist_lanes_from_lookup_context() -> None:
    # Given: an evidence-backed lookup context packet for an agent run.
    snapshot = build_lookup_snapshot(report(with_density_analysis=True))
    context_packet = ContextBroker().build_packet(
        ContextBuildRequest(
            workspace_id="ws_test",
            project_id="project_test",
            objective="Find verified by-right development capacity.",
            lookup_snapshot=snapshot,
        )
    )

    # When: the planner decomposes the run before synthesis.
    plan = HarnessPlanner().plan(context_packet)

    # Then: every required specialist lane has evidence-bound work.
    assert tuple(assignment.lane for assignment in plan.assignments) == tuple(SpecialistLane)
    assert plan.evidence_ids == context_packet.evidence_ids
    parcel_lane = plan.assignment_for(SpecialistLane.PARCEL_ANALYST)
    zoning_lane = plan.assignment_for(SpecialistLane.ZONING_CODE_ANALYST)
    underwriting_lane = plan.assignment_for(SpecialistLane.UNDERWRITING_ANALYST)
    evidence_lane = plan.assignment_for(SpecialistLane.EVIDENCE_REVIEWER)
    assert FieldKey("parcel.apn") in parcel_lane.field_keys
    assert FieldKey("zoning.district") in zoning_lane.field_keys
    assert underwriting_lane.calculation_outputs == ("max_units=2",)
    assert evidence_lane.evidence_ids == context_packet.evidence_ids
    assert all(
        assignment.evidence_ids or assignment.calculation_outputs for assignment in plan.assignments
    )


def test_harness_planner_escalates_unresolved_lookup_context_before_synthesis() -> None:
    # Given: a context packet with unknown and contradicted lookup facts.
    unknown_height = LookupField.from_quality(
        LookupFieldSpec(
            key=FieldKey("standards.height"),
            label="Maximum height",
            value=None,
            unit="ft",
            evidence_ids=(),
            source_priority=("official_ordinance_table",),
            fallback_sources=("adopted_planning_pdf",),
        ),
        FieldQuality(
            accepted_authority=True,
            freshness=FreshnessStatus.CURRENT,
            units_normalized=True,
            parser_confidence=0.95,
            contradiction_status=ContradictionStatus.CLEAR,
        ),
    )
    contradicted_district = LookupField.from_quality(
        LookupFieldSpec(
            key=FieldKey("zoning.district"),
            label="Zoning district",
            value="RM-2",
            unit="",
            evidence_ids=(EvidenceId("ev_map"), EvidenceId("ev_parcel")),
            source_priority=("official_zoning_map",),
            fallback_sources=("official_parcel_record",),
        ),
        FieldQuality(
            accepted_authority=True,
            freshness=FreshnessStatus.CURRENT,
            units_normalized=True,
            parser_confidence=0.99,
            contradiction_status=ContradictionStatus.BLOCKING,
        ),
    )
    context_packet = ContextBroker().build_packet(
        ContextBuildRequest(
            workspace_id="ws_test",
            objective="Assess zoning capacity.",
            lookup_snapshot=LookupSnapshot(
                lookup_snapshot_id=LookupSnapshotId("ls_planner_test"),
                site_id=SiteId("site_planner_test"),
                run_id=RunId("run_planner_test"),
                fields=(unknown_height, contradicted_district),
                calculations=(),
                warnings=(),
            ),
        )
    )

    # When: the planner builds lane assignments.
    plan = HarnessPlanner().plan(context_packet)

    # Then: synthesis is blocked until unresolved evidence is reviewed.
    lead_lane = plan.assignment_for(SpecialistLane.LEAD_DEVELOPER_CONSULTANT)
    assert plan.ready_for_synthesis is False
    assert lead_lane.escalation_required is True
    assert any(
        escalation.field_key == FieldKey("standards.height") for escalation in plan.escalations
    )
    assert any(
        escalation.field_key == FieldKey("zoning.district") for escalation in plan.escalations
    )
