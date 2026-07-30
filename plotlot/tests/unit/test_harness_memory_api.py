from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch

from plotlot.api.main import app


@pytest.fixture(autouse=True)
def memory_store_path(tmp_path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("PLOTLOT_HARNESS_MEMORY_STORE_PATH", str(tmp_path / "memory.json"))


@pytest.fixture
def transport() -> ASGITransport:
    return ASGITransport(app=app)


@pytest.fixture
async def client(transport: ASGITransport):
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_memory_api_creates_lists_shows_and_updates_memory(client: AsyncClient) -> None:
    create_response = await client.post(
        "/api/v1/harness/memory",
        json={
            "workspace_id": "ws_fixture",
            "project_id": "project_fixture",
            "site_id": "site_fixture",
            "memory_type": "site_assumption",
            "content": "Use 850 sf average unit size until official plans are provided.",
            "source_run_id": "run_fixture_001",
            "evidence_ids": ["ev_fixture_001"],
        },
    )
    created = create_response.json()
    list_response = await client.get(
        "/api/v1/harness/memory", params={"workspace_id": "ws_fixture"}
    )
    show_response = await client.get(f"/api/v1/harness/memory/{created['memory_id']}")
    update_response = await client.patch(
        f"/api/v1/harness/memory/{created['memory_id']}",
        json={"content": "Use 900 sf average unit size from sponsor update."},
    )

    assert create_response.status_code == 200
    assert list_response.status_code == 200
    assert show_response.status_code == 200
    assert update_response.status_code == 200
    assert created["metadata"]["is_evidence"] is False
    assert list_response.json()["memory"][0]["memory_id"] == created["memory_id"]
    assert show_response.json()["source_run_id"] == "run_fixture_001"
    assert update_response.json()["content"] == "Use 900 sf average unit size from sponsor update."


@pytest.mark.asyncio
async def test_memory_api_returns_404_for_missing_memory(client: AsyncClient) -> None:
    response = await client.get("/api/v1/harness/memory/mem_missing")

    assert response.status_code == 404
