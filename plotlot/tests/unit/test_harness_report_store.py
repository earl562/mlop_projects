from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch

from plotlot.api.main import app
from plotlot.cli_harness import main
from plotlot.harness.contracts import ReportId, ReportStatus
from plotlot.harness.evidence_store import LocalEvidenceLedger
from plotlot.harness.fixture_runs import FixtureDealRunRequest, run_fixture_deal_analysis
from plotlot.harness.report_store import LocalReportLedger
from plotlot.harness.run_persistence import FixtureRunPersistenceStores, persist_fixture_run_result
from plotlot.harness.run_store import LocalHarnessRunStore


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


def test_fixture_run_persistence_saves_claims_and_report(tmp_path) -> None:
    # Given: a fixture run result and isolated local ledgers.
    result = run_fixture_deal_analysis(
        FixtureDealRunRequest(
            address="example Miami-Dade fixture address",
            analysis_type="acquisition_memo",
        )
    )
    report_ledger = LocalReportLedger(tmp_path / "reports.json")

    # When: the shared fixture persistence path is used.
    persist_fixture_run_result(
        result,
        FixtureRunPersistenceStores(
            run_store=LocalHarnessRunStore(tmp_path / "runs.json"),
            evidence_ledger=LocalEvidenceLedger(tmp_path / "evidence.json"),
            report_ledger=report_ledger,
        ),
    )

    # Then: report claims retain source-grounding and the report links them.
    claims = report_ledger.list_claims(run_id=result.run_id)
    report = report_ledger.get_report(ReportId(result.report_id))
    assert claims
    assert claims[0].evidence_ids[0] == result.evidence_ids[0]
    assert report.run_id == result.run_id
    assert report.status is ReportStatus.PRELIMINARY
    assert report.claims == [claim.claim_id for claim in claims]


def test_cli_run_persists_claims_and_report_for_inspection(capsys) -> None:
    # Given: a fixture acquisition memo run through the CLI.
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

    # When: claims and the report are inspected through CLI surfaces.
    list_exit = main(["claims", "list", "--run-id", run_payload["run_id"]])
    listed = json.loads(capsys.readouterr().out)
    claim_id = listed["claims"][0]["claim_id"]
    show_claim_exit = main(["claims", "show", claim_id])
    shown_claim = json.loads(capsys.readouterr().out)
    show_report_exit = main(["reports", "show", run_payload["report_id"]])
    shown_report = json.loads(capsys.readouterr().out)

    # Then: both surfaces read the shared report ledger.
    assert run_exit == 0
    assert list_exit == 0
    assert show_claim_exit == 0
    assert show_report_exit == 0
    assert shown_claim["evidence_ids"][0] in run_payload["evidence_ids"]
    assert shown_report["report_id"] == run_payload["report_id"]
    assert claim_id in shown_report["claims"]
    assert shown_report["comp_support_snapshot"]["status"] == "passed"
    assert shown_report["comp_support_snapshot"]["combined_support_tier"] != "unknown"


@pytest.mark.asyncio
async def test_api_run_persists_claims_and_report_for_inspection(client: AsyncClient) -> None:
    # Given: a fixture acquisition memo run through the API.
    create_response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "example Miami-Dade fixture address",
            "analysis_type": "acquisition_memo",
            "source_mode": "fixture",
        },
    )
    run_payload = create_response.json()

    # When: claims and the report are inspected through API routes.
    claims_response = await client.get(f"/api/v1/harness/runs/{run_payload['run_id']}/claims")
    claim_id = claims_response.json()["claims"][0]["claim_id"]
    claim_response = await client.get(f"/api/v1/claims/{claim_id}")
    report_response = await client.get(f"/api/v1/reports/{run_payload['report_id']}")

    # Then: the persisted report is traceable back to claim and evidence IDs.
    assert create_response.status_code == 200
    assert claims_response.status_code == 200
    assert claim_response.status_code == 200
    assert report_response.status_code == 200
    assert claim_response.json()["evidence_ids"][0] in run_payload["evidence_ids"]
    assert claim_id in report_response.json()["claims"]
