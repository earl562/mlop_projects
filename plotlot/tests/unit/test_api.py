"""Unit tests for the PlotLot API endpoints.

Uses httpx.AsyncClient with ASGITransport to test FastAPI endpoints
without starting a real server. Pipeline is mocked to avoid real API/DB calls.
"""

import json
from dataclasses import asdict
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from plotlot.api.main import app
from plotlot.core.types import (
    ConstraintResult,
    DensityAnalysis,
    NumericZoningParams,
    PropertyRecord,
    Setbacks,
    ZoningReport,
)


def _mock_report() -> ZoningReport:
    """Build a realistic mock ZoningReport."""
    return ZoningReport(
        address="171 NE 209th Ter, Miami, FL 33179",
        formatted_address="171 NE 209th Ter, Miami Gardens, FL 33179",
        municipality="Miami Gardens",
        county="Miami-Dade",
        lat=25.957,
        lng=-80.199,
        zoning_district="R-1",
        zoning_description="Single-Family Residential",
        allowed_uses=["Single-family dwelling"],
        conditional_uses=["Home occupation"],
        prohibited_uses=[],
        setbacks=Setbacks(front="25 ft", side="7.5 ft", rear="25 ft"),
        max_height="35 ft / 2 stories",
        max_density="6 units per acre",
        floor_area_ratio="0.50",
        lot_coverage="40%",
        min_lot_size="7,500 sq ft",
        parking_requirements="2 spaces per dwelling unit",
        property_record=PropertyRecord(
            folio="3422120000010",
            address="171 NE 209TH TER",
            municipality="Miami Gardens",
            county="Miami-Dade",
            zoning_code="R-1",
            lot_size_sqft=7500.0,
            lot_dimensions="75 x 100",
            bedrooms=3,
            bathrooms=2.0,
            year_built=1965,
        ),
        numeric_params=NumericZoningParams(
            max_density_units_per_acre=6.0,
            min_lot_area_per_unit_sqft=7500.0,
            setback_front_ft=25.0,
            setback_side_ft=7.5,
            setback_rear_ft=25.0,
            max_height_ft=35.0,
            max_stories=2,
        ),
        density_analysis=DensityAnalysis(
            max_units=1,
            governing_constraint="density",
            constraints=[
                ConstraintResult(
                    name="density",
                    max_units=1,
                    raw_value=1.033,
                    formula="7500 sqft * 6.0 units/acre / 43560 = 1.033",
                    is_governing=True,
                ),
            ],
            lot_size_sqft=7500.0,
            confidence="high",
        ),
        summary="Single-family residential property in Miami Gardens.",
        sources=["Sec. 34-342 — R-1 Single-Family Residential"],
        confidence="high",
    )


@pytest.fixture
def transport():
    return ASGITransport(app=app)


@pytest.fixture
async def client(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health(client):
    """Health check returns 200."""
    with patch("plotlot.api.main.get_session") as mock_session:
        session = AsyncMock()
        mock_session.return_value = session
        resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("healthy", "degraded")


@pytest.mark.asyncio
async def test_analyze_success(client):
    """Successful analysis returns full ZoningReport."""
    report = _mock_report()
    with patch("plotlot.api.routes.lookup_address", new_callable=AsyncMock, return_value=report):
        resp = await client.post(
            "/api/v1/analyze",
            json={"address": "171 NE 209th Ter, Miami, FL 33179"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["municipality"] == "Miami Gardens"
    assert data["zoning_district"] == "R-1"
    assert data["density_analysis"]["max_units"] == 1
    assert data["confidence"] == "high"


@pytest.mark.asyncio
async def test_analyze_geocode_failure(client):
    """Pipeline returning None → 422."""
    with patch("plotlot.api.routes.lookup_address", new_callable=AsyncMock, return_value=None):
        resp = await client.post(
            "/api/v1/analyze",
            json={"address": "123 Fake St, Nowhere, FL 00000"},
        )
    assert resp.status_code == 422
    assert "geocode" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_analyze_missing_address(client):
    """Missing address field → 422 validation error."""
    resp = await client.post("/api/v1/analyze", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_analyze_pipeline_error(client):
    """Pipeline exception → 502."""
    with patch(
        "plotlot.api.routes.lookup_address",
        new_callable=AsyncMock,
        side_effect=RuntimeError("LLM provider down"),
    ):
        resp = await client.post(
            "/api/v1/analyze",
            json={"address": "171 NE 209th Ter, Miami, FL 33179"},
        )
    assert resp.status_code == 502
    assert "LLM provider down" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Chat endpoint tests (Phase 5c)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_streams_response(client):
    """Chat endpoint streams tokens via SSE."""
    # Clear memory between tests
    from plotlot.api.chat import _sessions
    _sessions._conversations.clear()
    _sessions._last_access.clear()

    mock_response = {"content": "Hello there!", "tool_calls": []}
    with patch("plotlot.api.chat.call_llm", new_callable=AsyncMock, return_value=mock_response):
        resp = await client.post(
            "/api/v1/chat",
            json={
                "message": "What can I build?",
                "history": [],
                "report_context": None,
            },
        )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    body = resp.text
    assert "token" in body
    assert "done" in body


@pytest.mark.asyncio
async def test_chat_with_report_context(client):
    """Chat with report context doesn't error."""
    from plotlot.api.chat import _sessions
    _sessions._conversations.clear()
    _sessions._last_access.clear()

    report = _mock_report()
    report_dict = {
        "address": report.address,
        "formatted_address": report.formatted_address,
        "municipality": report.municipality,
        "county": report.county,
        "zoning_district": report.zoning_district,
        "zoning_description": report.zoning_description,
        "allowed_uses": report.allowed_uses,
        "conditional_uses": report.conditional_uses,
        "prohibited_uses": report.prohibited_uses,
        "setbacks": {"front": "25 ft", "side": "7.5 ft", "rear": "25 ft"},
        "max_height": report.max_height,
        "max_density": report.max_density,
        "floor_area_ratio": report.floor_area_ratio,
        "lot_coverage": report.lot_coverage,
        "min_lot_size": report.min_lot_size,
        "parking_requirements": report.parking_requirements,
        "summary": report.summary,
        "sources": report.sources,
        "confidence": report.confidence,
    }

    mock_response = {"content": "Based on the R-1 zoning...", "tool_calls": []}
    with patch("plotlot.api.chat.call_llm", new_callable=AsyncMock, return_value=mock_response):
        resp = await client.post(
            "/api/v1/chat",
            json={
                "message": "Explain the density",
                "history": [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello"}],
                "report_context": report_dict,
            },
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_chat_with_tool_use(client):
    """Chat agent uses tools and returns results."""
    from plotlot.api.chat import _sessions
    _sessions._conversations.clear()
    _sessions._last_access.clear()

    # First call: LLM wants to use a tool
    tool_response = {
        "content": "",
        "tool_calls": [{
            "id": "call_123",
            "function": {
                "name": "search_zoning_ordinance",
                "arguments": '{"municipality": "Miami Gardens", "query": "setback requirements"}',
            },
        }],
    }
    # Second call: LLM gives final answer after receiving tool results
    final_response = {"content": "The setback requirements are 25ft front...", "tool_calls": []}

    with (
        patch("plotlot.api.chat.call_llm", new_callable=AsyncMock, side_effect=[tool_response, final_response]),
        patch("plotlot.api.chat.hybrid_search", new_callable=AsyncMock, return_value=[]),
    ):
        resp = await client.post(
            "/api/v1/chat",
            json={"message": "What are the setbacks in Miami Gardens?"},
        )
    assert resp.status_code == 200
    body = resp.text
    assert "tool_use" in body
    assert "tool_result" in body
    assert "setback" in body.lower()


@pytest.mark.asyncio
async def test_chat_session_memory(client):
    """Chat preserves conversation memory across requests."""
    from plotlot.api.chat import _sessions
    _sessions._conversations.clear()
    _sessions._last_access.clear()

    mock_response = {"content": "I'll remember that!", "tool_calls": []}
    with patch("plotlot.api.chat.call_llm", new_callable=AsyncMock, return_value=mock_response):
        resp = await client.post(
            "/api/v1/chat",
            json={"message": "My name is Earl", "session_id": "test-session"},
        )
    assert resp.status_code == 200
    # Check that the session event was emitted
    assert "test-session" in resp.text
    # Memory should have the user message + assistant response
    assert len(_sessions._conversations.get("test-session", [])) == 2


# ---------------------------------------------------------------------------
# Portfolio endpoint tests (Phase 5b)
# ---------------------------------------------------------------------------

def _mock_report_dict() -> dict:
    """Build a report dict for portfolio tests."""
    return {
        "address": "171 NE 209th Ter, Miami, FL 33179",
        "formatted_address": "171 NE 209th Ter, Miami Gardens, FL 33179",
        "municipality": "Miami Gardens",
        "county": "Miami-Dade",
        "zoning_district": "R-1",
        "zoning_description": "Single-Family Residential",
        "allowed_uses": ["Single-family dwelling"],
        "conditional_uses": [],
        "prohibited_uses": [],
        "setbacks": {"front": "25 ft", "side": "7.5 ft", "rear": "25 ft"},
        "max_height": "35 ft",
        "max_density": "6 units/acre",
        "floor_area_ratio": "0.50",
        "lot_coverage": "40%",
        "min_lot_size": "7500 sqft",
        "parking_requirements": "2/unit",
        "summary": "Test summary",
        "sources": [],
        "confidence": "high",
    }


@pytest.mark.asyncio
async def test_portfolio_save_and_list(client):
    """Save an analysis and retrieve it from portfolio."""
    # Clear any existing portfolio state
    from plotlot.api.portfolio import _portfolio
    _portfolio.clear()

    report_dict = _mock_report_dict()
    resp = await client.post("/api/v1/portfolio", json={"report": report_dict})
    assert resp.status_code == 200
    saved = resp.json()
    assert saved["municipality"] == "Miami Gardens"
    assert saved["zoning_district"] == "R-1"
    assert "id" in saved

    # List
    resp = await client.get("/api/v1/portfolio")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 1
    assert items[0]["id"] == saved["id"]


@pytest.mark.asyncio
async def test_portfolio_delete(client):
    """Delete an analysis from portfolio."""
    from plotlot.api.portfolio import _portfolio
    _portfolio.clear()

    report_dict = _mock_report_dict()
    resp = await client.post("/api/v1/portfolio", json={"report": report_dict})
    analysis_id = resp.json()["id"]

    resp = await client.delete(f"/api/v1/portfolio/{analysis_id}")
    assert resp.status_code == 200

    resp = await client.get("/api/v1/portfolio")
    assert resp.json() == []


@pytest.mark.asyncio
async def test_portfolio_not_found(client):
    """Get non-existent analysis → 404."""
    resp = await client.get("/api/v1/portfolio/nonexistent")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Google Workspace tool tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_create_spreadsheet_tool(client):
    """Chat agent creates a spreadsheet via tool call."""
    from plotlot.api.chat import _sessions
    _sessions._conversations.clear()
    _sessions._last_access.clear()

    tool_response = {
        "content": "",
        "tool_calls": [{
            "id": "call_sheet",
            "function": {
                "name": "create_spreadsheet",
                "arguments": json.dumps({
                    "title": "Test Lots",
                    "headers": ["Address", "Zoning"],
                    "rows": [["123 Main St", "R-1"]],
                }),
            },
        }],
    }
    final_response = {"content": "Here's your spreadsheet!", "tool_calls": []}

    from plotlot.retrieval.google_workspace import SpreadsheetResult
    mock_result = SpreadsheetResult(
        spreadsheet_id="abc123",
        spreadsheet_url="https://docs.google.com/spreadsheets/d/abc123",
        title="Test Lots",
    )

    with (
        patch("plotlot.api.chat.call_llm", new_callable=AsyncMock, side_effect=[tool_response, final_response]),
        patch("plotlot.api.chat.create_spreadsheet", new_callable=AsyncMock, return_value=mock_result),
    ):
        resp = await client.post(
            "/api/v1/chat",
            json={"message": "Put the results in a spreadsheet"},
        )
    assert resp.status_code == 200
    body = resp.text
    assert "tool_use" in body
    assert "Creating spreadsheet" in body


@pytest.mark.asyncio
async def test_chat_create_document_tool(client):
    """Chat agent creates a document via tool call."""
    from plotlot.api.chat import _sessions
    _sessions._conversations.clear()
    _sessions._last_access.clear()

    tool_response = {
        "content": "",
        "tool_calls": [{
            "id": "call_doc",
            "function": {
                "name": "create_document",
                "arguments": json.dumps({
                    "title": "Zoning Report",
                    "content": "Analysis of R-1 zoning district...",
                }),
            },
        }],
    }
    final_response = {"content": "Created your report!", "tool_calls": []}

    from plotlot.retrieval.google_workspace import DocumentResult
    mock_result = DocumentResult(
        document_id="doc456",
        document_url="https://docs.google.com/document/d/doc456/edit",
        title="Zoning Report",
    )

    with (
        patch("plotlot.api.chat.call_llm", new_callable=AsyncMock, side_effect=[tool_response, final_response]),
        patch("plotlot.api.chat.create_document", new_callable=AsyncMock, return_value=mock_result),
    ):
        resp = await client.post(
            "/api/v1/chat",
            json={"message": "Write me a zoning report"},
        )
    assert resp.status_code == 200
    body = resp.text
    assert "tool_use" in body
    assert "Creating document" in body


# ---------------------------------------------------------------------------
# Property research tool tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_search_properties(client):
    """Agent calls search_properties and returns summary."""
    from plotlot.api.chat import _sessions
    _sessions._conversations.clear()
    _sessions._datasets.clear()
    _sessions._last_access.clear()

    tool_response = {
        "content": "",
        "tool_calls": [{
            "id": "call_search",
            "function": {
                "name": "search_properties",
                "arguments": json.dumps({
                    "county": "Miami-Dade",
                    "land_use_type": "vacant_residential",
                    "ownership_min_years": 20,
                }),
            },
        }],
    }
    final_response = {"content": "Found 3 vacant lots in Miami-Dade...", "tool_calls": []}

    mock_records = [
        {"folio": f"F{i}", "address": f"{i} MAIN ST", "city": "MIAMI",
         "county": "Miami-Dade", "owner": "OWNER", "land_use_code": "0000",
         "lot_size_sqft": 7500, "year_built": 0, "assessed_value": 50000,
         "sale_price": 25000, "sale_date": "01/01/2000", "lat": 25.9, "lng": -80.2}
        for i in range(3)
    ]

    with (
        patch("plotlot.api.chat.call_llm", new_callable=AsyncMock, side_effect=[tool_response, final_response]),
        patch("plotlot.api.chat.bulk_property_search", new_callable=AsyncMock, return_value=mock_records),
    ):
        resp = await client.post(
            "/api/v1/chat",
            json={"message": "Find vacant lots in Miami-Dade owned over 20 years"},
        )
    assert resp.status_code == 200
    body = resp.text
    assert "tool_use" in body
    assert "Searching property records" in body


@pytest.mark.asyncio
async def test_chat_export_dataset(client):
    """Agent exports dataset to Google Sheets."""
    from plotlot.api.chat import _sessions
    from plotlot.retrieval.bulk_search import DatasetInfo
    _sessions._conversations.clear()
    _sessions._datasets.clear()
    _sessions._last_access.clear()

    # Pre-populate a dataset for session "test-export"
    _sessions.set_dataset("test-export", DatasetInfo(
        records=[
            {"folio": "123", "address": "100 MAIN ST", "city": "MIAMI",
             "county": "Miami-Dade", "owner": "OWNER", "land_use_code": "0000",
             "lot_size_sqft": 7500, "year_built": 0, "assessed_value": 50000,
             "sale_price": 25000, "sale_date": "2000-01-01", "lat": 25.9, "lng": -80.2},
        ],
        search_params={"county": "Miami-Dade"},
        query_description="Vacant Residential In Miami-Dade",
        total_available=1,
        fetched_at="2026-01-01T00:00:00",
    ))
    _sessions.touch("test-export")

    tool_response = {
        "content": "",
        "tool_calls": [{
            "id": "call_export",
            "function": {
                "name": "export_dataset",
                "arguments": json.dumps({"title": "My Export"}),
            },
        }],
    }
    final_response = {"content": "Here's your spreadsheet!", "tool_calls": []}

    from plotlot.retrieval.google_workspace import SpreadsheetResult
    mock_result = SpreadsheetResult(
        spreadsheet_id="exp789",
        spreadsheet_url="https://docs.google.com/spreadsheets/d/exp789",
        title="My Export",
    )

    with (
        patch("plotlot.api.chat.call_llm", new_callable=AsyncMock, side_effect=[tool_response, final_response]),
        patch("plotlot.api.chat.create_spreadsheet", new_callable=AsyncMock, return_value=mock_result),
    ):
        resp = await client.post(
            "/api/v1/chat",
            json={"message": "Export to spreadsheet", "session_id": "test-export"},
        )
    assert resp.status_code == 200
    body = resp.text
    assert "tool_use" in body
    assert "Exporting to Google Sheets" in body
