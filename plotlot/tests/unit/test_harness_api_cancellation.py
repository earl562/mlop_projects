from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch

from plotlot.api.main import app
from plotlot.harness.contracts import SourceMode
from plotlot.harness.fixture_runs import (
    FixtureDealRunRequest,
    run_fixture_deal_analysis_async,
)
from plotlot.harness.run_store import default_harness_run_store


@pytest.fixture(autouse=True)
def harness_store_path(tmp_path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("PLOTLOT_HARNESS_STORE_PATH", str(tmp_path / "harness-runs.json"))
    monkeypatch.setenv("PLOTLOT_HARNESS_JOB_STORE_PATH", str(tmp_path / "harness-jobs.json"))
    monkeypatch.setenv("PLOTLOT_HARNESS_REPORT_STORE_PATH", str(tmp_path / "harness-reports.json"))


@pytest.fixture
def transport() -> ASGITransport:
    return ASGITransport(app=app)


@pytest.fixture
async def client(transport: ASGITransport):
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_harness_run_cancel_api_updates_queued_run_and_emits_event(
    client: AsyncClient,
) -> None:
    result = (
        await run_fixture_deal_analysis_async(
            FixtureDealRunRequest(
                address="example queued API cancellation fixture address",
                analysis_type="acquisition_memo",
                source_mode=SourceMode.FIXTURE,
            )
        )
    ).model_copy(update={"status": "queued"})
    default_harness_run_store().save_run(result)

    cancel_response = await client.post(
        f"/api/v1/harness/runs/{result.run_id}/cancel",
        json={"reason": "No longer needed.", "actor_user_id": "api_fixture"},
    )
    events_response = await client.get(f"/api/v1/harness/runs/{result.run_id}/events")

    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"
    assert events_response.json()["events"][-1]["type"] == "run.cancelled"
    assert events_response.json()["events"][-1]["payload"]["actor_user_id"] == "api_fixture"
