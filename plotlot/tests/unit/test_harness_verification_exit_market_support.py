from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch

from plotlot.api.main import app
from plotlot.cli_harness import main
from plotlot.harness.contracts import (
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
from plotlot.harness.verification_store import (
    LocalVerificationLedger,
    default_verification_ledger_path,
)


@pytest.fixture(autouse=True)
def harness_store_path(tmp_path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("PLOTLOT_HARNESS_STORE_PATH", str(tmp_path / "harness-runs.json"))
    monkeypatch.setenv("PLOTLOT_HARNESS_JOB_STORE_PATH", str(tmp_path / "harness-jobs.json"))
    monkeypatch.setenv(
        "PLOTLOT_HARNESS_CALCULATION_STORE_PATH",
        str(tmp_path / "harness-calculations.json"),
    )
    monkeypatch.setenv(
        "PLOTLOT_HARNESS_EVIDENCE_STORE_PATH", str(tmp_path / "harness-evidence.json")
    )
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


def _weak_exit_market_support_report(
    *,
    report_id: ReportId,
    run_id: RunId,
) -> Report:
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
                    "reason": "direct land comps available",
                    "combined_support_tier": "balanced",
                    "exit_support_market_scope": "outside_subject_municipality",
                    "exit_support_sale_date": "2025-12-01",
                    "exit_support_recency_tier": "recent_12m",
                    "exit_support_quality_score": 0.58,
                    "exit_micro_market_confidence": "low",
                },
            }
        ],
        source_mode=SourceMode.LIVE,
    )


def _save_live_report_with_weak_exit_market_support() -> tuple[ReportId, VerificationId]:
    report_id = ReportId("report_live_weak_exit_market_support")
    report = _weak_exit_market_support_report(
        report_id=report_id,
        run_id=RunId("run_live_weak_exit_market_support"),
    )
    verification = VerificationResult(
        verification_id=VerificationId("verification_report_live_weak_exit_market_support"),
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
            "exit_market_support": "warning",
        },
    )
    LocalReportLedger(default_report_ledger_path()).save_report(report)
    LocalVerificationLedger(default_verification_ledger_path()).save_verification(verification)
    return report_id, verification.verification_id


def test_verify_report_traceability_warns_when_exit_comp_market_support_is_weak() -> None:
    report = _weak_exit_market_support_report(
        report_id=ReportId("report_live_weak_exit_market_support_traceability"),
        run_id=RunId("run_live_weak_exit_market_support_traceability"),
    )

    verification = verify_report_traceability(report, claims=[], evidence_items=[])

    assert verification.status is VerificationStatus.PASSED_WITH_WARNINGS
    assert verification.checks["exit_market_support"] == "warning"


def test_cli_verification_show_surfaces_exit_market_support_warning(capsys) -> None:
    report_id, verification_id = _save_live_report_with_weak_exit_market_support()

    verify_exit = main(["verification", "show", str(verification_id)])
    verification = json.loads(capsys.readouterr().out)

    assert verify_exit == 0
    assert verification["verification_id"] == str(verification_id)
    assert verification["warning_checks"] == ["exit_market_support"]
    assert verification["comp_support_snapshot"]["report_id"] == str(report_id)
    assert (
        verification["comp_support_snapshot"]["exit_support_market_scope"]
        == "outside_subject_municipality"
    )


def test_cli_report_finalize_is_blocked_for_weak_exit_market_support(capsys) -> None:
    report_id, verification_id = _save_live_report_with_weak_exit_market_support()

    finalize_exit = main(["reports", "finalize", str(report_id)])
    finalized = json.loads(capsys.readouterr().out)

    assert finalize_exit == 1
    assert finalized["error"] == "report_finalization_blocked"
    assert finalized["reason"] == "weak_exit_market_support"
    assert finalized["verification_id"] == str(verification_id)


@pytest.mark.asyncio
async def test_api_verification_endpoints_surface_exit_market_support_warning(
    client: AsyncClient,
) -> None:
    report_id, verification_id = _save_live_report_with_weak_exit_market_support()

    verification_response = await client.get(f"/api/v1/verification/{verification_id}")
    report_response = await client.get(f"/api/v1/reports/{report_id}/verification")

    assert verification_response.status_code == 200
    assert report_response.status_code == 200
    assert verification_response.json()["warning_checks"] == ["exit_market_support"]
    assert report_response.json()["comp_support_snapshot"]["exit_support_market_scope"] == (
        "outside_subject_municipality"
    )


@pytest.mark.asyncio
async def test_api_report_finalize_is_blocked_for_weak_exit_market_support(
    client: AsyncClient,
) -> None:
    report_id, verification_id = _save_live_report_with_weak_exit_market_support()

    finalize_response = await client.post(f"/api/v1/reports/{report_id}/finalize")

    assert finalize_response.status_code == 409
    assert finalize_response.json()["detail"]["error"] == "report_finalization_blocked"
    assert finalize_response.json()["detail"]["reason"] == "weak_exit_market_support"
    assert finalize_response.json()["detail"]["verification_id"] == str(verification_id)


def test_direct_report_finalize_is_blocked_for_weak_exit_market_support() -> None:
    report_id, verification_id = _save_live_report_with_weak_exit_market_support()

    with pytest.raises(ReportFinalizationBlockedError) as exc_info:
        finalize_report(
            report_id,
            report_ledger=LocalReportLedger(default_report_ledger_path()),
            verification_ledger=LocalVerificationLedger(default_verification_ledger_path()),
        )

    assert exc_info.value.reason == "weak_exit_market_support"
    assert exc_info.value.verification is not None
    assert exc_info.value.verification.verification_id == verification_id
