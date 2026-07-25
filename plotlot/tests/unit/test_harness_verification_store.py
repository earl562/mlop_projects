from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch

from plotlot.api.main import app
from plotlot.cli_harness import main
from plotlot.harness.contracts import (
    ApplicabilityStatus,
    Claim,
    ClaimFreshnessStatus,
    ClaimId,
    ClaimKind,
    ClaimOrigin,
    ClaimStatus,
    EvidenceId,
    EvidenceItem,
    EvidenceSourceType,
    FreshnessStatus,
    Report,
    ReportId,
    ReportStatus,
    ReportType,
    RunId,
    SourceMode,
    VerificationId,
    VerificationResult,
    VerificationStatus,
)
from plotlot.harness.report_finalization import ReportFinalizationBlockedError, finalize_report
from plotlot.harness.evidence_store import LocalEvidenceLedger
from plotlot.harness.fixture_runs import FixtureDealRunRequest, run_fixture_deal_analysis
from plotlot.harness.report_store import LocalReportLedger, default_report_ledger_path
from plotlot.harness.run_persistence import FixtureRunPersistenceStores, persist_fixture_run_result
from plotlot.harness.run_store import LocalHarnessRunStore
from plotlot.harness.verification import verify_report_traceability
from plotlot.harness.verification_store import LocalVerificationLedger, default_verification_ledger_path


@pytest.fixture(autouse=True)
def harness_store_path(tmp_path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("PLOTLOT_HARNESS_STORE_PATH", str(tmp_path / "harness-runs.json"))
    monkeypatch.setenv("PLOTLOT_HARNESS_JOB_STORE_PATH", str(tmp_path / "harness-jobs.json"))
    monkeypatch.setenv(
        "PLOTLOT_HARNESS_CALCULATION_STORE_PATH",
        str(tmp_path / "harness-calculations.json"),
    )
    monkeypatch.setenv("PLOTLOT_HARNESS_EVIDENCE_STORE_PATH", str(tmp_path / "harness-evidence.json"))
    monkeypatch.setenv("PLOTLOT_HARNESS_REPORT_STORE_PATH", str(tmp_path / "harness-reports.json"))
    monkeypatch.setenv(
        "PLOTLOT_HARNESS_VERIFICATION_STORE_PATH",
        str(tmp_path / "harness-verifications.json"),
    )


@pytest.fixture
def transport() -> ASGITransport:
    return ASGITransport(app=app)


@pytest.fixture
async def client(transport: ASGITransport):
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _save_live_report_with_weak_comp_support() -> tuple[ReportId, VerificationId]:
    report_id = ReportId("report_live_comp_support_warning")
    report = Report(
        report_id=report_id,
        run_id=RunId("run_live_comp_support_warning"),
        report_type=ReportType.ACQUISITION_MEMO,
        title="Preliminary Acquisition Memo",
        status=ReportStatus.PRELIMINARY,
        sections=[
            {
                "section_id": "underwriting_summary",
                "comp_support_summary": {
                    "status": "warning",
                    "reason": "offer guidance depends on county-reconciled public listing support rather than direct land comps",
                },
            }
        ],
        source_mode=SourceMode.LIVE,
    )
    verification = VerificationResult(
        verification_id=VerificationId("verification_report_live_comp_support_warning"),
        run_id=report.run_id,
        report_id=report_id,
        status=VerificationStatus.PASSED,
        checks={
            "claim_evidence": "passed",
            "claim_source_boundary": "passed",
            "source_mode": "passed",
            "freshness": "passed",
            "underwriting_basis": "passed",
            "comp_support": "warning",
        },
    )
    LocalReportLedger(default_report_ledger_path()).save_report(report)
    LocalVerificationLedger(default_verification_ledger_path()).save_verification(verification)
    return report_id, verification.verification_id


def _save_live_report_with_comping_gate_warning() -> tuple[ReportId, VerificationId]:
    report_id = ReportId("report_live_comping_gate_warning")
    report = Report(
        report_id=report_id,
        run_id=RunId("run_live_comping_gate_warning"),
        report_type=ReportType.ACQUISITION_MEMO,
        title="Preliminary Acquisition Memo",
        status=ReportStatus.PRELIMINARY,
        sections=[
            {
                "section_id": "underwriting_summary",
                "comp_support_summary": {
                    "status": "passed",
                    "reason": "direct land comps or county-reconciled support available",
                    "comping_underwriting_status": "blocked_pending_county_reconciliation",
                    "comping_underwriting_blocker": (
                        "public listing comps require county-record reconciliation before confident underwriting"
                    ),
                },
            }
        ],
        source_mode=SourceMode.LIVE,
    )
    verification = VerificationResult(
        verification_id=VerificationId("verification_report_live_comping_gate_warning"),
        run_id=report.run_id,
        report_id=report_id,
        status=VerificationStatus.PASSED_WITH_WARNINGS,
        checks={
            "claim_evidence": "passed",
            "claim_source_boundary": "passed",
            "source_mode": "passed",
            "freshness": "passed",
            "underwriting_basis": "passed",
            "comping_underwriting_gate": "warning",
            "comp_support": "passed",
            "comp_provenance": "passed",
            "exit_market_support": "passed",
            "zoning_official_support": "passed",
        },
    )
    LocalReportLedger(default_report_ledger_path()).save_report(report)
    LocalVerificationLedger(default_verification_ledger_path()).save_verification(verification)
    return report_id, verification.verification_id


def _save_live_report_ready_for_finalization() -> tuple[ReportId, VerificationId]:
    report_id = ReportId("report_live_ready_for_finalization")
    report = Report(
        report_id=report_id,
        run_id=RunId("run_live_ready_for_finalization"),
        report_type=ReportType.ACQUISITION_MEMO,
        title="Verified Acquisition Memo",
        status=ReportStatus.PRELIMINARY,
        sections=[
            {
                "section_id": "underwriting_summary",
                "comp_support_summary": {
                    "status": "passed",
                    "reason": "direct land comps or county-reconciled support available",
                    "comping_underwriting_status": "available_to_underwriting",
                    "comping_underwriting_blocker": "",
                },
            }
        ],
        source_mode=SourceMode.LIVE,
    )
    verification = VerificationResult(
        verification_id=VerificationId("verification_report_live_ready_for_finalization"),
        run_id=report.run_id,
        report_id=report_id,
        status=VerificationStatus.PASSED,
        checks={
            "claim_evidence": "passed",
            "claim_source_boundary": "passed",
            "source_mode": "passed",
            "freshness": "passed",
            "underwriting_basis": "passed",
            "comping_underwriting_gate": "passed",
            "comp_support": "passed",
            "comp_provenance": "passed",
            "exit_market_support": "passed",
            "zoning_official_support": "passed",
        },
    )
    LocalReportLedger(default_report_ledger_path()).save_report(report)
    LocalVerificationLedger(default_verification_ledger_path()).save_verification(verification)
    return report_id, verification.verification_id


def _save_live_report_with_exit_only_support_tier() -> tuple[ReportId, VerificationId]:
    report_id = ReportId("report_live_exit_only_support")
    report = Report(
        report_id=report_id,
        run_id=RunId("run_live_exit_only_support"),
        report_type=ReportType.ACQUISITION_MEMO,
        title="Preliminary Acquisition Memo",
        status=ReportStatus.PRELIMINARY,
        sections=[
            {
                "section_id": "underwriting_summary",
                "comp_support_summary": {
                    "status": "passed",
                    "reason": "direct land comps or county-reconciled support available",
                    "combined_support_tier": "exit_only",
                },
            }
        ],
        source_mode=SourceMode.LIVE,
    )
    verification = VerificationResult(
        verification_id=VerificationId("verification_report_live_exit_only_support"),
        run_id=report.run_id,
        report_id=report_id,
        status=VerificationStatus.PASSED,
        checks={
            "claim_evidence": "passed",
            "claim_source_boundary": "passed",
            "source_mode": "passed",
            "freshness": "passed",
            "underwriting_basis": "passed",
            "comp_support": "warning",
        },
    )
    LocalReportLedger(default_report_ledger_path()).save_report(report)
    LocalVerificationLedger(default_verification_ledger_path()).save_verification(verification)
    return report_id, verification.verification_id


def _save_live_report_with_contextual_zoning_warning() -> tuple[ReportId, VerificationId]:
    report_id = ReportId("report_live_contextual_zoning_warning")
    report = Report(
        report_id=report_id,
        run_id=RunId("run_live_contextual_zoning_warning"),
        report_type=ReportType.ZONING_RESEARCH_MEMO,
        title="Preliminary Zoning Research Memo",
        status=ReportStatus.PRELIMINARY,
        sections=[
            {
                "section_id": "underwriting_summary",
                "comp_support_summary": {
                    "status": "passed",
                    "reason": "comp support not required for zoning memo",
                    "combined_support_tier": "balanced",
                },
            }
        ],
        source_mode=SourceMode.LIVE,
    )
    verification = VerificationResult(
        verification_id=VerificationId("verification_report_live_contextual_zoning_warning"),
        run_id=report.run_id,
        report_id=report_id,
        status=VerificationStatus.PASSED_WITH_WARNINGS,
        checks={
            "claim_evidence": "passed",
            "claim_source_boundary": "passed",
            "source_mode": "passed",
            "freshness": "passed",
            "underwriting_basis": "passed",
            "comp_support": "passed",
            "jurisdiction_alignment": "warning",
        },
        jurisdiction_mismatches=["claim_broward_contextual_zoning"],
    )
    LocalReportLedger(default_report_ledger_path()).save_report(report)
    LocalVerificationLedger(default_verification_ledger_path()).save_verification(verification)
    return report_id, verification.verification_id


def test_verify_report_traceability_flags_exit_only_support_tier_as_warning() -> None:
    report = Report(
        report_id=ReportId("report_live_exit_only_support_traceability"),
        run_id=RunId("run_live_exit_only_support_traceability"),
        report_type=ReportType.ACQUISITION_MEMO,
        title="Preliminary Acquisition Memo",
        status=ReportStatus.PRELIMINARY,
        sections=[
            {
                "section_id": "underwriting_summary",
                "comp_support_summary": {
                    "status": "passed",
                    "reason": "direct land comps or county-reconciled support available",
                    "combined_support_tier": "exit_only",
                },
            }
        ],
        source_mode=SourceMode.LIVE,
    )

    verification = verify_report_traceability(report, claims=[], evidence_items=[])

    assert verification.status is VerificationStatus.PASSED_WITH_WARNINGS
    assert verification.checks["comp_support"] == "warning"


def test_verify_report_traceability_warns_when_zoning_claim_relies_on_contextual_gis() -> None:
    run_id = RunId("run_broward_contextual_zoning")
    report = Report(
        report_id=ReportId("report_broward_contextual_zoning"),
        run_id=run_id,
        report_type=ReportType.ACQUISITION_MEMO,
        title="Preliminary Acquisition Memo",
        status=ReportStatus.PRELIMINARY,
        source_mode=SourceMode.LIVE,
    )
    claim = Claim(
        claim_id=ClaimId("claim_broward_contextual_zoning"),
        run_id=run_id,
        report_id=report.report_id,
        claim_text="Fort Lauderdale zoning must be confirmed against the controlling municipal code.",
        claim_type="zoning_code",
        field_key="zoning.current_district",
        kind=ClaimKind.HYPOTHESIS,
        origin=ClaimOrigin.LOCAL_AUTHORITY,
        status=ClaimStatus.PRELIMINARY,
        confidence=0.7,
        evidence_ids=[EvidenceId("ev_broward_contextual_gis")],
        source_url="https://plotlot.local/south-florida-gis-site-context",
        claim_freshness=ClaimFreshnessStatus.REQUIRES_OFFICIAL_VERIFICATION,
        next_verification_step="Confirm the Fort Lauderdale municipal zoning code section.",
        source_mode=SourceMode.LIVE,
    )
    evidence = EvidenceItem(
        evidence_id=EvidenceId("ev_broward_contextual_gis"),
        run_id=run_id,
        source_type=EvidenceSourceType.GIS_LAYER,
        source_name="South Florida GIS site context",
        source_url="https://plotlot.local/south-florida-gis-site-context",
        provider="south_florida_gis",
        jurisdiction="Fort Lauderdale",
        county="Broward",
        municipality="Fort Lauderdale",
        freshness_status=FreshnessStatus.FRESH,
        applicability=ApplicabilityStatus.REQUIRES_MUNICIPAL_VERIFICATION,
        confidence=0.8,
        source_mode=SourceMode.LIVE,
    )

    verification = verify_report_traceability(report, claims=[claim], evidence_items=[evidence])

    assert verification.status is VerificationStatus.PASSED_WITH_WARNINGS
    assert verification.checks["jurisdiction_alignment"] == "warning"
    assert verification.jurisdiction_mismatches == [str(claim.claim_id)]


def test_fixture_run_persistence_saves_blocking_verification(tmp_path) -> None:
    # Given: a fixture run result and isolated local ledgers.
    result = run_fixture_deal_analysis(
        FixtureDealRunRequest(
            address="example Miami-Dade fixture address",
            analysis_type="acquisition_memo",
        )
    )
    verification_ledger = LocalVerificationLedger(tmp_path / "verifications.json")

    # When: fixture persistence writes the report traceability bundle.
    persist_fixture_run_result(
        result,
        FixtureRunPersistenceStores(
            run_store=LocalHarnessRunStore(tmp_path / "runs.json"),
            evidence_ledger=LocalEvidenceLedger(tmp_path / "evidence.json"),
            report_ledger=LocalReportLedger(tmp_path / "reports.json"),
            verification_ledger=verification_ledger,
        ),
    )

    # Then: fixture evidence blocks report finalization while preserving checklist details.
    verification = verification_ledger.get_latest_for_report(ReportId(result.report_id))
    assert verification.status is VerificationStatus.BLOCKED
    assert verification.mock_or_fixture_blockers == result.evidence_ids
    assert verification.checks["claim_evidence"] == "passed"


def test_cli_report_finalize_is_blocked_for_fixture_evidence(capsys) -> None:
    # Given: a persisted fixture acquisition memo report.
    run_exit = main(
        [
            "run",
            "acquisition-memo",
            "--address",
            "example Miami-Dade fixture address",
            "--source-mode",
            "fixture",
        ]
    )
    run_payload = json.loads(capsys.readouterr().out)

    # When: the CLI attempts to finalize that report.
    verify_exit = main(["verification", "show", "--report-id", run_payload["report_id"]])
    verification = json.loads(capsys.readouterr().out)
    finalize_exit = main(["reports", "finalize", run_payload["report_id"]])
    finalized = json.loads(capsys.readouterr().out)

    # Then: finalization fails loudly and cites the verification blocker.
    assert run_exit == 0
    assert verify_exit == 0
    assert finalize_exit == 1
    assert verification["status"] == "blocked"
    assert verification["comp_support_snapshot"]["status"] == "passed"
    assert verification["comp_support_snapshot"]["combined_support_tier"] != "unknown"
    assert finalized["error"] == "report_finalization_blocked"
    assert finalized["verification_id"] == verification["verification_id"]


@pytest.mark.asyncio
async def test_api_report_finalize_is_blocked_for_fixture_evidence(client: AsyncClient) -> None:
    # Given: a persisted fixture acquisition memo report through the API.
    create_response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "example Miami-Dade fixture address",
            "analysis_type": "acquisition_memo",
            "source_mode": "fixture",
        },
    )
    run_payload = create_response.json()

    # When: verification is inspected and finalization is requested.
    verification_response = await client.get(
        f"/api/v1/harness/runs/{run_payload['run_id']}/verification"
    )
    finalize_response = await client.post(f"/api/v1/reports/{run_payload['report_id']}/finalize")

    # Then: the API exposes the verifier result and blocks finalization with conflict status.
    assert create_response.status_code == 200
    assert verification_response.status_code == 200
    assert finalize_response.status_code == 409
    assert verification_response.json()["status"] == "blocked"
    assert finalize_response.json()["detail"]["error"] == "report_finalization_blocked"


def test_direct_report_finalize_is_blocked_for_weak_live_comp_support() -> None:
    report_id, verification_id = _save_live_report_with_weak_comp_support()

    with pytest.raises(ReportFinalizationBlockedError) as exc_info:
        finalize_report(
            report_id,
            report_ledger=LocalReportLedger(default_report_ledger_path()),
            verification_ledger=LocalVerificationLedger(default_verification_ledger_path()),
        )

    assert exc_info.value.reason == "weak_comp_support"
    assert exc_info.value.verification is not None
    assert exc_info.value.verification.verification_id == verification_id


def test_direct_report_finalize_is_blocked_for_comping_underwriting_gate() -> None:
    report_id, verification_id = _save_live_report_with_comping_gate_warning()

    with pytest.raises(ReportFinalizationBlockedError) as exc_info:
        finalize_report(
            report_id,
            report_ledger=LocalReportLedger(default_report_ledger_path()),
            verification_ledger=LocalVerificationLedger(default_verification_ledger_path()),
        )

    assert exc_info.value.reason == "comping_underwriting_not_ready"
    assert exc_info.value.verification is not None
    assert exc_info.value.verification.verification_id == verification_id


def test_direct_report_finalize_passes_when_comping_underwriting_gate_is_clear() -> None:
    report_id, _verification_id = _save_live_report_ready_for_finalization()

    finalized = finalize_report(
        report_id,
        report_ledger=LocalReportLedger(default_report_ledger_path()),
        verification_ledger=LocalVerificationLedger(default_verification_ledger_path()),
    )

    assert finalized.status is ReportStatus.FINAL
    assert finalized.finalized_at is not None


def test_cli_report_finalize_is_blocked_for_weak_live_comp_support(capsys) -> None:
    report_id, verification_id = _save_live_report_with_weak_comp_support()

    finalize_exit = main(["reports", "finalize", str(report_id)])
    finalized = json.loads(capsys.readouterr().out)

    assert finalize_exit == 1
    assert finalized["error"] == "report_finalization_blocked"
    assert finalized["reason"] == "weak_comp_support"
    assert finalized["verification_id"] == str(verification_id)


def test_cli_report_finalize_is_blocked_for_comping_underwriting_gate(capsys) -> None:
    report_id, verification_id = _save_live_report_with_comping_gate_warning()

    finalize_exit = main(["reports", "finalize", str(report_id)])
    finalized = json.loads(capsys.readouterr().out)

    assert finalize_exit == 1
    assert finalized["error"] == "report_finalization_blocked"
    assert finalized["reason"] == "comping_underwriting_not_ready"
    assert finalized["verification_id"] == str(verification_id)


def test_cli_verification_show_surfaces_exit_only_comp_support_snapshot(capsys) -> None:
    report_id, verification_id = _save_live_report_with_exit_only_support_tier()

    verify_exit = main(["verification", "show", "--report-id", str(report_id)])
    verification = json.loads(capsys.readouterr().out)

    assert verify_exit == 0
    assert verification["verification_id"] == str(verification_id)
    assert verification["comp_support_snapshot"]["status"] == "passed"
    assert verification["comp_support_snapshot"]["combined_support_tier"] == "exit_only"


def test_cli_verification_show_surfaces_jurisdiction_alignment_warning(capsys) -> None:
    report_id, verification_id = _save_live_report_with_contextual_zoning_warning()

    verify_exit = main(["verification", "show", str(verification_id)])
    verification = json.loads(capsys.readouterr().out)

    assert verify_exit == 0
    assert verification["verification_id"] == str(verification_id)
    assert verification["warning_checks"] == ["jurisdiction_alignment"]
    assert verification["jurisdiction_alignment_status"] == "warning"
    assert verification["jurisdiction_mismatch_count"] == 1
    assert verification["comp_support_snapshot"]["report_id"] == str(report_id)


@pytest.mark.asyncio
async def test_api_report_finalize_is_blocked_for_weak_live_comp_support(
    client: AsyncClient,
) -> None:
    report_id, verification_id = _save_live_report_with_weak_comp_support()

    finalize_response = await client.post(f"/api/v1/reports/{report_id}/finalize")

    assert finalize_response.status_code == 409
    assert finalize_response.json()["detail"]["error"] == "report_finalization_blocked"
    assert finalize_response.json()["detail"]["reason"] == "weak_comp_support"
    assert finalize_response.json()["detail"]["verification_id"] == str(verification_id)


@pytest.mark.asyncio
async def test_api_report_finalize_is_blocked_for_comping_underwriting_gate(
    client: AsyncClient,
) -> None:
    report_id, verification_id = _save_live_report_with_comping_gate_warning()

    finalize_response = await client.post(f"/api/v1/reports/{report_id}/finalize")

    assert finalize_response.status_code == 409
    assert finalize_response.json()["detail"]["error"] == "report_finalization_blocked"
    assert finalize_response.json()["detail"]["reason"] == "comping_underwriting_not_ready"
    assert finalize_response.json()["detail"]["verification_id"] == str(verification_id)


@pytest.mark.asyncio
async def test_api_verification_endpoints_surface_jurisdiction_alignment_warning(
    client: AsyncClient,
) -> None:
    report_id, verification_id = _save_live_report_with_contextual_zoning_warning()

    verification_response = await client.get(f"/api/v1/verification/{verification_id}")
    report_response = await client.get(f"/api/v1/reports/{report_id}/verification")

    assert verification_response.status_code == 200
    assert report_response.status_code == 200
    assert verification_response.json()["jurisdiction_alignment_status"] == "warning"
    assert verification_response.json()["jurisdiction_mismatch_count"] == 1
    assert verification_response.json()["warning_checks"] == ["jurisdiction_alignment"]
    assert report_response.json()["comp_support_snapshot"]["report_id"] == str(report_id)


def test_direct_report_finalize_is_blocked_for_exit_only_support_tier() -> None:
    report_id, verification_id = _save_live_report_with_exit_only_support_tier()

    with pytest.raises(ReportFinalizationBlockedError) as exc_info:
        finalize_report(
            report_id,
            report_ledger=LocalReportLedger(default_report_ledger_path()),
            verification_ledger=LocalVerificationLedger(default_verification_ledger_path()),
        )

    assert exc_info.value.reason == "weak_comp_support"
    assert exc_info.value.verification is not None
    assert exc_info.value.verification.verification_id == verification_id
