from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch

from plotlot.api.main import app


@pytest.fixture(autouse=True)
def harness_store_paths(tmp_path, monkeypatch: MonkeyPatch) -> None:
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
    monkeypatch.setenv(
        "PLOTLOT_HARNESS_APPROVAL_STORE_PATH",
        str(tmp_path / "harness-approvals.json"),
    )


@pytest.fixture
def transport() -> ASGITransport:
    return ASGITransport(app=app)


@pytest.fixture
async def client(transport: ASGITransport):
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_harness_approval_api_requests_lists_shows_and_approves(
    client: AsyncClient,
) -> None:
    request_response = await client.post(
        "/api/v1/harness/runs/run_fixture_api_approval/approvals",
        json={
            "requested_action": "export_lender_package",
            "risk_level": "high",
            "reason": "Exporting a lender package requires analyst approval.",
            "policy_ids": ["fixture-export-approval"],
        },
    )
    approval_id = request_response.json()["approval_id"]

    list_response = await client.get("/api/v1/harness/runs/run_fixture_api_approval/approvals")
    show_response = await client.get(f"/api/v1/harness/approvals/{approval_id}")
    approve_response = await client.post(
        f"/api/v1/harness/approvals/{approval_id}/approve",
        json={"resolved_by": "analyst@example.test"},
    )

    assert request_response.status_code == 200
    assert list_response.status_code == 200
    assert show_response.status_code == 200
    assert approve_response.status_code == 200
    assert list_response.json()["approvals"][0]["approval_id"] == approval_id
    assert show_response.json()["status"] == "pending"
    assert approve_response.json()["status"] == "approved"
    assert approve_response.json()["resolved_by"] == "analyst@example.test"


@pytest.mark.asyncio
async def test_harness_debug_bundle_includes_local_approval_artifacts(
    client: AsyncClient,
) -> None:
    run_response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "example Miami-Dade fixture address",
            "analysis_type": "acquisition_memo",
            "source_mode": "fixture",
        },
    )
    run_id = run_response.json()["run_id"]
    approval_response = await client.post(
        f"/api/v1/harness/runs/{run_id}/approvals",
        json={
            "requested_action": "export_lender_package",
            "risk_level": "high",
            "reason": "Fixture report export requires analyst approval.",
        },
    )

    bundle_response = await client.get(f"/api/v1/harness/runs/{run_id}/debug-bundle")

    assert approval_response.status_code == 200
    assert bundle_response.status_code == 200
    assert bundle_response.json()["approvals"][0]["approval_id"] == approval_response.json()[
        "approval_id"
    ]
    assert bundle_response.json()["approval_events"][0]["type"] == "approval.requested"
