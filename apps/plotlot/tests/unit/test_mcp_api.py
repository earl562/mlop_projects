"""Contract tests for the MCP adapter surface."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from plotlot.api.main import app
from plotlot.property.models import DatasetInfo


@pytest.mark.asyncio
async def test_mcp_tools_expose_contract_metadata() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/mcp/tools")

    assert response.status_code == 200
    tools = {tool["name"]: tool for tool in response.json()["tools"]}
    assert tools["plotlot.search_ordinance"]["risk_class"] == "read_only"
    assert "output_schema" in tools["plotlot.search_ordinance"]
    assert tools["plotlot.discover_open_data_layers"]["input_schema"]["required"] == [
        "county",
        "lat",
        "lng",
    ]
    assert tools["plotlot.search_municode_live"]["input_schema"]["required"] == [
        "municipality",
        "query",
    ]


@pytest.mark.asyncio
async def test_mcp_invoke_open_data_layers_returns_serialized_datasets(monkeypatch) -> None:
    monkeypatch.setattr(
        "plotlot.api.mcp.discover_datasets",
        AsyncMock(
            return_value=(
                DatasetInfo(
                    dataset_id="p1",
                    name="Parcel Layer",
                    url="https://example.com/FeatureServer",
                    layer_id=0,
                    dataset_type="parcels",
                    county="Broward",
                    state="FL",
                    fields=["FOLIO", "OWNER"],
                ),
                DatasetInfo(
                    dataset_id="z1",
                    name="Zoning Layer",
                    url="https://example.com/Zoning/FeatureServer",
                    layer_id=9,
                    dataset_type="zoning",
                    county="Broward",
                    state="FL",
                    fields=["ZONE", "DESC"],
                ),
            )
        ),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/mcp/invoke",
            json={
                "name": "plotlot.discover_open_data_layers",
                "input": {"county": "Broward", "state": "FL", "lat": 26.1, "lng": -80.1},
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["result"]["parcels_dataset"]["dataset_type"] == "parcels"
    assert payload["result"]["zoning_dataset"]["fields_preview"] == ["ZONE", "DESC"]


@pytest.mark.asyncio
async def test_mcp_invoke_municode_live_returns_parsed_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        "plotlot.api.chat._execute_municode_live_search",
        AsyncMock(
            return_value=json.dumps(
                {
                    "status": "success",
                    "municipality": "Miami",
                    "source_type": "municode_live",
                    "results": [
                        {
                            "heading": "Sec. 1 Setbacks",
                            "parent_heading": "Zoning",
                            "node_id": "123",
                            "score": 2,
                            "snippet": "Front setback 25 ft.",
                        }
                    ],
                }
            )
        ),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/mcp/invoke",
            json={
                "name": "plotlot.search_municode_live",
                "input": {"municipality": "Miami", "query": "setbacks"},
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["tool"] == "plotlot.search_municode_live"
    assert payload["result"]["status"] == "success"
    assert payload["result"]["results"][0]["node_id"] == "123"
