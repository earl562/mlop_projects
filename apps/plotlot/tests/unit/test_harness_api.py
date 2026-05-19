"""Unit tests for the harness execution API."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from plotlot.api.main import app
from plotlot.core.types import Setbacks, ZoningReport


@pytest.mark.asyncio
async def test_harness_run_endpoint_executes_zoning_research_skill(monkeypatch) -> None:
    report = ZoningReport(
        address="123 Main St",
        formatted_address="123 Main St, Miami, FL",
        municipality="Miami",
        county="Miami-Dade",
        zoning_district="RU-1",
        allowed_uses=["single-family"],
        setbacks=Setbacks(front="25 ft", side="7.5 ft", rear="25 ft"),
        summary="Single-family zoning report.",
        sources=["Sec. 33-1"],
        confidence="high",
    )
    monkeypatch.setattr(
        "plotlot.skills.zoning_research.workflow.lookup_address",
        AsyncMock(return_value=report),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/harness/run",
            json={
                "skill": "zoning_research",
                "prompt": "123 Main St",
                "payload": {"address": "123 Main St"},
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["data"]["report"]["zoning_district"] == "RU-1"
    assert data["evidence_ids"] == ["ev_source_0"]


@pytest.mark.asyncio
async def test_harness_run_uses_prompt_as_address_when_payload_missing(monkeypatch) -> None:
    report = ZoningReport(
        address="123 Main St",
        formatted_address="123 Main St, Miami, FL",
        municipality="Miami",
        county="Miami-Dade",
        zoning_district="RU-1",
        allowed_uses=["single-family"],
        setbacks=Setbacks(front="25 ft", side="7.5 ft", rear="25 ft"),
        summary="Single-family zoning report.",
        sources=["Sec. 33-1"],
        confidence="high",
    )
    monkeypatch.setattr(
        "plotlot.skills.zoning_research.workflow.lookup_address",
        AsyncMock(return_value=report),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/harness/run",
            json={"skill": "zoning_research", "prompt": "123 Main St"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["data"]["report"]["zoning_district"] == "RU-1"


@pytest.mark.asyncio
async def test_harness_run_routes_intent_aliases(monkeypatch) -> None:
    report = ZoningReport(
        address="123 Main St",
        formatted_address="123 Main St, Miami, FL",
        municipality="Miami",
        county="Miami-Dade",
        zoning_district="RU-1",
        allowed_uses=["single-family"],
        setbacks=Setbacks(front="25 ft", side="7.5 ft", rear="25 ft"),
        summary="Single-family zoning report.",
        sources=["Sec. 33-1"],
        confidence="high",
    )
    monkeypatch.setattr(
        "plotlot.skills.zoning_research.workflow.lookup_address",
        AsyncMock(return_value=report),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/harness/run",
            json={"intent": "zoning_lookup", "prompt": "123 Main St"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["data"]["report"]["zoning_district"] == "RU-1"


@pytest.mark.asyncio
async def test_mcp_tools_endpoint_lists_known_tools() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/mcp/tools")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data.get("tools"), list)
    assert any(tool.get("name") == "plotlot.search_ordinance" for tool in data["tools"])
