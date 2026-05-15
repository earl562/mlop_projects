"""Thin MCP-style adapter over internal PlotLot tools.

This keeps MCP as an external adapter. The internal product contract remains
the FastAPI/harness/tool layer.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from plotlot.api.ordinances import ExtractRulesRequest, extract_rules, search_ordinance_records
from plotlot.property.hub_discovery import discover_datasets
from plotlot.storage.db import get_session

router = APIRouter(prefix="/api/v1/mcp", tags=["mcp"])


class MCPInvokeRequest(BaseModel):
    name: str
    input: dict[str, Any] = Field(default_factory=dict)


MCP_TOOLS: list[dict[str, Any]] = [
    {
        "name": "plotlot.search_ordinance",
        "description": "Search PlotLot's ordinance intelligence index for cited zoning sections.",
        "risk_class": "read_only",
        "input_schema": {
            "type": "object",
            "properties": {
                "municipality": {"type": "string"},
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "required": ["municipality", "query"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "section_id": {"type": "string"},
                            "section": {"type": "string"},
                            "title": {"type": "string"},
                            "text_preview": {"type": "string"},
                            "municipality": {"type": "string"},
                            "score": {"type": "number"},
                        },
                    },
                }
            },
        },
    },
    {
        "name": "plotlot.get_zoning_rules",
        "description": "Return candidate normalized zoning rules for a zoning code.",
        "risk_class": "read_only",
        "input_schema": {
            "type": "object",
            "properties": {
                "municipality": {"type": "string"},
                "zoning_code": {"type": "string"},
            },
            "required": ["municipality", "zoning_code"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "zoning_code": {"type": "string"},
                "rules": {"type": "array"},
                "open_questions": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    {
        "name": "plotlot.discover_open_data_layers",
        "description": "Discover parcel and zoning ArcGIS/Open Data layers for a county and location.",
        "risk_class": "read_only",
        "input_schema": {
            "type": "object",
            "properties": {
                "county": {"type": "string"},
                "state": {"type": "string"},
                "lat": {"type": "number"},
                "lng": {"type": "number"},
            },
            "required": ["county", "lat", "lng"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "county": {"type": "string"},
                "state": {"type": "string"},
                "parcels_dataset": {"type": ["object", "null"]},
                "zoning_dataset": {"type": ["object", "null"]},
            },
        },
    },
    {
        "name": "plotlot.search_municode_live",
        "description": "Search live Municode headings for zoning sections when indexed chunks are weak or stale.",
        "risk_class": "read_only",
        "input_schema": {
            "type": "object",
            "properties": {
                "municipality": {"type": "string"},
                "query": {"type": "string"},
            },
            "required": ["municipality", "query"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "municipality": {"type": "string"},
                "source_type": {"type": "string"},
                "warnings": {"type": "array", "items": {"type": "string"}},
                "results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "heading": {"type": "string"},
                            "parent_heading": {"type": ["string", "null"]},
                            "node_id": {"type": "string"},
                            "score": {"type": "integer"},
                            "snippet": {"type": "string"},
                        },
                    },
                },
            },
        },
    },
]


@router.get("/tools")
@router.post("/tools/list", include_in_schema=False)
async def list_tools() -> dict[str, Any]:
    return {"tools": MCP_TOOLS}


@router.post("/invoke")
@router.post("/tools/invoke", include_in_schema=False)
async def invoke_tool(
    payload: MCPInvokeRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if payload.name == "plotlot.search_ordinance":
        municipality = payload.input.get("municipality")
        query = payload.input.get("query")
        if not municipality or not query:
            raise HTTPException(status_code=422, detail="municipality and query are required")
        hits = await search_ordinance_records(
            session,
            municipality=municipality,
            query=query,
            limit=int(payload.input.get("limit", 10)),
        )
        return {
            "status": "success",
            "tool": payload.name,
            "result": {"results": [hit.model_dump() for hit in hits]},
        }

    if payload.name == "plotlot.get_zoning_rules":
        municipality = payload.input.get("municipality")
        zoning_code = payload.input.get("zoning_code")
        if not municipality or not zoning_code:
            raise HTTPException(status_code=422, detail="municipality and zoning_code are required")
        rules_result = await extract_rules(
            ExtractRulesRequest(municipality=municipality, zoning_code=zoning_code),
            session,
        )
        return {"status": "success", "tool": payload.name, "result": rules_result.model_dump()}

    if payload.name == "plotlot.discover_open_data_layers":
        county = payload.input.get("county")
        lat = payload.input.get("lat")
        lng = payload.input.get("lng")
        if county is None or lat is None or lng is None:
            raise HTTPException(status_code=422, detail="county, lat, and lng are required")

        state = payload.input.get("state", "FL")
        parcels_dataset, zoning_dataset = await discover_datasets(
            float(lat),
            float(lng),
            str(county),
            str(state),
        )

        def _serialize(dataset: Any) -> dict[str, Any] | None:
            if dataset is None:
                return None
            return {
                "dataset_id": dataset.dataset_id,
                "name": dataset.name,
                "url": dataset.url,
                "layer_id": dataset.layer_id,
                "dataset_type": dataset.dataset_type,
                "county": dataset.county,
                "state": dataset.state,
                "field_count": len(dataset.fields),
                "fields_preview": dataset.fields[:15],
            }

        return {
            "status": "success",
            "tool": payload.name,
            "result": {
                "county": str(county),
                "state": str(state),
                "parcels_dataset": _serialize(parcels_dataset),
                "zoning_dataset": _serialize(zoning_dataset),
            },
        }

    if payload.name == "plotlot.search_municode_live":
        municipality = payload.input.get("municipality")
        query = payload.input.get("query")
        if not municipality or not query:
            raise HTTPException(status_code=422, detail="municipality and query are required")

        # Keep this adapter thin: reuse the same implementation used by the agent chat lane.
        from plotlot.api.chat import _execute_municode_live_search

        raw = await _execute_municode_live_search(str(municipality), str(query))
        try:
            municode_result = json.loads(raw)
        except json.JSONDecodeError:
            municode_result = {"status": "error", "message": raw}

        return {"status": "success", "tool": payload.name, "result": municode_result}

    raise HTTPException(status_code=404, detail=f"Unsupported MCP tool: {payload.name}")
