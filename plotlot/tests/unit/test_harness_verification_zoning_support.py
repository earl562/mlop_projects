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
from plotlot.harness.verification_store import LocalVerificationLedger, default_verification_ledger_path
from plotlot.harness.fixture_runs import _zoning_support_summary


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


def _weak_zoning_support_report(*, report_id: ReportId, run_id: RunId) -> Report:
    return Report(
        report_id=report_id,
        run_id=run_id,
        report_type=ReportType.ACQUISITION_MEMO,
        title="Preliminary Acquisition Memo",
        status=ReportStatus.PRELIMINARY,
        sections=[
            {
                "section_id": "underwriting_summary",
                "zoning_support_summary": {
                    "status": "warning",
                    "reason": "zoning support still depends on preliminary ordinance or staged municipal authority context",
                    "ordinance_rules_resolved": True,
                    "ordinance_source": "ordinance_search",
                    "requires_official_verification": True,
                    "authority_source_type": "municode_live_table",
                    "authority_resolution": "section_table_extract",
                    "authority_confidence": "official_live_preliminary_extract",
                    "authority_jurisdiction": "Miami Gardens, FL",
                    "authority_is_live": True,
                    "authority_is_official": True,
                    "gis_applicability": "requires_municipal_verification",
                },
            }
        ],
        source_mode=SourceMode.LIVE,
    )


def _save_live_report_with_weak_zoning_support() -> tuple[ReportId, VerificationId]:
    report_id = ReportId("report_live_weak_zoning_support")
    report = _weak_zoning_support_report(
        report_id=report_id,
        run_id=RunId("run_live_weak_zoning_support"),
    )
    verification = VerificationResult(
        verification_id=VerificationId("verification_report_live_weak_zoning_support"),
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
            "exit_market_support": "passed",
            "zoning_official_support": "warning",
        },
    )
    LocalReportLedger(default_report_ledger_path()).save_report(report)
    LocalVerificationLedger(default_verification_ledger_path()).save_verification(verification)
    return report_id, verification.verification_id


def test_verify_report_traceability_warns_when_zoning_support_is_not_official() -> None:
    report = _weak_zoning_support_report(
        report_id=ReportId("report_live_weak_zoning_support_traceability"),
        run_id=RunId("run_live_weak_zoning_support_traceability"),
    )

    verification = verify_report_traceability(report, claims=[], evidence_items=[])

    assert verification.status is VerificationStatus.PASSED_WITH_WARNINGS
    assert verification.checks["zoning_official_support"] == "warning"


def test_zoning_support_summary_warns_when_rules_are_indexed_but_not_live() -> None:
    summary = _zoning_support_summary(
        {
            "ordinance_search": {
                "fallback_source": "verified_dimensional_standard",
                "requires_official_verification": False,
                "authority_source_type": "indexed_dimensional_standard",
                "authority_resolution": "indexed_local_standard",
                "authority_confidence": "indexed_official_reference",
                "authority_jurisdiction": "Miami Gardens, FL",
                "authority_is_live": False,
                "authority_is_official": True,
            },
            "ordinance_rules": {
                "source": "verified_dimensional_standard",
                "zoning_district": "R-1",
                "min_lot_area_sqft": 7500.0,
                "requires_official_verification": False,
                "authority_is_live": False,
                "authority_is_official": True,
            },
            "gis_source": {
                "zoning_record_applicability": "direct",
            },
            "gis_site_context": {},
        }
    )

    assert summary["status"] == "warning"
    assert summary["reason"] == (
        "zoning authority source is not live/current enough for final entitlement claims"
    )
    assert summary["ordinance_rules_resolved"] is True
    assert summary["authority_is_official"] is True
    assert summary["authority_is_live"] is False


def test_zoning_support_summary_warns_when_gis_requires_municipal_verification() -> None:
    summary = _zoning_support_summary(
        {
            "ordinance_search": {
                "fallback_source": "municode_live_table",
                "requires_official_verification": False,
                "authority_confidence": "official_live_search",
                "authority_jurisdiction": "Fort Lauderdale, FL",
                "authority_is_live": True,
                "authority_is_official": True,
            },
            "ordinance_rules": {
                "source": "municode_live_table",
                "zoning_district": "RS-8",
                "min_lot_area_sqft": 6500.0,
                "requires_official_verification": False,
                "authority_is_live": True,
                "authority_is_official": True,
            },
            "gis_source": {},
            "gis_site_context": {
                "zoning_record_applicability": "requires_municipal_verification",
            },
        }
    )

    assert summary["status"] == "warning"
    assert summary["reason"] == "GIS zoning context requires municipal verification"
    assert summary["gis_applicability"] == "requires_municipal_verification"


def test_cli_verification_show_surfaces_zoning_support_snapshot(capsys) -> None:
    report_id, verification_id = _save_live_report_with_weak_zoning_support()

    verify_exit = main(["verification", "show", str(verification_id)])
    verification = json.loads(capsys.readouterr().out)

    assert verify_exit == 0
    assert verification["warning_checks"] == ["zoning_official_support"]
    assert verification["zoning_support_snapshot"]["report_id"] == str(report_id)
    assert verification["zoning_support_snapshot"]["requires_official_verification"] is True


def test_cli_report_finalize_is_blocked_for_weak_zoning_support(capsys) -> None:
    report_id, verification_id = _save_live_report_with_weak_zoning_support()

    finalize_exit = main(["reports", "finalize", str(report_id)])
    finalized = json.loads(capsys.readouterr().out)

    assert finalize_exit == 1
    assert finalized["error"] == "report_finalization_blocked"
    assert finalized["reason"] == "weak_zoning_official_support"
    assert finalized["verification_id"] == str(verification_id)


@pytest.mark.asyncio
async def test_api_verification_endpoints_surface_zoning_support_snapshot(
    client: AsyncClient,
) -> None:
    report_id, verification_id = _save_live_report_with_weak_zoning_support()

    verification_response = await client.get(f"/api/v1/verification/{verification_id}")
    report_response = await client.get(f"/api/v1/reports/{report_id}/verification")

    assert verification_response.status_code == 200
    assert report_response.status_code == 200
    assert verification_response.json()["warning_checks"] == ["zoning_official_support"]
    assert report_response.json()["zoning_support_snapshot"]["requires_official_verification"] is True


@pytest.mark.asyncio
async def test_api_report_finalize_is_blocked_for_weak_zoning_support(
    client: AsyncClient,
) -> None:
    report_id, verification_id = _save_live_report_with_weak_zoning_support()

    finalize_response = await client.post(f"/api/v1/reports/{report_id}/finalize")

    assert finalize_response.status_code == 409
    assert finalize_response.json()["detail"]["error"] == "report_finalization_blocked"
    assert finalize_response.json()["detail"]["reason"] == "weak_zoning_official_support"
    assert finalize_response.json()["detail"]["verification_id"] == str(verification_id)


def test_direct_report_finalize_is_blocked_for_weak_zoning_support() -> None:
    report_id, verification_id = _save_live_report_with_weak_zoning_support()

    with pytest.raises(ReportFinalizationBlockedError) as exc_info:
        finalize_report(
            report_id,
            report_ledger=LocalReportLedger(default_report_ledger_path()),
            verification_ledger=LocalVerificationLedger(default_verification_ledger_path()),
        )

    assert exc_info.value.reason == "weak_zoning_official_support"
    assert exc_info.value.verification is not None
    assert exc_info.value.verification.verification_id == verification_id
