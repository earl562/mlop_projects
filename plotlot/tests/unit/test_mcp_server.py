"""Unit tests for mcp/server.py — 5 PlotLot MCP tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch

from plotlot.mcp.server import (
    get_comparable_sales,
    get_coverage,
    ingest_municipality,
    mcp,
    run_full_analysis,
    search_zoning,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_search_result(section: str = "12.3", score: float = 0.85) -> MagicMock:
    r = MagicMock()
    r.section = section
    r.section_title = "Residential Density"
    r.chapter = "Chapter 12"
    r.zone_codes = ["RM-25"]
    r.score = score
    r.chunk_text = "Max density is 25 units per acre."
    r.source_url = "https://library.municode.com/search?nodeId=123"
    return r


@dataclass
class _FakeCompAnalysis:
    comparables: list = field(default_factory=list)
    median_price_per_acre: float = 120000.0
    estimated_land_value: float = 480000.0
    adv_per_unit: float = 60000.0
    confidence: float = 0.75  # matches CompAnalysis.confidence: float


# ── MCP server registration ───────────────────────────────────────────────────


def test_mcp_server_has_name():
    assert mcp.name == "plotlot"


def test_mcp_server_has_version():
    assert mcp.version == "2.1.0"


def test_mcp_instructions_have_grounding_rules():
    """Server instructions must forbid fabrication (anti-hallucination contract)."""
    instr = (mcp.instructions or "").lower()
    assert "never invent" in instr
    assert "data_status" in instr
    assert "presentation_guidance" in instr


async def test_all_five_tools_registered():
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    assert "ingest_municipality" in names
    assert "run_full_analysis" in names
    assert "search_zoning" in names
    assert "get_coverage" in names
    assert "get_comparable_sales" in names


def test_tool_functions_are_callable():
    assert callable(ingest_municipality)
    assert callable(run_full_analysis)
    assert callable(search_zoning)
    assert callable(get_coverage)
    assert callable(get_comparable_sales)


# ── ingest_municipality ───────────────────────────────────────────────────────


async def test_ingest_municipality_success():
    from plotlot.ingestion.acp_coordinator import IngestProgress

    async def _mock_run(req):
        yield IngestProgress(stage="resolving", message="Finding source…")
        yield IngestProgress(stage="fetching", message="Downloading…", chunks_total=10)
        yield IngestProgress(
            stage="complete",
            message="Done",
            chunks_done=10,
            chunks_total=10,
            complete=True,
        )

    with patch("plotlot.mcp.server.run_on_demand_ingestion", _mock_run):
        result = await ingest_municipality("Fremont", "CA", "Alameda")

    assert result["success"] is True
    assert result["chunks_stored"] == 10
    assert result["municipality"] == "Fremont"
    assert result["state"] == "CA"
    assert result["error"] is None
    assert len(result["progress"]) == 3


async def test_ingest_municipality_no_adapter():
    from plotlot.ingestion.acp_coordinator import IngestProgress

    async def _mock_run(req):
        yield IngestProgress(
            stage="error",
            message="No adapter found",
            error="no_adapter",
            complete=True,
        )

    with patch("plotlot.mcp.server.run_on_demand_ingestion", _mock_run):
        result = await ingest_municipality("Unknown City", "ZZ")

    assert result["success"] is False
    assert result["chunks_stored"] == 0
    assert result["error"] == "no_adapter"


async def test_ingest_municipality_state_uppercased():
    """state is uppercased in the returned dict."""
    from plotlot.ingestion.acp_coordinator import IngestProgress

    async def _mock_run(req):
        yield IngestProgress(stage="complete", message="Done", chunks_done=5, complete=True)

    with patch("plotlot.mcp.server.run_on_demand_ingestion", _mock_run):
        result = await ingest_municipality("Fremont", "ca")

    assert result["state"] == "CA"


async def test_ingest_municipality_empty_events_handled():
    """If the generator yields nothing, success must be False."""

    async def _empty_run(req):
        return
        yield  # make it an async generator

    with patch("plotlot.mcp.server.run_on_demand_ingestion", _empty_run):
        result = await ingest_municipality("Ghost Town", "TX")

    assert result["success"] is False
    assert result["chunks_stored"] == 0


async def test_ingest_municipality_passes_county():
    from plotlot.ingestion.acp_coordinator import IngestProgress

    captured: dict = {}

    async def _mock_run(req):
        captured["county"] = req.county
        yield IngestProgress(stage="complete", message="Done", chunks_done=3, complete=True)

    with patch("plotlot.mcp.server.run_on_demand_ingestion", _mock_run):
        await ingest_municipality("Oakland", "CA", county="Alameda")

    assert captured["county"] == "Alameda"


# ── run_full_analysis ─────────────────────────────────────────────────────────

_FULL_RAW = {
    "municipality": "Fremont",
    "county": "Alameda",
    "zoning_district": "RM-25",
    "zoning_description": "Multi-Family Residential",
    "confidence": "high",
    "numeric_params": {
        "max_density_units_per_acre": 25.0,
        "max_height_ft": 45.0,
        "far": 2.0,
        "setback_front_ft": 15.0,
        "setback_side_ft": 5.0,
        "setback_rear_ft": 20.0,
        "min_lot_area_per_unit_sqft": 6000.0,
    },
    "density_analysis": {"max_units": 8, "governing_constraint": "density"},
    "pro_forma": {"max_land_price": 850000.0, "cost_per_door": 106250.0},
}


async def test_run_full_analysis_success():
    mock_report = MagicMock()

    with (
        patch("plotlot.mcp.server.lookup_address", AsyncMock(return_value=mock_report)),
        patch("plotlot.mcp.server.asdict", return_value=_FULL_RAW),
    ):
        result = await run_full_analysis("123 Main St, Fremont CA")

    assert result["municipality"] == "Fremont"
    assert result["zoning_district"] == "RM-25"
    assert result["max_density_units_per_acre"] == 25.0
    assert result["max_units"] == 8
    assert result["max_land_price"] == 850000.0
    assert "full_report" in result


async def test_run_full_analysis_none_report():
    with patch("plotlot.mcp.server.lookup_address", AsyncMock(return_value=None)):
        result = await run_full_analysis("999 Nowhere St")

    assert "error" in result
    assert result["address"] == "999 Nowhere St"


async def test_run_full_analysis_exception_returns_error_dict():
    with patch(
        "plotlot.mcp.server.lookup_address",
        AsyncMock(side_effect=RuntimeError("geocode API down")),
    ):
        result = await run_full_analysis("123 Main St")

    assert "error" in result
    assert "geocode API down" in result["error"]
    assert result["address"] == "123 Main St"


async def test_run_full_analysis_missing_optional_fields():
    """None numeric_params / density_analysis / pro_forma must not crash."""
    raw = {
        "municipality": "Empty Town",
        "county": "Nowhere",
        "zoning_district": None,
        "zoning_description": None,
        "confidence": "low",
        "numeric_params": None,
        "density_analysis": None,
        "pro_forma": None,
    }

    with (
        patch("plotlot.mcp.server.lookup_address", AsyncMock(return_value=MagicMock())),
        patch("plotlot.mcp.server.asdict", return_value=raw),
    ):
        result = await run_full_analysis("1 Empty Rd")

    assert result["municipality"] == "Empty Town"
    assert result["max_units"] is None
    assert result["max_land_price"] is None


# ── run_full_analysis: data_status anti-hallucination contract ────────────────


async def test_run_full_analysis_full_coverage_data_status():
    """When numeric standards are present, coverage is 'full'."""
    raw = dict(_FULL_RAW, sources=["12.3 — Residential Density"])
    with (
        patch("plotlot.mcp.server.lookup_address", AsyncMock(return_value=MagicMock())),
        patch("plotlot.mcp.server.asdict", return_value=raw),
    ):
        result = await run_full_analysis("123 Main St, Fremont CA")

    ds = result["data_status"]
    assert ds["coverage"] == "full"
    assert ds["zoning_district_found"] is True
    assert ds["dimensional_standards_found"] is True
    assert ds["max_units_computed"] is True
    assert "presentation_guidance" in result


async def test_run_full_analysis_zoning_only_coverage_and_guidance():
    """Zoning code present but NO dimensional standards → 'zoning_only' + honest guidance.

    This is the Las Vegas / un-ingested-city case that previously caused the agent
    to hallucinate a 'could not be retrieved' message with a fake phone number.
    """
    raw = {
        "municipality": "Las Vegas",
        "county": "Clark",
        "zoning_district": "RS20",
        "zoning_description": "Residential Single-Family 20",
        "confidence": "low",
        "numeric_params": {
            "max_density_units_per_acre": None,
            "min_lot_area_per_unit_sqft": None,
            "far": None,
            "max_height_ft": None,
            "setback_front_ft": None,
            "setback_side_ft": None,
            "setback_rear_ft": None,
            "property_type": "single_family",
        },
        "density_analysis": {"max_units": 0, "governing_constraint": "insufficient_data"},
        "pro_forma": None,
        "sources": [],
    }
    with (
        patch("plotlot.mcp.server.lookup_address", AsyncMock(return_value=MagicMock())),
        patch("plotlot.mcp.server.asdict", return_value=raw),
    ):
        result = await run_full_analysis("2975 Montessouri St, Las Vegas, NV 89117")

    # The zoning district MUST be surfaced — not hidden behind a "not found" message.
    assert result["zoning_district"] == "RS20"
    ds = result["data_status"]
    assert ds["coverage"] == "zoning_only"
    assert ds["zoning_district_found"] is True
    assert ds["dimensional_standards_found"] is False
    assert ds["max_units_computed"] is False

    guidance = result["presentation_guidance"].lower()
    assert "rs20" in guidance  # district echoed so the agent states it
    assert "not" in guidance and "fabricate" in guidance  # forbids invention
    assert "ingest_municipality" in guidance  # offers the remedy


async def test_run_full_analysis_no_zoning_coverage_none():
    """No zoning district resolved at all → coverage 'none', no invented code."""
    raw = {
        "municipality": "Nowhere",
        "county": "Nowhere",
        "zoning_district": "",
        "zoning_description": "",
        "confidence": "low",
        "numeric_params": None,
        "density_analysis": None,
        "pro_forma": None,
        "sources": [],
    }
    with (
        patch("plotlot.mcp.server.lookup_address", AsyncMock(return_value=MagicMock())),
        patch("plotlot.mcp.server.asdict", return_value=raw),
    ):
        result = await run_full_analysis("999 Nowhere Rd")

    ds = result["data_status"]
    assert ds["coverage"] == "none"
    assert ds["zoning_district_found"] is False
    assert "invent" in result["presentation_guidance"].lower()


# ── search_zoning ─────────────────────────────────────────────────────────────


async def test_search_zoning_returns_results():
    mock_results = [_make_search_result("12.3", 0.92), _make_search_result("12.5", 0.77)]
    mock_session = MagicMock()
    mock_session.close = AsyncMock()

    with (
        patch("plotlot.mcp.server.get_session", AsyncMock(return_value=mock_session)),
        patch("plotlot.mcp.server.hybrid_search", AsyncMock(return_value=mock_results)),
    ):
        result = await search_zoning("Fremont", "density limit")

    assert result["municipality"] == "Fremont"
    assert result["query"] == "density limit"
    assert result["result_count"] == 2
    assert result["results"][0]["section"] == "12.3"
    assert result["results"][0]["score"] == 0.92


async def test_search_zoning_empty_results():
    mock_session = MagicMock()
    mock_session.close = AsyncMock()

    with (
        patch("plotlot.mcp.server.get_session", AsyncMock(return_value=mock_session)),
        patch("plotlot.mcp.server.hybrid_search", AsyncMock(return_value=[])),
    ):
        result = await search_zoning("Unknown Town", "setbacks")

    assert result["result_count"] == 0
    assert result["results"] == []
    assert "error" not in result


async def test_search_zoning_db_error_returns_error_dict():
    mock_session = MagicMock()
    mock_session.close = AsyncMock()

    with (
        patch("plotlot.mcp.server.get_session", AsyncMock(return_value=mock_session)),
        patch(
            "plotlot.mcp.server.hybrid_search",
            AsyncMock(side_effect=RuntimeError("DB offline")),
        ),
    ):
        result = await search_zoning("Fremont", "density")

    assert "error" in result
    assert result["results"] == []


async def test_search_zoning_limit_clamped_to_25():
    mock_session = MagicMock()
    mock_session.close = AsyncMock()
    captured: dict = {}

    async def _mock_search(session, muni, query, limit):
        captured["limit"] = limit
        return []

    with (
        patch("plotlot.mcp.server.get_session", AsyncMock(return_value=mock_session)),
        patch("plotlot.mcp.server.hybrid_search", _mock_search),
    ):
        await search_zoning("Fremont", "test", limit=100)

    assert captured["limit"] == 25


async def test_search_zoning_limit_clamped_to_1():
    mock_session = MagicMock()
    mock_session.close = AsyncMock()
    captured: dict = {}

    async def _mock_search(session, muni, query, limit):
        captured["limit"] = limit
        return []

    with (
        patch("plotlot.mcp.server.get_session", AsyncMock(return_value=mock_session)),
        patch("plotlot.mcp.server.hybrid_search", _mock_search),
    ):
        await search_zoning("Fremont", "test", limit=0)

    assert captured["limit"] == 1


async def test_search_zoning_result_has_all_fields():
    mock_session = MagicMock()
    mock_session.close = AsyncMock()

    with (
        patch("plotlot.mcp.server.get_session", AsyncMock(return_value=mock_session)),
        patch(
            "plotlot.mcp.server.hybrid_search",
            AsyncMock(return_value=[_make_search_result()]),
        ),
    ):
        result = await search_zoning("Fremont", "density")

    r = result["results"][0]
    for fld in (
        "section",
        "section_title",
        "chapter",
        "zone_codes",
        "score",
        "chunk_text",
        "source_url",
    ):
        assert fld in r, f"missing field: {fld}"


# ── get_coverage ──────────────────────────────────────────────────────────────


async def test_get_coverage_returns_summary():
    row1 = MagicMock()
    row1.municipality = "Fremont"
    row1.county = "Alameda"
    row1.state = "CA"
    row1.chunks = 1500

    row2 = MagicMock()
    row2.municipality = "San Jose"
    row2.county = "Santa Clara"
    row2.state = "CA"
    row2.chunks = 1200

    mock_result = MagicMock()
    mock_result.fetchall = MagicMock(return_value=[row1, row2])

    mock_session = MagicMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.close = AsyncMock()

    with patch("plotlot.mcp.server.get_session", AsyncMock(return_value=mock_session)):
        result = await get_coverage()

    assert result["total_municipalities"] == 2
    assert result["total_chunks"] == 2700
    assert result["municipalities"][0]["municipality"] == "Fremont"
    assert result["municipalities"][0]["chunks"] == 1500


async def test_get_coverage_empty_database():
    mock_result = MagicMock()
    mock_result.fetchall = MagicMock(return_value=[])

    mock_session = MagicMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.close = AsyncMock()

    with patch("plotlot.mcp.server.get_session", AsyncMock(return_value=mock_session)):
        result = await get_coverage()

    assert result["total_municipalities"] == 0
    assert result["total_chunks"] == 0
    assert result["municipalities"] == []


async def test_get_coverage_db_error_returns_error_dict():
    mock_session = MagicMock()
    mock_session.execute = AsyncMock(side_effect=RuntimeError("DB offline"))
    mock_session.close = AsyncMock()

    with patch("plotlot.mcp.server.get_session", AsyncMock(return_value=mock_session)):
        result = await get_coverage()

    assert "error" in result
    assert result["municipalities"] == []


async def test_get_coverage_municipality_fields():
    row = MagicMock()
    row.municipality = "Oakland"
    row.county = "Alameda"
    row.state = "CA"
    row.chunks = 800

    mock_result = MagicMock()
    mock_result.fetchall = MagicMock(return_value=[row])

    mock_session = MagicMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.close = AsyncMock()

    with patch("plotlot.mcp.server.get_session", AsyncMock(return_value=mock_session)):
        result = await get_coverage()

    m = result["municipalities"][0]
    assert m["municipality"] == "Oakland"
    assert m["county"] == "Alameda"
    assert m["state"] == "CA"
    assert m["chunks"] == 800


# ── get_comparable_sales ──────────────────────────────────────────────────────


async def test_get_comparable_sales_success():
    comp_result = _FakeCompAnalysis()

    with patch("plotlot.mcp.server.find_comparables", AsyncMock(return_value=comp_result)):
        result = await get_comparable_sales(37.5, -122.0, county="San Mateo", state="CA")

    assert result["lat"] == 37.5
    assert result["lng"] == -122.0
    assert result["state"] == "CA"
    assert result["county"] == "San Mateo"
    assert result["median_price_per_acre"] == 120000.0
    assert result["estimated_land_value"] == 480000.0
    assert result["comparable_count"] == 0
    assert "error" not in result


async def test_get_comparable_sales_requires_county():
    # Empty county is why this tool always returned nothing before — now it's a
    # clear error instead of a silent empty result.
    result = await get_comparable_sales(37.5, -122.0, county="", state="CA")
    assert "error" in result
    assert "county" in result["error"]
    assert result["comparables"] == []


async def test_get_comparable_sales_exception_returns_error():
    with patch(
        "plotlot.mcp.server.find_comparables",
        AsyncMock(side_effect=RuntimeError("ArcGIS timeout")),
    ):
        result = await get_comparable_sales(25.7, -80.2, county="Miami-Dade", state="FL")

    assert "error" in result
    assert "ArcGIS timeout" in result["error"]
    assert result["comparables"] == []


async def test_get_comparable_sales_default_state_is_fl():
    comp_result = _FakeCompAnalysis()
    captured: dict = {}

    async def _mock_comps(prop, state):
        captured["state"] = state
        return comp_result

    with patch("plotlot.mcp.server.find_comparables", _mock_comps):
        await get_comparable_sales(25.7, -80.2, county="Miami-Dade")

    assert captured["state"] == "FL"


async def test_get_comparable_sales_result_fields():
    comp_result = _FakeCompAnalysis()

    with patch("plotlot.mcp.server.find_comparables", AsyncMock(return_value=comp_result)):
        result = await get_comparable_sales(37.5, -122.0, county="San Mateo")

    for fld in (
        "lat",
        "lng",
        "state",
        "comparable_count",
        "median_price_per_acre",
        "estimated_land_value",
        "adv_per_unit",
        "confidence",
        "comparables",
    ):
        assert fld in result, f"missing field: {fld}"


# ── Tool metadata ─────────────────────────────────────────────────────────────


async def test_tools_have_descriptions():
    tools = await mcp.list_tools()
    for tool in tools:
        assert tool.description, f"Tool {tool.name!r} has no description"


async def test_tool_input_schemas_present():
    """Every tool must expose a parameters schema."""
    tools = await mcp.list_tools()
    for tool in tools:
        # fastmcp exposes the JSON schema via to_mcp_tool()
        mcp_tool = tool.to_mcp_tool()
        assert mcp_tool.inputSchema is not None, f"Tool {tool.name!r} has no inputSchema"


# ── Entry point & config files ────────────────────────────────────────────────


def test_run_function_exists():
    from plotlot.mcp.server import run

    assert callable(run)


def test_mcp_json_exists():
    from pathlib import Path

    mcp_json = Path(__file__).parents[2] / ".mcp.json"
    assert mcp_json.exists(), f".mcp.json not found at {mcp_json}"


def test_mcp_json_has_plotlot_server():
    import json
    from pathlib import Path

    mcp_json = Path(__file__).parents[2] / ".mcp.json"
    config = json.loads(mcp_json.read_text())
    assert "mcpServers" in config
    assert "plotlot" in config["mcpServers"]
    server = config["mcpServers"]["plotlot"]
    assert server["type"] == "stdio"
    assert "plotlot-mcp" in server["args"]
