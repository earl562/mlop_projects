from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from plotlot.api.main import app


@pytest.fixture
def transport() -> ASGITransport:
    return ASGITransport(app=app)


@pytest.fixture
async def client(transport: ASGITransport):
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_municode_api_search_section_and_extract_rules(client: AsyncClient) -> None:
    search_response = await client.post(
        "/api/v1/municode/search",
        json={"jurisdiction": "miami", "query": "parking", "source_mode": "fixture"},
    )
    section_id = search_response.json()["results"][0]["section_id"]
    section_response = await client.get(f"/api/v1/municode/sections/{section_id}")
    rules_response = await client.post(
        "/api/v1/ordinances/extract-rules",
        json={"section_id": section_id, "source_mode": "fixture"},
    )

    assert search_response.status_code == 200
    assert search_response.json()["results"][0]["provider"] == "municode"
    assert section_response.status_code == 200
    assert section_response.json()["section_identifier"] == "Sec. 7.1.2.3"
    assert rules_response.status_code == 200
    assert rules_response.json()["rules"]["parking_spaces_per_dwelling_unit"] == 1.5
