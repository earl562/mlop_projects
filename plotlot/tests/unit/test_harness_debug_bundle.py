from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch

from plotlot.api.main import app
from plotlot.cli_harness import main
from plotlot.harness.approval_store import LocalApprovalLedger
from plotlot.harness.calculation_store import LocalCalculationLedger
from plotlot.harness.contracts import CalculationResult, RunId
from plotlot.harness.debug_bundle import DebugBundleStores, export_debug_bundle
from plotlot.harness.evidence_store import LocalEvidenceLedger
from plotlot.harness.fixture_runs import FixtureDealRunRequest, run_fixture_deal_analysis
from plotlot.harness.memory_store import LocalMemoryStore, MemoryWriteRequest
from plotlot.harness.report_store import LocalReportLedger
from plotlot.harness.run_persistence import FixtureRunPersistenceStores, persist_fixture_run_result
from plotlot.harness.run_store import LocalHarnessRunStore
from plotlot.harness.tool_call_store import LocalToolCallLedger, tool_call_from_result
from plotlot.harness.tool_router import HarnessToolCallRequest, default_tool_router
from plotlot.domain.types import ToolContext
from plotlot.harness.verification_store import LocalVerificationLedger


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
    monkeypatch.setenv(
        "PLOTLOT_HARNESS_APPROVAL_STORE_PATH",
        str(tmp_path / "harness-approvals.json"),
    )
    monkeypatch.setenv("PLOTLOT_HARNESS_MEMORY_STORE_PATH", str(tmp_path / "harness-memory.json"))
    monkeypatch.setenv("PLOTLOT_HARNESS_TOOL_CALL_STORE_PATH", str(tmp_path / "tool-calls.json"))


@pytest.fixture
def transport() -> ASGITransport:
    return ASGITransport(app=app)


@pytest.fixture
async def client(transport: ASGITransport):
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def test_debug_bundle_exports_run_traceability_without_transcript_text(tmp_path) -> None:
    # Given: a persisted fixture run with evidence, report, verification, and a calculation.
    run_store = LocalHarnessRunStore(tmp_path / "runs.json")
    evidence_ledger = LocalEvidenceLedger(tmp_path / "evidence.json")
    report_ledger = LocalReportLedger(tmp_path / "reports.json")
    calculation_ledger = LocalCalculationLedger(tmp_path / "calculations.json")
    verification_ledger = LocalVerificationLedger(tmp_path / "verifications.json")
    approval_ledger = LocalApprovalLedger(tmp_path / "approvals.json")
    memory_store = LocalMemoryStore(tmp_path / "memory.json")
    tool_call_ledger = LocalToolCallLedger(tmp_path / "tool-calls.json")
    result = run_fixture_deal_analysis(
        FixtureDealRunRequest(
            address="example Miami-Dade fixture address",
            analysis_type="acquisition_memo",
        )
    )
    persist_fixture_run_result(
        result,
        FixtureRunPersistenceStores(
            run_store=run_store,
            evidence_ledger=evidence_ledger,
            report_ledger=report_ledger,
            verification_ledger=verification_ledger,
        ),
    )
    calculation_ledger.save_calculation(
        CalculationResult(
            calculation_id="calc_debug_bundle_residual",
            run_id=result.run_id,
            calculation_type="residual_land_value",
            inputs={"as_built_value": 1_235_000},
            assumptions={"source": "fixture"},
            outputs={"max_supportable_land_price": 195_000},
            formula_version="residual_land_value.v1",
        )
    )
    memory_store.write_memory(
        MemoryWriteRequest(
            workspace_id="workspace_fixture",
            project_id="project_fixture",
            site_id="site_fixture",
            memory_type="site_assumption",
            content="Sponsor prefers 850 sf average unit assumptions.",
            source_run_id=result.run_id,
            evidence_ids=[result.evidence_ids[0]],
        )
    )
    tool_result = default_tool_router().call(
        HarnessToolCallRequest(
            tool_name="search_municode",
            args={"jurisdiction": "miami", "query": "parking"},
            context=ToolContext(
                workspace_id="workspace_fixture",
                actor_user_id="analyst_fixture",
                run_id=str(result.run_id),
            ),
        )
    )
    tool_call_ledger.save_tool_call(tool_call_from_result(tool_result))

    # When: a debug bundle is exported through the shared harness exporter.
    bundle = export_debug_bundle(
        RunId(result.run_id),
        DebugBundleStores(
            run_store=run_store,
            evidence_ledger=evidence_ledger,
            report_ledger=report_ledger,
            calculation_ledger=calculation_ledger,
            verification_ledger=verification_ledger,
            approval_ledger=approval_ledger,
            memory_store=memory_store,
            tool_call_ledger=tool_call_ledger,
        ),
    )

    # Then: the bundle joins traceability data and carries transcript redaction metadata.
    dumped = bundle.model_dump(mode="json")
    assert dumped["run"]["run_id"] == result.run_id
    assert dumped["event_count"] == len(result.events)
    assert dumped["evidence"][0]["evidence_id"] in result.evidence_ids
    assert dumped["claims"][0]["evidence_ids"][0] in result.evidence_ids
    assert dumped["calculations"][0]["calculation_id"] == "calc_debug_bundle_residual"
    assert dumped["verifications"][0]["status"] == "blocked"
    assert dumped["reports"][0]["report_id"] == result.report_id
    assert dumped["approvals"] == []
    assert dumped["approval_events"] == []
    assert dumped["memory"][0]["metadata"]["is_evidence"] is False
    assert dumped["memory"][0]["source_run_id"] == result.run_id
    assert dumped["tool_calls"][0]["tool_name"] == "search_municode"
    assert "full_transcripts_omitted" in dumped["redactions"]


def test_cli_runs_export_debug_bundle_reads_shared_ledgers(capsys) -> None:
    # Given: a fixture run persisted through the CLI.
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

    # When: the run debug bundle is exported through the CLI.
    bundle_exit = main(["runs", "export-debug-bundle", run_payload["run_id"]])
    bundle = json.loads(capsys.readouterr().out)

    # Then: CLI output includes persisted evidence, report, and verification metadata.
    assert run_exit == 0
    assert bundle_exit == 0
    assert bundle["run"]["run_id"] == run_payload["run_id"]
    assert bundle["reports"][0]["report_id"] == run_payload["report_id"]
    assert bundle["verifications"][0]["status"] == "blocked"


@pytest.mark.asyncio
async def test_api_run_debug_bundle_reads_shared_ledgers(client: AsyncClient) -> None:
    # Given: a fixture run persisted through the API.
    create_response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "example Miami-Dade fixture address",
            "analysis_type": "acquisition_memo",
            "source_mode": "fixture",
        },
    )
    run_payload = create_response.json()

    # When: the debug bundle endpoint is requested.
    bundle_response = await client.get(f"/api/v1/harness/runs/{run_payload['run_id']}/debug-bundle")
    bundle = bundle_response.json()

    # Then: API output reconstructs the persisted run traceability bundle.
    assert create_response.status_code == 200
    assert bundle_response.status_code == 200
    assert bundle["run"]["run_id"] == run_payload["run_id"]
    assert bundle["evidence"][0]["evidence_id"] in run_payload["evidence_ids"]
    assert bundle["reports"][0]["report_id"] == run_payload["report_id"]
