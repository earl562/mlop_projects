from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch

from plotlot.api.main import app
from plotlot.cli_harness import main
from plotlot.harness.contracts import Report, ReportId, ReportStatus, ReportType, RunId, SourceMode
from plotlot.harness.evidence_store import LocalEvidenceLedger
from plotlot.harness.fixture_runs import FixtureDealRunRequest, run_fixture_deal_analysis
from plotlot.harness.report_export import ReportArtifactExportRequest, export_report_artifact
from plotlot.harness.report_store import LocalReportLedger
from plotlot.harness.run_persistence import FixtureRunPersistenceStores, persist_fixture_run_result
from plotlot.harness.run_store import LocalHarnessRunStore
from plotlot.harness.verification_store import LocalVerificationLedger


@pytest.fixture(autouse=True)
def harness_store_path(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
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
    monkeypatch.setenv("PLOTLOT_HARNESS_REPORT_EXPORT_DIR", str(tmp_path / "exports"))


@pytest.fixture
def transport() -> ASGITransport:
    return ASGITransport(app=app)


@pytest.fixture
async def client(transport: ASGITransport):
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def test_report_export_writes_artifact_updates_report_and_appends_event(tmp_path: Path) -> None:
    result = run_fixture_deal_analysis(
        FixtureDealRunRequest(
            address="example Miami-Dade fixture address",
            analysis_type="acquisition_memo",
        )
    )
    report_ledger = LocalReportLedger(tmp_path / "reports.json")
    run_store = LocalHarnessRunStore(tmp_path / "runs.json")
    persist_fixture_run_result(
        result,
        FixtureRunPersistenceStores(
            run_store=run_store,
            evidence_ledger=LocalEvidenceLedger(tmp_path / "evidence.json"),
            report_ledger=report_ledger,
            verification_ledger=LocalVerificationLedger(tmp_path / "verifications.json"),
        ),
    )

    export = export_report_artifact(
        ReportArtifactExportRequest(
            report_id=ReportId(result.report_id),
            export_dir=tmp_path / "exports",
        ),
        report_ledger=report_ledger,
        run_store=run_store,
    )

    exported_path = Path(export.file_path)
    exported_text = exported_path.read_text(encoding="utf-8")
    updated_report = report_ledger.get_report(ReportId(result.report_id))
    events = run_store.get_events(result.run_id)
    assert exported_path.exists()
    assert "Preliminary Acquisition Memo" in exported_text
    assert "- Comping search phase: accepted direct land comps" in exported_text
    assert "- Comping accepted land comps: 2" in exported_text
    assert export.artifact_uri in updated_report.export_urls
    assert events[-1].type == "report.exported"
    assert events[-1].payload["report_id"] == result.report_id


def test_report_export_surfaces_acquisition_guidance_summary(tmp_path: Path) -> None:
    report_ledger = LocalReportLedger(tmp_path / "reports.json")
    run_store = LocalHarnessRunStore(tmp_path / "runs.json")
    report = Report(
        report_id=ReportId("report_live_guidance"),
        run_id=RunId("run_live_guidance"),
        report_type=ReportType.ACQUISITION_MEMO,
        title="Preliminary Acquisition Memo",
        status=ReportStatus.PRELIMINARY,
        sections=[
            {
                "section_id": "underwriting_summary",
                "title": "Underwriting Summary",
                "acquisition_guidance": {
                    "recommended_action": "offer_range",
                    "basis": "county_reconciled_land_signal",
                    "market_signal_verification_status": "county_reconciled",
                    "recommendation_confidence": "medium",
                    "requires_market_signal_validation": False,
                },
                "comp_support_summary": {
                    "status": "warning",
                    "reason": "offer guidance depends on county-reconciled public listing support rather than direct land comps",
                    "comping_underwriting_status": "blocked_pending_county_reconciliation",
                    "comping_underwriting_blocker": (
                        "public listing comps require county-record reconciliation before confident underwriting"
                    ),
                    "land_support_source": "contextual_public_listing",
                    "land_support_fit_score": 0.891,
                    "land_support_quality_score": 0.0,
                    "exit_support_fit_score": 1.0,
                    "exit_support_quality_score": 0.92,
                    "combined_support_tier": "exit_only",
                },
                "contextual_land_listing_reconciliation": {
                    "status": "no_county_record_match",
                    "attempted_candidate_count": 3,
                    "reconciled_candidate_count": 0,
                    "rejected_candidate_count": 3,
                },
                "comping_decision_trace": {
                    "status": "blocked_pending_county_reconciliation",
                    "search_phase_reached": "pending_county_reconciliation",
                    "accepted_land_comp_count": 0,
                    "accepted_exit_comp_count": 2,
                    "contextual_public_listing_count": 3,
                    "county_reconciled_public_listing_count": 0,
                    "rejected_candidate_count": 3,
                    "next_required_action": "reconcile_public_listing_candidates_to_county_records",
                },
            }
        ],
        source_mode=SourceMode.LIVE,
    )
    report_ledger.save_report(report)

    export = export_report_artifact(
        ReportArtifactExportRequest(
            report_id=report.report_id,
            export_dir=tmp_path / "exports",
        ),
        report_ledger=report_ledger,
        run_store=run_store,
    )

    markdown = Path(export.file_path).read_text(encoding="utf-8")
    assert "- Market signal verification: county reconciled" in markdown
    assert "- Recommendation confidence: medium" in markdown
    assert "- Recommended action: offer range" in markdown
    assert "- Guidance basis: county reconciled land signal" in markdown
    assert "- Market validation required: no" in markdown
    assert "- Comp support check: warning" in markdown
    assert "county-reconciled public listing support rather than direct land comps" in markdown
    assert "- Comp support tier: exit only" in markdown
    assert "- Land support source: contextual public listing" in markdown
    assert "- Land support fit score: 0.891" in markdown
    assert "- Exit support fit score: 1.000" in markdown
    assert "- Comping underwriting status: blocked pending county reconciliation" in markdown
    assert (
        "public listing comps require county-record reconciliation before confident underwriting"
        in markdown
    )
    assert "- County reconciliation status: no county record match" in markdown
    assert "- County reconciliation attempted candidates: 3" in markdown
    assert "- County reconciliation matched candidates: 0" in markdown
    assert "- County reconciliation rejected candidates: 3" in markdown
    assert "- Comping search phase: pending county reconciliation" in markdown
    assert "- Comping accepted land comps: 0" in markdown
    assert "- Comping contextual listing comps: 3" in markdown
    assert (
        "- Comping next action: reconcile public listing candidates to county records" in markdown
    )


def test_cli_report_export_reads_shared_report_ledger(capsys) -> None:
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

    export_exit = main(["reports", "export", run_payload["report_id"]])
    export_payload = json.loads(capsys.readouterr().out)
    show_exit = main(["reports", "show", run_payload["report_id"]])
    report_payload = json.loads(capsys.readouterr().out)

    assert run_exit == 0
    assert export_exit == 0
    assert show_exit == 0
    assert Path(export_payload["file_path"]).exists()
    assert export_payload["artifact_uri"] in report_payload["export_urls"]


@pytest.mark.asyncio
async def test_api_report_export_writes_file_and_appends_event(client: AsyncClient) -> None:
    create_response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "example Miami-Dade fixture address",
            "analysis_type": "acquisition_memo",
            "source_mode": "fixture",
        },
    )
    run_payload = create_response.json()

    export_response = await client.post(f"/api/v1/reports/{run_payload['report_id']}/export")
    report_response = await client.get(f"/api/v1/reports/{run_payload['report_id']}")
    events_response = await client.get(f"/api/v1/harness/runs/{run_payload['run_id']}/events")

    assert create_response.status_code == 200
    assert export_response.status_code == 200
    assert Path(export_response.json()["file_path"]).exists()
    assert export_response.json()["artifact_uri"] in report_response.json()["export_urls"]
    assert events_response.json()["events"][-1]["type"] == "report.exported"


def test_approved_export_report_tool_writes_export_artifact(capsys) -> None:
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
    approval_id = f"apr_{run_payload['run_id']}_export_report"

    tool_exit = main(
        [
            "tools",
            "call",
            "export_report",
            "--run-id",
            run_payload["run_id"],
            "--workspace-id",
            "ws_fixture",
            "--approved-approval-id",
            approval_id,
            "--json",
            json.dumps({"report_id": run_payload["report_id"]}),
        ]
    )
    tool_payload = json.loads(capsys.readouterr().out)

    assert run_exit == 0
    assert tool_exit == 0
    assert tool_payload["ok"] is True
    assert Path(tool_payload["payload"]["export"]["file_path"]).exists()
