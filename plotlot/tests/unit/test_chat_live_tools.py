"""Unit tests for live-data agent tool wrappers.

These tests are intentionally assertion-dense so small logic mutations
(wrong tool routing, missing dataset fields, heading-filter regressions)
are more likely to be caught.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from plotlot.api.chat import (
    CHAT_TOOLS,
    CORE_TOOLS,
    _get_tools_for_turn,
    _sessions,
    _execute_municode_live_search,
    _execute_open_data_discovery,
    _execute_tool,
    _execute_web_search,
    _execute_zoning_search,
    _store_harness_analysis_context,
)
from plotlot.core.types import CompAnalysis, ComparableSale, MunicodeConfig, PropertyRecord, TocNode
from plotlot.harness.default_runtime import _RUNTIME_DATASETS, _RuntimeDataset, get_default_runtime
from plotlot.harness.tool_registry import tool_exists
from plotlot.harness.web_lookup import WebLookupStatus, WebSearchResult, WebSearchResultItem
from plotlot.land_use import ToolContext
from plotlot.property.hub_discovery import DatasetInfo


class _FakeScraper:
    def __init__(self, *args, **kwargs):
        pass

    async def walk_toc(self, client, config, root_node_id, max_depth=3):
        return [
            TocNode(
                node_id="n1",
                heading="RS-8 Residential District",
                has_children=False,
                depth=1,
                parent_heading="Zoning",
            ),
            TocNode(
                node_id="n2",
                heading="Setback Requirements",
                has_children=False,
                depth=1,
                parent_heading="RS-8 Residential District",
            ),
            TocNode(
                node_id="n3",
                heading="Noise Regulations",
                has_children=False,
                depth=1,
                parent_heading="General",
            ),
        ]

    async def get_section_content(self, client, config, node_id):
        if node_id == "n2":
            return "<p>Minimum front setback 25 feet. Rear setback 15 feet.</p>"
            return "<p>RS-8 permits single-family residential uses.</p>"


def test_chat_tools_expose_live_tool_metadata():
    functions = {
        tool["function"]["name"]: tool["function"]
        for tool in CHAT_TOOLS
        if tool.get("type") == "function"
    }

    municode = functions["search_municode_live"]
    assert "Municode" in municode["description"]
    assert municode["parameters"]["required"] == ["municipality", "query"]
    assert municode["parameters"]["properties"]["municipality"]["type"] == "string"
    assert municode["parameters"]["properties"]["query"]["type"] == "string"

    open_data = functions["discover_open_data_layers"]
    assert "ArcGIS/Open Data" in open_data["description"]
    assert open_data["parameters"]["required"] == ["county", "state", "lat", "lng"]
    assert open_data["parameters"]["properties"]["county"]["type"] == "string"
    assert open_data["parameters"]["properties"]["lat"]["type"] == "number"
    assert open_data["parameters"]["properties"]["lng"]["type"] == "number"


def test_get_tools_for_turn_exposes_live_tools_in_core_runtime_set():
    _sessions._datasets.clear()

    tools = _get_tools_for_turn("session-1", "What zoning setbacks apply here?")
    names = [tool["function"]["name"] for tool in tools]

    assert "search_municode_live" in names
    assert "discover_open_data_layers" in names
    assert "search_zoning_ordinance" in names


def test_chat_tools_expose_full_harness_source_tools_with_contracts():
    chat_names = {tool["function"]["name"] for tool in CHAT_TOOLS}
    core_names = {tool["function"]["name"] for tool in CORE_TOOLS}

    for name in {
        "search_municode",
        "get_municode_section",
        "extract_ordinance_rules",
        "search_south_florida_gis",
        "find_comparables",
        "discover_rehabvaluator_video_sections",
    }:
        assert name in chat_names
        assert name in core_names
        assert tool_exists(name)


@pytest.mark.asyncio
async def test_execute_open_data_discovery_returns_serialized_datasets():
    with patch(
        "plotlot.property.hub_discovery.discover_datasets",
        new=AsyncMock(
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
    ):
        payload = json.loads(await _execute_open_data_discovery("Broward", "FL", 26.1, -80.1))

    assert payload["status"] == "success"
    assert payload["county"] == "Broward"
    assert payload["parcels_dataset"]["dataset_type"] == "parcels"
    assert payload["parcels_dataset"]["name"] == "Parcel Layer"
    assert payload["parcels_dataset"]["field_count"] == 2
    assert payload["zoning_dataset"]["dataset_type"] == "zoning"
    assert payload["zoning_dataset"]["name"] == "Zoning Layer"
    assert payload["zoning_dataset"]["fields_preview"] == ["ZONE", "DESC"]


@pytest.mark.asyncio
async def test_execute_municode_live_search_returns_matching_sections():
    config = MunicodeConfig(
        municipality="Fort Lauderdale",
        county="broward",
        client_id=1,
        product_id=2,
        job_id=3,
        zoning_node_id="root",
    )

    with (
        patch(
            "plotlot.ingestion.discovery.get_municode_configs",
            new=AsyncMock(return_value={"fort_lauderdale": config}),
        ),
        patch("plotlot.ingestion.scraper.MunicodeScraper", _FakeScraper),
    ):
        payload = json.loads(
            await _execute_municode_live_search("Fort Lauderdale", "RS-8 setbacks")
        )

    assert payload["status"] == "success"
    assert payload["municipality"] == "Fort Lauderdale"
    assert payload["source_type"] == "municode_live"
    assert len(payload["results"]) >= 1
    headings = [row["heading"] for row in payload["results"]]
    assert "Setback Requirements" in headings
    assert any("25 feet" in row["snippet"] for row in payload["results"])
    assert all(row["snippet"] for row in payload["results"])


@pytest.mark.asyncio
async def test_execute_municode_live_search_returns_no_results_when_headings_do_not_match():
    config = MunicodeConfig(
        municipality="Fort Lauderdale",
        county="broward",
        client_id=1,
        product_id=2,
        job_id=3,
        zoning_node_id="root",
    )

    with (
        patch(
            "plotlot.ingestion.discovery.get_municode_configs",
            new=AsyncMock(return_value={"fort_lauderdale": config}),
        ),
        patch("plotlot.ingestion.scraper.MunicodeScraper", _FakeScraper),
    ):
        payload = json.loads(
            await _execute_municode_live_search("Fort Lauderdale", "shipyard cranes")
        )

    assert payload["status"] == "no_results"
    assert "shipyard cranes" in payload["message"]


@pytest.mark.asyncio
async def test_execute_tool_run_deal_analysis_stores_harness_analysis_in_session(
    monkeypatch,
) -> None:
    session_id = "sess-harness-analysis"
    _sessions.delete_session(session_id)

    async def _fake_execute_full_harness_chat_tool(*_args, **_kwargs) -> str:  # noqa: ANN001
        return json.dumps(
            {
                "status": "success",
                "tool_name": "run_deal_analysis",
                "source_mode": "live",
                "evidence_ids": ["ev_1", "ev_2"],
                "active_analysis": {
                    "status": "success",
                    "analysis_origin": "harness_run",
                    "address": "45 NW 209 ST, Miami Gardens, FL 33169",
                    "zoning_code": "R-1",
                    "lot_size_sqft": 10105.0,
                    "by_right": {"max_units": 1},
                    "valuation": {"recommended_offer": 120000.0},
                },
                "payload": {
                    "artifacts": {
                        "property_record": {
                            "address": "45 NW 209 ST, Miami Gardens, FL 33169",
                            "municipality": "Miami Gardens",
                            "county": "Miami-Dade",
                            "zoning_code": "R-1",
                            "ordinance_district_code": "R-1",
                            "zoning_description": "Single-family detached residential",
                            "lot_size_sqft": 10105.0,
                            "owner": "Fixture Owner",
                        }
                    }
                },
            }
        )

    monkeypatch.setattr(
        "plotlot.api.chat.execute_full_harness_chat_tool",
        _fake_execute_full_harness_chat_tool,
    )

    payload = json.loads(
        await _execute_tool(
            "run_deal_analysis",
            {"address": "45 NW 209 ST, Miami Gardens, FL 33169"},
            session_id=session_id,
            context=ToolContext(
                workspace_id="ws_fixture",
                actor_user_id="chat_agent",
                run_id=session_id,
                live_network_allowed=True,
            ),
        )
    )

    assert payload["status"] == "success"
    stored_analysis = _sessions.get_analysis(session_id)
    assert stored_analysis is not None
    assert stored_analysis["analysis_origin"] == "harness_run"
    assert stored_analysis["valuation"]["recommended_offer"] == 120000.0
    property_context = _sessions.get_property_context(session_id)
    assert property_context is not None
    assert property_context["zoning_code"] == "R-1"
    assert _sessions.get_evidence_ids(session_id) == ["ev_1", "ev_2"]

    _sessions.delete_session(session_id)


def test_ready_harness_analysis_replaces_stale_blocked_session_analysis() -> None:
    session_id = "sess-ready-replaces-blocked"
    _sessions.delete_session(session_id)
    _sessions.set_analysis(
        session_id,
        {
            "status": "blocked",
            "address": "623 4TH ST, West Palm Beach, FL 33401",
            "evaluation_readiness": {"status": "blocked"},
        },
    )
    ready_analysis = {
        "status": "ready",
        "analysis_origin": "harness_run",
        "address": "623 4TH ST, West Palm Beach, FL 33401",
        "zoning_code": "NWD-R (city)",
        "by_right": {"max_units": 2},
        "valuation": {"recommended_offer": 196000.0},
        "evaluation_readiness": {"status": "ready"},
    }

    _store_harness_analysis_context(
        session_id,
        {
            "evidence_ids": ["ev_parcel", "ev_zoning"],
            "active_analysis": ready_analysis,
            "payload": {
                "artifacts": {
                    "property_record": {
                        "address": "623 4TH ST, West Palm Beach, FL 33401",
                        "municipality": "West Palm Beach",
                        "county": "Palm Beach",
                        "zoning_code": "NWD-R (city)",
                    }
                }
            },
        },
    )

    assert _sessions.get_analysis(session_id) == ready_analysis
    _sessions.delete_session(session_id)


@pytest.mark.asyncio
async def test_zoning_search_no_results_echoes_known_zoning_code_and_forbids_fabrication():
    """Regression: un-indexed RS20 must surface the code + ban fabricated contacts.

    Previously the agent invented a Clark County phone number and said the zoning
    "could not be retrieved" — even though lookup_property_info had returned RS20.
    """
    session_id = "sess-vegas"
    _sessions.set_property_context(
        session_id,
        {
            "address": "2975 Montessouri St",
            "municipality": "Las Vegas",
            "county": "Clark",
            "zoning_code": "RS20",
            "zoning_description": "Residential Single-Family 20",
            "lot_size_sqft": 23522.0,
        },
    )
    fake_session = AsyncMock()
    fake_session.close = AsyncMock()

    with (
        patch("plotlot.harness.ordinance_lookup.get_session", AsyncMock(return_value=fake_session)),
        patch("plotlot.harness.ordinance_lookup.hybrid_search", AsyncMock(return_value=[])),
    ):
        payload = json.loads(
            await _execute_zoning_search("Las Vegas", "RS20 setbacks", session_id=session_id)
        )

    assert payload["status"] == "no_results"
    assert payload["known_zoning_code"] == "RS20"
    guidance = payload["presentation_guidance"].lower()
    assert "rs20" in guidance
    assert "not yet indexed" in guidance or "not yet in the plotlot database" in guidance
    assert "never fabricate" in guidance
    # The guidance must instruct AGAINST the "could not be retrieved" phrasing.
    assert "do not say the zoning could not be retrieved" in guidance
    _sessions.delete_session(session_id)


@pytest.mark.asyncio
async def test_zoning_search_no_results_without_session_still_forbids_fabrication():
    """No session context → still honest, still bans fabricated phone numbers/URLs."""
    fake_session = AsyncMock()
    fake_session.close = AsyncMock()

    with (
        patch("plotlot.harness.ordinance_lookup.get_session", AsyncMock(return_value=fake_session)),
        patch("plotlot.harness.ordinance_lookup.hybrid_search", AsyncMock(return_value=[])),
    ):
        payload = json.loads(await _execute_zoning_search("Nowhere", "R-1 setbacks"))

    assert payload["status"] == "no_results"
    assert payload["known_zoning_code"] == ""
    assert "never fabricate" in payload["presentation_guidance"].lower()


@pytest.mark.asyncio
async def test_execute_tool_passes_session_id_to_zoning_search():
    """The dispatcher must thread session_id so the no-results guidance can echo zoning."""
    captured: dict = {}

    async def _spy(municipality, query, session_id=""):
        captured["session_id"] = session_id
        return json.dumps({"status": "no_results", "results": []})

    with patch("plotlot.api.chat._execute_zoning_search", _spy):
        await _execute_tool(
            "search_zoning_ordinance",
            {"municipality": "Las Vegas", "query": "RS20"},
            session_id="sess-xyz",
        )

    assert captured["session_id"] == "sess-xyz"


@pytest.mark.asyncio
async def test_execute_tool_routes_zoning_search_through_shared_runtime_when_context_present():
    session_id = "sess-zoning-runtime"
    _sessions.set_property_context(
        session_id,
        {
            "zoning_code": "RS20",
            "ordinance_district_code": "R-E",
        },
    )
    captured: dict = {}

    async def _fake_harness_tool(tool_name, args, *, context, session_id):
        captured["tool_name"] = tool_name
        captured["tool_args"] = args
        captured["run_id"] = context.run_id if context is not None else ""
        return json.dumps(
            {
                "status": "success",
                "payload": {
                    "status": "no_results",
                    "known_zoning_code": args["known_zoning_code"],
                    "zone_code_boost": args["zone_code_boost"],
                },
            }
        )

    context = ToolContext(
        workspace_id="ws_fixture",
        actor_user_id="analyst_fixture",
        run_id="run_chat_zoning_search",
        risk_budget_cents=0,
    )
    try:
        with patch("plotlot.api.chat.execute_full_harness_chat_tool", new=_fake_harness_tool):
            payload = json.loads(
                await _execute_tool(
                    "search_zoning_ordinance",
                    {"municipality": "Las Vegas", "query": "RS20 setbacks"},
                    session_id=session_id,
                    context=context,
                )
            )
    finally:
        _sessions.delete_session(session_id)

    assert captured["tool_name"] == "search_zoning_ordinance"
    assert captured["run_id"] == "run_chat_zoning_search"
    assert captured["tool_args"]["municipality"] == "Las Vegas"
    assert captured["tool_args"]["query"] == "RS20 setbacks"
    assert captured["tool_args"]["known_zoning_code"] == "RS20"
    assert captured["tool_args"]["zone_code_boost"] == "R-E"
    assert payload["known_zoning_code"] == "RS20"
    assert payload["zone_code_boost"] == "R-E"


@pytest.mark.asyncio
async def test_default_runtime_zoning_search_no_results_matches_chat_guidance():
    fake_session = AsyncMock()
    fake_session.close = AsyncMock()
    captured: dict = {}

    async def _fake_hybrid_search(
        session,
        municipality: str,
        zone_code: str,
        limit: int = 10,
        zone_code_boost: str | None = None,
    ):
        captured["municipality"] = municipality
        captured["zone_code"] = zone_code
        captured["limit"] = limit
        captured["zone_code_boost"] = zone_code_boost
        return []

    context = ToolContext(
        workspace_id="ws_fixture",
        actor_user_id="analyst_fixture",
        run_id="run_runtime_zoning_search",
        risk_budget_cents=0,
    )
    with (
        patch("plotlot.harness.ordinance_lookup.get_session", AsyncMock(return_value=fake_session)),
        patch("plotlot.harness.ordinance_lookup.hybrid_search", new=_fake_hybrid_search),
    ):
        result = await get_default_runtime().call_tool(
            tool_name="search_zoning_ordinance",
            tool_args={
                "municipality": "Las Vegas",
                "query": "RS20 setbacks",
                "known_zoning_code": "RS20",
                "zone_code_boost": "R-E",
            },
            context=context,
        )

    assert result.status == "ok"
    assert result.result is not None
    assert captured == {
        "municipality": "Las Vegas",
        "zone_code": "RS20 setbacks",
        "limit": 8,
        "zone_code_boost": "R-E",
    }
    assert result.result["status"] == "no_results"
    assert result.result["known_zoning_code"] == "RS20"
    guidance = result.result["presentation_guidance"].lower()
    assert "rs20" in guidance
    assert "not yet indexed" in guidance
    assert "do not say the zoning could not be retrieved" in guidance
    assert "never fabricate" in guidance


@pytest.mark.asyncio
async def test_execute_tool_routes_new_live_tools():
    context = ToolContext(
        workspace_id="ws_fixture",
        actor_user_id="analyst_fixture",
        run_id="run_chat_live_tools",
        risk_budget_cents=100,
        live_network_allowed=True,
    )
    with (
        patch(
            "plotlot.api.chat.execute_full_harness_chat_tool",
            new=AsyncMock(
                side_effect=[
                    json.dumps(
                        {"status": "success", "payload": {"status": "success", "kind": "open_data"}}
                    ),
                    json.dumps(
                        {"status": "success", "payload": {"status": "success", "kind": "municode"}}
                    ),
                ]
            ),
        ),
    ):
        open_data_payload = json.loads(
            await _execute_tool(
                "discover_open_data_layers",
                {"county": "Broward", "state": "FL", "lat": 26.1, "lng": -80.1},
                session_id="s1",
                context=context,
            )
        )
        municode_payload = json.loads(
            await _execute_tool(
                "search_municode_live",
                {"municipality": "Fort Lauderdale", "query": "RS-8 setbacks"},
                session_id="s1",
                context=context,
            )
        )

    assert open_data_payload["kind"] == "open_data"
    assert municode_payload["kind"] == "municode"


@pytest.mark.asyncio
async def test_default_runtime_property_lookup_adds_crosswalked_next_step():
    async def _fake_lookup_property(
        address: str,
        county: str,
        *,
        lat: float,
        lng: float,
        state: str = "",
    ) -> PropertyRecord:
        return PropertyRecord(
            folio="123",
            address=address,
            municipality="Las Vegas",
            county=county,
            owner="Fixture Owner",
            zoning_code="RS20",
            zoning_description="Residential Single-Family 20",
            lot_size_sqft=23522.0,
            lot_size_source="assessor",
            lat=lat,
            lng=lng,
        )

    context = ToolContext(
        workspace_id="ws_fixture",
        actor_user_id="analyst_fixture",
        run_id="run_runtime_property_lookup",
        risk_budget_cents=0,
    )
    with patch("plotlot.retrieval.property.lookup_property", new=_fake_lookup_property):
        result = await get_default_runtime().call_tool(
            tool_name="lookup_property_info",
            tool_args={
                "address": "2975 Montessouri St, Las Vegas, NV",
                "county": "Clark",
                "state": "NV",
                "lat": 36.0,
                "lng": -115.0,
            },
            context=context,
        )

    assert result.status == "ok"
    assert result.result is not None
    payload = result.result["result"]
    assert payload["zoning_code"] == "RS20"
    assert payload["lot_size_source"] == "assessor"
    assert payload["ordinance_district_code"] == "R-E"
    assert "search under 'R-E', not 'RS20'" in payload["next_step"]
    assert result.result["evidence"][0]["payload"]["zoning_code"] == "RS20"


@pytest.mark.asyncio
async def test_execute_tool_routes_property_lookup_through_shared_runtime_when_context_present():
    session_id = "sess-property-runtime"
    _sessions.set_geocode(session_id, {"lat": 36.123456, "lng": -115.123456, "state": "NV"})
    captured: dict = {}

    async def _fake_harness_tool(tool_name, args, *, context, session_id):
        captured["tool_name"] = tool_name
        captured["tool_args"] = args
        captured["run_id"] = context.run_id if context is not None else ""
        return json.dumps(
            {
                "status": "success",
                "payload": {
                    "status": "success",
                    "result": {
                        "address": "2975 Montessouri St",
                        "municipality": "Las Vegas",
                        "county": "Clark",
                        "owner": "Fixture Owner",
                        "zoning_code": "RS20",
                        "ordinance_district_code": "R-E",
                        "zoning_description": "Residential Single-Family 20",
                        "lot_size_sqft": 23522.0,
                    },
                    "evidence": [{"id": "ev_property_fixture"}],
                },
            }
        )

    context = ToolContext(
        workspace_id="ws_fixture",
        actor_user_id="analyst_fixture",
        run_id="run_chat_property_lookup",
        risk_budget_cents=0,
    )
    with patch("plotlot.api.chat.execute_full_harness_chat_tool", new=_fake_harness_tool):
        payload = json.loads(
            await _execute_tool(
                "lookup_property_info",
                {
                    "address": "2975 Montessouri St",
                    "county": "Clark",
                    "lat": 36.0,
                    "lng": -115.0,
                },
                session_id=session_id,
                context=context,
            )
        )

    assert captured["tool_name"] == "lookup_property_info"
    assert captured["run_id"] == "run_chat_property_lookup"
    assert captured["tool_args"]["lat"] == 36.123456
    assert captured["tool_args"]["lng"] == -115.123456
    assert captured["tool_args"]["state"] == "NV"
    assert payload["result"]["zoning_code"] == "RS20"
    stored = _sessions.get_property_context(session_id)
    assert stored is not None
    assert stored["zoning_code"] == "RS20"
    assert stored["ordinance_district_code"] == "R-E"
    _sessions.delete_session(session_id)


@pytest.mark.asyncio
async def test_execute_tool_routes_full_harness_source_tool_through_router():
    payload = json.loads(
        await _execute_tool(
            "search_municode",
            {"jurisdiction": "miami", "query": "parking"},
            session_id="sess-harness",
        )
    )

    assert payload["status"] == "success"
    assert payload["tool_name"] == "search_municode"
    assert payload["payload"]["results"][0]["section_id"] == "municode_miami_parking_fixture"
    assert [event["type"] for event in payload["events"]] == [
        "tool.requested",
        "tool.policy_checked",
        "tool.started",
        "tool.completed",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "args", "assertion"),
    [
        (
            "search_south_florida_gis",
            {"query": "zoning", "county": "Broward"},
            lambda payload: payload["payload"]["results"][0]["provider"] == "broward_geohub",
        ),
        (
            "discover_rehabvaluator_video_sections",
            {"url": "https://www.youtube.com/watch?v=0IS1iFMJ8sQ"},
            lambda payload: payload["payload"]["videos"][0]["platform_video_id"] == "0IS1iFMJ8sQ",
        ),
        (
            "run_residual_land_value",
            {
                "as_built_value": 1_235_000,
                "desired_profit": 150_000,
                "hard_costs": 600_000,
                "soft_costs": 90_000,
                "contingency": 60_000,
                "developer_fee": 30_000,
                "closing_costs": 15_000,
                "financing_costs": 40_000,
                "holding_costs": 20_000,
                "selling_costs": 35_000,
                "asking_price": 175_000,
            },
            lambda payload: payload["payload"]["max_supportable_land_price"] == 195000.0,
        ),
    ],
)
async def test_execute_tool_routes_additional_full_harness_tools_through_router(
    tool_name: str,
    args: dict[str, object],
    assertion,
):
    payload = json.loads(await _execute_tool(tool_name, args, session_id="sess-harness"))

    assert payload["status"] == "success"
    assert payload["tool_name"] == tool_name
    assert [event["type"] for event in payload["events"]] == [
        "tool.requested",
        "tool.policy_checked",
        "tool.started",
        "tool.completed",
    ]
    assert assertion(payload)


@pytest.mark.asyncio
async def test_execute_tool_routes_find_comparables_through_shared_router():
    comp_analysis = CompAnalysis(
        comparables=[
            ComparableSale(
                address="100 Comp Ave",
                sale_price=210000,
                sale_date="2026-01-15",
                lot_size_sqft=8000,
                zoning_code="RU-1",
                distance_miles=0.4,
                price_per_acre=1143450.0,
            )
        ],
        unit_comparables=[
            ComparableSale(
                address="200 Built Ave",
                sale_price=950000,
                sale_date="2026-02-10",
                lot_size_sqft=10000,
                zoning_code="T6-8",
                distance_miles=0.8,
                price_per_unit=237500.0,
            )
        ],
        median_price_per_acre=1143450.0,
        estimated_land_value=210000.0,
        adv_per_unit=237500.0,
        adv_source="comps",
        confidence=0.8,
    )

    with patch(
        "plotlot.harness.tool_router_handlers.find_comparables",
        new=AsyncMock(return_value=comp_analysis),
    ):
        payload = json.loads(
            await _execute_tool(
                "find_comparables",
                {
                    "address": "123 Example St",
                    "county": "Miami-Dade",
                    "municipality": "Miami",
                    "state": "FL",
                    "lat": 25.7617,
                    "lng": -80.1918,
                    "lot_size_sqft": 8000,
                    "zoning_code": "T6-8",
                },
                session_id="sess-harness",
            )
        )

    assert payload["status"] == "success"
    assert payload["tool_name"] == "find_comparables"
    assert payload["payload"]["analysis"]["adv_per_unit"] == 237500.0
    assert payload["payload"]["analysis"]["comparables"][0]["evidence_id"]
    assert payload["payload"]["analysis"]["unit_comparables"][0]["evidence_id"]
    assert len(payload["payload"]["evidence"]) == 2
    assert [event["type"] for event in payload["events"]] == [
        "tool.requested",
        "tool.policy_checked",
        "tool.started",
        "tool.completed",
    ]


@pytest.mark.asyncio
async def test_execute_tool_routes_full_harness_export_through_policy_gate():
    payload = json.loads(
        await _execute_tool(
            "export_report",
            {"report_id": "report_fixture"},
            session_id="sess-harness",
        )
    )

    assert payload["status"] == "approval_required"
    assert payload["tool_name"] == "export_report"
    assert payload["policy_decision"]["approval_required"] is True
    assert [event["type"] for event in payload["events"]] == [
        "tool.requested",
        "tool.policy_checked",
        "tool.approval_required",
    ]


@pytest.mark.asyncio
async def test_execute_tool_routes_full_harness_failure_keeps_shared_metadata():
    payload = json.loads(
        await _execute_tool(
            "get_municode_section",
            {"section_id": "municode_missing_fixture"},
            session_id="sess-harness",
        )
    )

    assert payload["status"] == "failed"
    assert payload["ok"] is False
    assert payload["tool_name"] == "get_municode_section"
    assert payload["harness_status"] == "failed"
    assert payload["source_mode"] == "fixture"
    assert payload["payload"] == {}
    assert payload["error"]["code"] == "tool_call_failed"
    assert "municode_missing_fixture" in payload["error"]["message"]
    assert [event["type"] for event in payload["events"]] == [
        "tool.requested",
        "tool.policy_checked",
        "tool.started",
        "tool.failed",
    ]


@pytest.mark.asyncio
async def test_external_write_tools_fail_closed_without_approval():
    with patch("plotlot.api.chat.create_spreadsheet", new=AsyncMock()) as mock_create:
        payload = json.loads(
            await _execute_tool(
                "create_spreadsheet",
                {"title": "t", "headers": ["a"], "rows": [["1"]]},
                session_id="s1",
            )
        )

    assert payload["status"] == "pending_approval"
    mock_create.assert_not_awaited()


# ---------------------------------------------------------------------------
# Bug 3 regression — web search graceful error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_web_search_no_key_returns_not_configured():
    with patch("plotlot.api.chat.settings") as mock_settings:
        mock_settings.exa_api_key = None
        payload = json.loads(await _execute_web_search("RM-3-7 density San Diego"))

    assert payload["status"] == "not_configured"
    assert "EXA_API_KEY" in payload["message"]
    assert "search_zoning_ordinance" in payload["message"]


@pytest.mark.asyncio
async def test_execute_tool_routes_web_search_through_shared_runtime_when_context_present():
    context = ToolContext(
        workspace_id="ws_fixture",
        actor_user_id="analyst_fixture",
        run_id="run_chat_web_search",
        risk_budget_cents=100,
        live_network_allowed=True,
    )
    search_result = WebSearchResult(
        status=WebLookupStatus.SUCCESS,
        results=[
            WebSearchResultItem(
                title="Fixture result",
                url="https://example.com/web-search",
                description="Fixture summary",
                content="Fixture content.",
            )
        ],
    )
    with patch(
        "plotlot.harness.tool_router_handlers.execute_web_search",
        new=AsyncMock(return_value=search_result),
    ):
        payload = json.loads(
            await _execute_tool(
                "web_search",
                {"query": "Miami zoning update"},
                session_id="run_chat_web_search",
                context=context,
            )
        )

    assert payload["status"] == "success"
    assert payload["tool_name"] == "web_search"
    assert payload["payload"]["results"][0]["title"] == "Fixture result"
    assert payload["payload"]["evidence"][0]["tool_name"] == "web_search"
    assert [event["type"] for event in payload["events"]] == [
        "tool.requested",
        "tool.policy_checked",
        "tool.started",
        "tool.completed",
    ]


@pytest.mark.asyncio
async def test_execute_tool_routes_search_properties_through_shared_runtime_when_context_present():
    context = ToolContext(
        workspace_id="ws_fixture",
        actor_user_id="analyst_fixture",
        run_id="run_chat_search_properties",
        risk_budget_cents=100,
        live_network_allowed=True,
    )
    mock_records = [
        {
            "folio": "F1",
            "address": "1 MAIN ST",
            "city": "MIAMI",
            "county": "Miami-Dade",
            "owner": "OWNER",
            "land_use_code": "0000",
            "lot_size_sqft": 7500,
            "year_built": 0,
            "assessed_value": 50000,
            "sale_price": 25000,
            "sale_date": "01/01/2000",
            "lat": 25.9,
            "lng": -80.2,
        }
    ]
    _RUNTIME_DATASETS.clear()
    with patch(
        "plotlot.retrieval.bulk_search.bulk_property_search",
        new=AsyncMock(return_value=mock_records),
    ):
        payload = json.loads(
            await _execute_tool(
                "search_properties",
                {"county": "Miami-Dade"},
                session_id="run_chat_search_properties",
                context=context,
            )
        )

    assert payload["status"] == "success"
    assert payload["total_results"] == 1
    assert payload["sample"][0]["folio"] == "F1"
    assert payload["message"] == (
        "Found 1 properties. Use filter_dataset to narrow down or export_dataset "
        "to create a spreadsheet."
    )


@pytest.mark.asyncio
async def test_execute_tool_routes_export_dataset_through_shared_runtime_when_context_present():
    context = ToolContext(
        workspace_id="ws_fixture",
        actor_user_id="analyst_fixture",
        run_id="run_chat_export_dataset",
        risk_budget_cents=100,
        live_network_allowed=True,
        approved_approval_ids={"apr_run_chat_export_dataset_export_dataset"},
    )
    _RUNTIME_DATASETS.clear()
    _RUNTIME_DATASETS[context.run_id] = _RuntimeDataset(
        records=[
            {
                "folio": "123",
                "address": "100 MAIN ST",
            }
        ],
        search_params={"county": "Miami-Dade"},
        query_description="Vacant Residential In Miami-Dade",
        total_available=1,
        fetched_at="2026-01-01T00:00:00",
    )
    with patch(
        "plotlot.retrieval.google_workspace.create_spreadsheet",
        new=AsyncMock(
            return_value=type(
                "SpreadsheetResult",
                (),
                {
                    "spreadsheet_url": "https://docs.google.com/spreadsheets/d/exp789",
                    "title": "My Export",
                },
            )()
        ),
    ):
        payload = json.loads(
            await _execute_tool(
                "export_dataset",
                {"title": "My Export"},
                session_id="run_chat_export_dataset",
                context=context,
            )
        )

    assert payload["status"] == "success"
    assert payload["spreadsheet_url"] == "https://docs.google.com/spreadsheets/d/exp789"
    assert payload["message"] == "Exported 1 properties to 'My Export'"


@pytest.mark.asyncio
async def test_default_runtime_web_search_no_key_matches_chat_guidance():
    context = ToolContext(
        workspace_id="ws_fixture",
        actor_user_id="analyst_fixture",
        run_id="run_runtime_web_search",
        risk_budget_cents=100,
        live_network_allowed=True,
    )
    with patch("plotlot.config.settings") as mock_settings:
        mock_settings.exa_api_key = None
        result = await get_default_runtime().call_tool(
            tool_name="web_search",
            tool_args={"query": "RM-3-7 density San Diego"},
            context=context,
        )

    assert result.result is not None
    assert result.result["status"] == "not_configured"
    assert "EXA_API_KEY" in result.result["message"]
    assert "search_zoning_ordinance" in result.result["message"]


@pytest.mark.asyncio
async def test_execute_tool_web_search_success_returns_evidence_backed_payload():
    context = ToolContext(
        workspace_id="ws_fixture",
        actor_user_id="analyst_fixture",
        run_id="run_runtime_web_search_success",
        risk_budget_cents=100,
        live_network_allowed=True,
    )
    search_result = WebSearchResult(
        status=WebLookupStatus.SUCCESS,
        results=[
            WebSearchResultItem(
                title="RM-3-7 setbacks",
                url="https://example.com/rm-3-7",
                description="Setback summary",
                content="Front setback 15 feet.",
            )
        ],
    )
    with (
        patch(
            "plotlot.harness.tool_router_handlers.execute_web_search",
            new=AsyncMock(return_value=search_result),
        ),
    ):
        payload = json.loads(
            await _execute_tool(
                "web_search",
                {"query": "RM-3-7 setbacks"},
                session_id="sess-web-evidence",
                context=context,
            )
        )

    assert payload["status"] == "success"
    assert payload["payload"]["results"][0]["title"] == "RM-3-7 setbacks"
    assert payload["payload"]["results"][0]["evidence_id"]
    assert payload["payload"]["results"][0]["citation"]["url"] == "https://example.com/rm-3-7"
    assert len(payload["payload"]["evidence"]) == 1
    assert payload["payload"]["evidence"][0]["tool_name"] == "web_search"


@pytest.mark.asyncio
async def test_execute_web_search_402_returns_quota_exceeded():
    mock_response = AsyncMock()
    mock_response.status_code = 402

    with (
        patch("plotlot.harness.tool_router_handlers.settings") as mock_settings,
        patch("plotlot.harness.web_lookup_clients.httpx.AsyncClient") as mock_client_cls,
    ):
        mock_settings.exa_api_key = "test-key"
        mock_client = mock_client_cls.return_value
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.post = AsyncMock(return_value=mock_response)

        payload = json.loads(await _execute_web_search("density"))

    assert payload["status"] == "quota_exceeded"
    assert "search_zoning_ordinance" in payload["message"]


@pytest.mark.asyncio
async def test_execute_web_search_401_returns_auth_error():
    mock_response = AsyncMock()
    mock_response.status_code = 401

    with (
        patch("plotlot.harness.tool_router_handlers.settings") as mock_settings,
        patch("plotlot.harness.web_lookup_clients.httpx.AsyncClient") as mock_client_cls,
    ):
        mock_settings.exa_api_key = "bad-key"
        mock_client = mock_client_cls.return_value
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.post = AsyncMock(return_value=mock_response)

        payload = json.loads(await _execute_web_search("density"))

    assert payload["status"] == "auth_error"
    assert "search_zoning_ordinance" in payload["message"]
