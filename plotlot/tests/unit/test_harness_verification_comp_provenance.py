from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch

from plotlot.api.main import app
from plotlot.cli_harness import main
from plotlot.harness.contracts import (
    ApplicabilityStatus,
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
from plotlot.harness.report_store import LocalReportLedger, default_report_ledger_path
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


def _live_report(report_id: ReportId, run_id: RunId) -> Report:
    return Report(
        report_id=report_id,
        run_id=run_id,
        report_type=ReportType.ACQUISITION_MEMO,
        title="Preliminary Acquisition Memo",
        status=ReportStatus.PRELIMINARY,
        sections=[
            {
                "section_id": "underwriting_summary",
                "comp_support_summary": {
                    "status": "passed",
                    "reason": "live comp path available",
                    "combined_support_tier": "county_land_plus_exit",
                },
            }
        ],
        source_mode=SourceMode.LIVE,
    )


def _comp_evidence(
    *,
    run_id: RunId,
    evidence_id: str,
    provenance_tier: str,
    source_type: EvidenceSourceType = EvidenceSourceType.MARKET_COMP,
) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=EvidenceId(evidence_id),
        run_id=run_id,
        source_type=source_type,
        source_name="Comparable sale",
        source_url="https://www.zillow.com/homedetails/example-comp",
        provider="comp_source",
        jurisdiction="Miami Gardens",
        county="Miami-Dade",
        municipality="Miami Gardens",
        freshness_status=FreshnessStatus.FRESH,
        applicability=ApplicabilityStatus.CONTEXTUAL,
        confidence=0.8,
        source_mode=SourceMode.LIVE,
        metadata={"provenance_tier": provenance_tier},
    )


def _save_live_report_with_weak_comp_provenance() -> tuple[ReportId, VerificationId]:
    report_id = ReportId("report_live_weak_comp_provenance")
    run_id = RunId("run_live_weak_comp_provenance")
    report = _live_report(report_id, run_id)
    verification = VerificationResult(
        verification_id=VerificationId("verification_report_live_weak_comp_provenance"),
        run_id=run_id,
        report_id=report_id,
        status=VerificationStatus.PASSED_WITH_WARNINGS,
        checks={
            "claim_evidence": "passed",
            "claim_source_boundary": "passed",
            "source_mode": "passed",
            "freshness": "passed",
            "underwriting_basis": "passed",
            "comp_support": "passed",
            "comp_provenance": "warning",
        },
    )
    LocalReportLedger(default_report_ledger_path()).save_report(report)
    LocalVerificationLedger(default_verification_ledger_path()).save_verification(verification)
    return report_id, verification.verification_id


def test_verify_report_traceability_warns_when_live_comps_are_public_listing_only() -> None:
    report = _live_report(
        ReportId("report_live_public_listing_only"),
        RunId("run_live_public_listing_only"),
    )
    evidence_items = [
        _comp_evidence(
            run_id=report.run_id,
            evidence_id="ev_live_public_listing_comp",
            provenance_tier="public_listing_parsed",
        )
    ]

    verification = verify_report_traceability(report, claims=[], evidence_items=evidence_items)

    assert verification.status is VerificationStatus.PASSED_WITH_WARNINGS
    assert verification.checks["comp_provenance"] == "warning"


def test_verify_report_traceability_passes_when_live_land_comp_is_county_reconciled() -> None:
    report = _live_report(
        ReportId("report_live_county_reconciled_comp"),
        RunId("run_live_county_reconciled_comp"),
    )
    evidence_items = [
        _comp_evidence(
            run_id=report.run_id,
            evidence_id="ev_live_county_reconciled_comp",
            provenance_tier="public_listing_county_reconciled",
        )
    ]

    verification = verify_report_traceability(report, claims=[], evidence_items=evidence_items)

    assert verification.checks["comp_provenance"] == "passed"


def test_cli_verification_show_surfaces_comp_provenance_warning(capsys) -> None:
    _, verification_id = _save_live_report_with_weak_comp_provenance()

    verify_exit = main(["verification", "show", str(verification_id)])
    verification = json.loads(capsys.readouterr().out)

    assert verify_exit == 0
    assert verification["verification_id"] == str(verification_id)
    assert "comp_provenance" in verification["warning_checks"]


def test_cli_report_finalize_is_blocked_for_weak_comp_provenance(capsys) -> None:
    report_id, verification_id = _save_live_report_with_weak_comp_provenance()

    finalize_exit = main(["reports", "finalize", str(report_id)])
    finalized = json.loads(capsys.readouterr().out)

    assert finalize_exit == 1
    assert finalized["error"] == "report_finalization_blocked"
    assert finalized["reason"] == "weak_comp_provenance"
    assert finalized["verification_id"] == str(verification_id)


@pytest.mark.asyncio
async def test_api_report_finalize_is_blocked_for_weak_comp_provenance(
    client: AsyncClient,
) -> None:
    report_id, verification_id = _save_live_report_with_weak_comp_provenance()

    finalize_response = await client.post(f"/api/v1/reports/{report_id}/finalize")

    assert finalize_response.status_code == 409
    assert finalize_response.json()["detail"]["error"] == "report_finalization_blocked"
    assert finalize_response.json()["detail"]["reason"] == "weak_comp_provenance"
    assert finalize_response.json()["detail"]["verification_id"] == str(verification_id)


def test_direct_report_finalize_is_blocked_for_weak_comp_provenance() -> None:
    report_id, verification_id = _save_live_report_with_weak_comp_provenance()

    with pytest.raises(ReportFinalizationBlockedError) as exc_info:
        finalize_report(
            report_id,
            report_ledger=LocalReportLedger(default_report_ledger_path()),
            verification_ledger=LocalVerificationLedger(default_verification_ledger_path()),
        )

    assert exc_info.value.reason == "weak_comp_provenance"
    assert exc_info.value.verification is not None
    assert exc_info.value.verification.verification_id == verification_id
