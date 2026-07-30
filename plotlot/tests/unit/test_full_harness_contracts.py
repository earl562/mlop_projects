from __future__ import annotations

from datetime import datetime, timezone

import pytest

from plotlot.harness.contracts import (
    ApplicabilityScope,
    ApplicabilityStatus,
    Claim,
    ClaimFreshnessStatus,
    ClaimId,
    ClaimKind,
    ClaimOrigin,
    ClaimStatus,
    CountyName,
    EvidenceId,
    EvidenceItem,
    EvidenceSourceType,
    ExecutionMode,
    FreshnessStatus,
    GISProvider,
    PlotLotEvent,
    PlotLotEventSource,
    PlotLotEventType,
    RunId,
    RunStatus,
    Report,
    ReportId,
    ReportStatus,
    ReportType,
    ScaffoldComponentType,
    ScaffoldFile,
    ScaffoldFileStatus,
    ScaffoldManifest,
    SourceCatalogEntry,
    SourceLane,
    SourceMode,
    transition_run_status,
)
from plotlot.harness.verification import verify_report_traceability
from plotlot.harness.contracts.run_state import InvalidRunTransitionError


def test_plotlot_event_round_trips_with_typed_envelope() -> None:
    # Given: a typed run-created event with an explicit UTC timestamp.
    created_at = datetime(2026, 6, 27, tzinfo=timezone.utc)

    # When: the event is parsed through the contract boundary.
    event = PlotLotEvent(
        run_id=RunId("run_fixture_001"),
        sequence=1,
        type=PlotLotEventType.RUN_CREATED,
        source=PlotLotEventSource.HARNESS,
        payload={"goal": "fixture acquisition memo"},
        source_mode=SourceMode.FIXTURE,
        execution_mode=ExecutionMode.LOCAL,
        created_at=created_at,
    )

    # Then: the JSON shape is stable for API, CLI, TUI, and replay consumers.
    dumped = event.model_dump(mode="json")
    assert dumped["type"] == "run.created"
    assert dumped["run_id"] == "run_fixture_001"
    assert dumped["source_mode"] == "fixture"
    assert dumped["execution_mode"] == "local"


def test_analysis_run_state_machine_rejects_invalid_transition() -> None:
    # Given: a queued run.
    current = RunStatus.QUEUED

    # When / Then: skipping directly to completed fails loudly.
    with pytest.raises(InvalidRunTransitionError) as exc:
        transition_run_status(current, RunStatus.COMPLETED)

    assert exc.value.current is RunStatus.QUEUED
    assert exc.value.target is RunStatus.COMPLETED


def test_analysis_run_state_machine_allows_verification_path() -> None:
    # Given: a running analysis run.
    current = RunStatus.RUNNING

    # When: the run enters verification.
    result = transition_run_status(current, RunStatus.VERIFYING)

    # Then: the transition result is typed and replayable.
    assert result.previous is RunStatus.RUNNING
    assert result.current is RunStatus.VERIFYING


def test_source_catalog_entry_preserves_gis_applicability_metadata() -> None:
    # Given: a Broward BMSD zoning source catalog entry.
    entry = SourceCatalogEntry(
        source_id="src_broward_bmsd_zoning",
        lane=SourceLane.SOUTH_FLORIDA_GIS,
        provider=GISProvider.BROWARD_GEOHUB,
        source_type="zoning_boundary",
        jurisdiction="Broward County",
        county=CountyName("Broward"),
        municipality=None,
        dataset_name="BMSD Zoning",
        layer_name="Zoning",
        source_url="https://geohub-bcgis.opendata.arcgis.com/",
        feature_service_url="https://services.arcgis.com/broward/FeatureServer/0",
        applicability_scope=ApplicabilityScope.BMSD,
        metadata={"scope": "unincorporated_or_bmsd"},
    )

    # When / Then: structured catalog metadata survives JSON serialization.
    dumped = entry.model_dump(mode="json")
    assert dumped["lane"] == "south_florida_gis"
    assert dumped["provider"] == "broward_geohub"
    assert dumped["county"] == "Broward"
    assert dumped["metadata"]["scope"] == "unincorporated_or_bmsd"


def test_report_contract_links_claims_to_evidence() -> None:
    # Given: a claim backed by fixture GIS evidence.
    run_id = RunId("run_fixture_report_contract")
    report_id = ReportId("report_run_fixture_report_contract")
    evidence_id = EvidenceId("ev_run_fixture_report_contract_gis")
    claim = Claim(
        claim_id=ClaimId("claim_run_fixture_report_contract_source"),
        run_id=run_id,
        report_id=report_id,
        claim_text="Fixture zoning evidence requires municipal verification.",
        claim_type="official_verification_caveat",
        field_key="zoning.official_verification_required",
        kind=ClaimKind.HYPOTHESIS,
        origin=ClaimOrigin.LOCAL_AUTHORITY,
        status=ClaimStatus.NEEDS_VERIFICATION,
        confidence=0.5,
        evidence_ids=[evidence_id],
        source_url="https://library.municode.com/fl",
        next_verification_step="Confirm effective municipal code with the planning department.",
        claim_freshness=ClaimFreshnessStatus.REQUIRES_OFFICIAL_VERIFICATION,
        source_mode=SourceMode.FIXTURE,
    )

    # When: a preliminary report is serialized for API/CLI consumers.
    report = Report(
        report_id=report_id,
        run_id=run_id,
        report_type=ReportType.ZONING_RESEARCH_MEMO,
        title="Preliminary Zoning Research Memo",
        status=ReportStatus.PRELIMINARY,
        claims=[claim.claim_id],
        evidence_ids=[evidence_id],
        source_mode=SourceMode.FIXTURE,
    )

    # Then: the traceability identifiers survive JSON serialization.
    dumped = report.model_dump(mode="json")
    assert dumped["claims"] == ["claim_run_fixture_report_contract_source"]
    assert dumped["evidence_ids"] == ["ev_run_fixture_report_contract_gis"]
    assert dumped["status"] == "preliminary"
    claim_dump = claim.model_dump(mode="json")
    assert claim_dump["kind"] == "hypothesis"
    assert claim_dump["origin"] == "local_authority"
    assert claim_dump["claim_freshness"] == "requires_official_verification"


def test_verifier_rejects_authority_claim_without_source_boundary_metadata() -> None:
    run_id = RunId("run_fixture_claim_boundary")
    report_id = ReportId("report_run_fixture_claim_boundary")
    evidence_id = EvidenceId("ev_run_fixture_claim_boundary_gis")
    claim = Claim(
        claim_id=ClaimId("claim_run_fixture_claim_boundary_zoning"),
        run_id=run_id,
        report_id=report_id,
        claim_text="The site is zoned T5.",
        claim_type="zoning_district",
        field_key="zoning.district",
        kind=ClaimKind.VERIFIED_FACT,
        origin=ClaimOrigin.LOCAL_AUTHORITY,
        status=ClaimStatus.SUPPORTED,
        confidence=0.8,
        evidence_ids=[evidence_id],
        claim_freshness=ClaimFreshnessStatus.UNKNOWN,
        source_mode=SourceMode.FIXTURE,
    )
    evidence = EvidenceItem(
        evidence_id=evidence_id,
        run_id=run_id,
        source_type=EvidenceSourceType.GIS_LAYER,
        source_name="Fixture zoning layer",
        source_url="https://example.test/zoning",
        provider=GISProvider.MIAMI_DADE_ARCGIS,
        jurisdiction="Miami",
        county=CountyName("Miami-Dade"),
        municipality="Miami",
        freshness_status=FreshnessStatus.FIXTURE,
        applicability=ApplicabilityStatus.DIRECT,
        confidence=0.5,
        source_mode=SourceMode.FIXTURE,
    )
    report = Report(
        report_id=report_id,
        run_id=run_id,
        report_type=ReportType.ZONING_RESEARCH_MEMO,
        title="Preliminary Zoning Research Memo",
        status=ReportStatus.PRELIMINARY,
        claims=[claim.claim_id],
        evidence_ids=[evidence_id],
        source_mode=SourceMode.FIXTURE,
    )

    verification = verify_report_traceability(report, [claim], [evidence])

    assert verification.unsupported_claims == [str(claim.claim_id)]
    assert verification.checks["claim_evidence"] == "failed"
    assert verification.checks["claim_source_boundary"] == "failed"


def test_scaffold_manifest_contract_preserves_generated_file_statuses() -> None:
    manifest = ScaffoldManifest(
        scaffold_id="scaffold_fixture",
        component_type=ScaffoldComponentType.TOOL,
        name="demo_tool",
        target_root="/tmp/plotlot-scaffold",
        files=[
            ScaffoldFile(
                path="src/plotlot/harness/generated_tools/demo_tool/handler.py",
                kind="tool_handler",
                status=ScaffoldFileStatus.CREATED,
            )
        ],
    )
    dumped = manifest.model_dump(mode="json")
    assert dumped["component_type"] == "tool"
    assert dumped["files"][0]["status"] == "created"
    assert PlotLotEventType.SCAFFOLD_COMPLETED == "scaffold.completed"


def test_verify_report_traceability_warns_when_comp_support_is_weak() -> None:
    from plotlot.harness.contracts import ReportStatus, ReportType, SourceMode

    report = Report(
        report_id=ReportId("report_live_comp_warning"),
        run_id=RunId("run_live_comp_warning"),
        report_type=ReportType.ACQUISITION_MEMO,
        title="Preliminary Acquisition Memo",
        status=ReportStatus.PRELIMINARY,
        sections=[
            {
                "section_id": "underwriting_summary",
                "comp_support_summary": {
                    "status": "warning",
                    "reason": "live market support is too weak for a confident offer recommendation",
                },
            }
        ],
        source_mode=SourceMode.LIVE,
    )

    verification = verify_report_traceability(report, [], [])

    assert verification.status == "passed_with_warnings"
    assert verification.checks["comp_support"] == "warning"


def test_verify_report_traceability_warns_when_comping_blocks_underwriting() -> None:
    report = Report(
        report_id=ReportId("report_live_comping_blocked"),
        run_id=RunId("run_live_comping_blocked"),
        report_type=ReportType.ACQUISITION_MEMO,
        title="Preliminary Acquisition Memo",
        status=ReportStatus.PRELIMINARY,
        sections=[
            {
                "section_id": "underwriting_summary",
                "comp_support_summary": {
                    "status": "warning",
                    "reason": "market signal depends on contextual public listing evidence",
                    "comping_underwriting_status": "blocked_pending_county_reconciliation",
                    "comping_underwriting_blocker": (
                        "public listing comps require county-record reconciliation before confident underwriting"
                    ),
                },
            }
        ],
        source_mode=SourceMode.LIVE,
    )

    verification = verify_report_traceability(report, [], [])

    assert verification.status == "passed_with_warnings"
    assert verification.checks["comping_underwriting_gate"] == "warning"
