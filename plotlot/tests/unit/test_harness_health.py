from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch

from plotlot.api.main import app
from plotlot.cli_harness import main
from plotlot.harness.health import collect_harness_health


@pytest.fixture(autouse=True)
def harness_health_paths(tmp_path, monkeypatch: MonkeyPatch) -> None:
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


def test_harness_health_collector_reports_registry_source_and_store_readiness() -> None:
    report = collect_harness_health()
    checks = {check.name: check for check in report.checks}

    assert report.status == "ok"
    assert checks["registries"].status == "ok"
    assert checks["south_florida_gis_catalog"].metadata["source_count"] >= 2
    assert checks["municode_fixture_catalog"].metadata["source_count"] >= 1
    assert checks["training_fixture_catalog"].metadata["video_count"] >= 1
    assert checks["local_store_paths"].metadata["approval_store"].endswith("harness-approvals.json")
    assert checks["local_store_paths"].metadata["memory_store"].endswith("harness-memory.json")
    assert checks["local_store_paths"].metadata["tool_call_store"].endswith("tool-calls.json")


def test_cli_doctor_returns_shared_harness_health(capsys) -> None:
    exit_code = main(["doctor"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "ok"
    assert payload["harness_health"]["status"] == "ok"
    assert payload["harness_health"]["metrics"]["skill_count"] >= 8
    assert payload["harness_health"]["metrics"]["municode_source_count"] >= 1


@pytest.mark.asyncio
async def test_harness_health_api_exposes_component_views(client: AsyncClient) -> None:
    harness_response = await client.get("/api/v1/health/harness")
    source_response = await client.get("/api/v1/health/sources")
    queue_response = await client.get("/api/v1/health/queue")
    cli_response = await client.get("/api/v1/health/cli")

    assert harness_response.status_code == 200
    assert source_response.status_code == 200
    assert queue_response.status_code == 200
    assert cli_response.status_code == 200
    assert harness_response.json()["status"] == "ok"
    assert source_response.json()["checks"][0]["name"] == "south_florida_gis_catalog"
    assert source_response.json()["checks"][1]["name"] == "municode_fixture_catalog"
    assert queue_response.json()["checks"][0]["name"] == "queue"
    assert cli_response.json()["checks"][0]["name"] == "cli"
    assert "tui" in cli_response.json()["checks"][0]["metadata"]["commands"]
