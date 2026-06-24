from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from uuid import uuid4

from plotlot.api.main import app
from plotlot.harness.agent_run_store import clear_agent_run_store
from plotlot.pipeline.lookup_snapshot import build_lookup_snapshot
from plotlot.pipeline.lookup_snapshot_store import clear_lookup_snapshot_store, save_lookup_snapshot
from tests.unit.lookup_snapshot_repository_fixtures import report


@pytest.fixture
def transport() -> ASGITransport:
    return ASGITransport(app=app)


@pytest.mark.asyncio
async def test_agent_run_start_rejects_duplicate_run_ids(
    transport: ASGITransport,
) -> None:
    clear_agent_run_store()
    clear_lookup_snapshot_store()
    snapshot = build_lookup_snapshot(report(with_density_analysis=True))
    save_lookup_snapshot(snapshot)
    run_id = f"run_{uuid4().hex}"

    payload = {
        "lookup_snapshot_id": str(snapshot.lookup_snapshot_id),
        "workspace_id": "ws_agent_access",
        "project_id": "project_agent_access",
        "run_id": run_id,
        "objective": "Lock durable replay state to a unique run ID.",
    }

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first_response = await client.post("/api/v1/agent-runs", json=payload)
        second_response = await client.post("/api/v1/agent-runs", json=payload)

    assert first_response.status_code == 200
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == f"Agent run {run_id} already exists"


@pytest.mark.asyncio
async def test_agent_run_endpoints_require_matching_workspace_scope(
    transport: ASGITransport,
) -> None:
    clear_agent_run_store()
    clear_lookup_snapshot_store()
    snapshot = build_lookup_snapshot(report(with_density_analysis=True))
    save_lookup_snapshot(snapshot)
    run_id = f"run_{uuid4().hex}"

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        start_response = await client.post(
            "/api/v1/agent-runs",
            json={
                "lookup_snapshot_id": str(snapshot.lookup_snapshot_id),
                "workspace_id": "ws_agent_owner",
                "project_id": "project_agent_owner",
                "run_id": run_id,
                "objective": "Protect scoped replay traces.",
            },
        )
        trace_response = await client.get(
            f"/api/v1/agent-runs/{run_id}/trace?workspace_id=ws_agent_other"
        )
        eval_response = await client.post(
            f"/api/v1/agent-runs/{run_id}/evals?workspace_id=ws_agent_other"
        )

    assert start_response.status_code == 200
    assert trace_response.status_code == 404
    assert trace_response.json()["detail"] == "Agent run not found"
    assert eval_response.status_code == 404
    assert eval_response.json()["detail"] == "Agent run not found"
