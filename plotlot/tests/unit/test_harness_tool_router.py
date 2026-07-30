from __future__ import annotations

from unittest.mock import AsyncMock, patch

from plotlot.core.types import CompAnalysis, ComparableSale
from plotlot.domain.types import ToolContext
from plotlot.harness.contracts import ExecutionMode, SourceMode
from plotlot.harness.tool_router import HarnessToolCallRequest, default_tool_router
from plotlot.harness.web_lookup import (
    WebLookupStatus,
    WebSearchProvider,
    WebSearchResult,
    WebSearchResultItem,
)


def _request(tool_name: str, args: dict[str, object]) -> HarnessToolCallRequest:
    return HarnessToolCallRequest(
        tool_name=tool_name,
        args=args,
        context=ToolContext(
            workspace_id="ws_fixture",
            actor_user_id="analyst_fixture",
            run_id="run_fixture_tools",
            live_network_allowed=False,
        ),
        source_mode=SourceMode.FIXTURE,
        execution_mode=ExecutionMode.CLI,
    )


def test_tool_router_runs_allowed_fixture_tool_with_policy_events() -> None:
    result = default_tool_router().call(
        _request(
            "search_municode",
            {"jurisdiction": "miami", "query": "parking"},
        )
    )

    assert result.ok is True
    assert result.status == "completed"
    assert result.payload["results"][0]["section_id"] == "municode_miami_parking_fixture"
    assert [event.type for event in result.events] == [
        "tool.requested",
        "tool.policy_checked",
        "tool.started",
        "tool.completed",
    ]


def test_tool_router_pauses_ask_tool_before_handler_execution() -> None:
    result = default_tool_router().call(_request("export_report", {"report_id": "report_fixture"}))

    assert result.ok is False
    assert result.status == "approval_required"
    assert result.policy_decision.approval_required is True
    assert result.events[-1].type == "tool.approval_required"


def test_tool_router_denies_blocked_tool_without_approval_path() -> None:
    result = default_tool_router().call(
        _request("download_protected_media", {"video_source_id": "vid_fixture"})
    )

    assert result.ok is False
    assert result.status == "denied"
    assert result.policy_decision.approval_required is False
    assert result.events[-1].type == "tool.denied"


def test_tool_router_runs_web_search_with_evidence_enrichment() -> None:
    search_result = WebSearchResult(
        status=WebLookupStatus.SUCCESS,
        results=[
            WebSearchResultItem(
                title="Miami zoning update",
                url="https://example.com/miami-zoning",
                description="Fixture zoning summary",
                content="Parking rules updated.",
            )
        ],
    )

    request = HarnessToolCallRequest(
        tool_name="web_search",
        args={"query": "Miami zoning update"},
        context=ToolContext(
            workspace_id="ws_fixture",
            actor_user_id="analyst_fixture",
            run_id="run_fixture_web_search",
            live_network_allowed=True,
            risk_budget_cents=100,
        ),
        source_mode=SourceMode.FIXTURE,
        execution_mode=ExecutionMode.CLI,
    )

    with patch(
        "plotlot.harness.tool_router_handlers.execute_web_search",
        new=AsyncMock(return_value=search_result),
    ):
        result = default_tool_router().call(request)

    assert result.ok is True
    assert result.status == "completed"
    assert result.payload["results"][0]["evidence_id"]
    assert result.payload["evidence"][0]["tool_name"] == "web_search"
    assert [event.type for event in result.events] == [
        "tool.requested",
        "tool.policy_checked",
        "tool.started",
        "tool.completed",
    ]


def test_tool_router_runs_find_comparables_with_evidence_enrichment() -> None:
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

    request = HarnessToolCallRequest(
        tool_name="find_comparables",
        args={
            "address": "123 Example St",
            "county": "Miami-Dade",
            "municipality": "Miami",
            "state": "FL",
            "lat": 25.7617,
            "lng": -80.1918,
            "lot_size_sqft": 8000,
            "zoning_code": "T6-8",
        },
        context=ToolContext(
            workspace_id="ws_fixture",
            actor_user_id="analyst_fixture",
            run_id="run_fixture_comps",
            live_network_allowed=False,
        ),
        source_mode=SourceMode.FIXTURE,
        execution_mode=ExecutionMode.CLI,
    )

    with patch(
        "plotlot.harness.tool_router_handlers.find_comparables",
        new=AsyncMock(return_value=comp_analysis),
    ):
        result = default_tool_router().call(request)

    assert result.ok is True
    assert result.status == "completed"
    assert result.payload["analysis"]["adv_per_unit"] == 237500.0
    assert result.payload["analysis"]["comparables"][0]["evidence_id"]
    assert result.payload["analysis"]["unit_comparables"][0]["evidence_id"]
    assert len(result.payload["evidence"]) == 2
    assert result.payload["evidence"][0]["tool_name"] == "find_comparables"
    assert [event.type for event in result.events] == [
        "tool.requested",
        "tool.policy_checked",
        "tool.started",
        "tool.completed",
    ]


def test_tool_router_enriches_thin_live_comps_with_web_listing_candidates() -> None:
    comp_analysis = CompAnalysis(
        comparables=[],
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
        estimated_land_value=0.0,
        adv_per_unit=237500.0,
        adv_source="comps",
        confidence=0.55,
    )
    first_search_result = WebSearchResult(
        status=WebLookupStatus.SUCCESS,
        provider=WebSearchProvider.EXA,
        results=[
            WebSearchResultItem(
                title="123 Example St sold lot",
                url="https://www.zillow.com/homedetails/123-example-st",
                description="Public listing candidate for a sold vacant lot.",
                content="Sold vacant lot in Miami-Dade.",
            )
        ],
    )
    second_search_result = WebSearchResult(
        status=WebLookupStatus.SUCCESS,
        provider=WebSearchProvider.EXA,
        results=[
            WebSearchResultItem(
                title="125 Example St sold lot",
                url="https://www.zillow.com/homedetails/125-example-st",
                description="Second public listing candidate for a sold vacant lot.",
                content="Sold vacant lot in Miami-Dade.",
            )
        ],
    )

    request = HarnessToolCallRequest(
        tool_name="find_comparables",
        args={
            "address": "123 Example St",
            "county": "Miami-Dade",
            "municipality": "Miami",
            "state": "FL",
            "lat": 25.7617,
            "lng": -80.1918,
            "lot_size_sqft": 8000,
            "zoning_code": "T6-8",
        },
        context=ToolContext(
            workspace_id="ws_fixture",
            actor_user_id="analyst_fixture",
            run_id="run_fixture_comps_live",
            live_network_allowed=True,
        ),
        source_mode=SourceMode.LIVE,
        execution_mode=ExecutionMode.CLI,
    )

    with (
        patch(
            "plotlot.harness.tool_router_handlers.find_comparables",
            new=AsyncMock(return_value=comp_analysis),
        ),
        patch(
            "plotlot.harness.tool_router_handlers.execute_web_search",
            new=AsyncMock(side_effect=[first_search_result, second_search_result]),
        ),
        patch("plotlot.harness.tool_router_handlers.settings") as mock_settings,
    ):
        mock_settings.exa_api_key = "test-exa-key"
        result = default_tool_router().call(request)

    assert result.ok is True
    assert result.payload["analysis"]["web_listing_search"]["provider"] == "exa"
    assert result.payload["analysis"]["web_listing_search"]["provider_policy"] == "exa_only"
    assert (
        result.payload["analysis"]["web_listing_search"]["strategy"]
        == "sold_land_then_improved_sales"
    )
    assert (
        result.payload["analysis"]["web_listing_search"]["selected_search_category"] == "sold_land"
    )
    assert result.payload["analysis"]["web_listing_search"]["selected_search_window_months"] == 6
    assert result.payload["analysis"]["web_listing_search"]["result_count"] == 2
    assert result.payload["analysis"]["web_listing_search"]["land_candidate_count"] == 2
    assert result.payload["analysis"]["web_listing_search"]["improved_candidate_count"] == 0
    assert len(result.payload["analysis"]["web_listing_search"]["attempts"]) == 2
    assert (
        result.payload["analysis"]["web_listing_candidates"][0]["title"]
        == "123 Example St sold lot"
    )
    assert (
        result.payload["analysis"]["web_listing_candidates"][0]["address_hint"]
        == "123 Example St sold lot"
    )
    assert (
        result.payload["analysis"]["web_listing_candidates"][0]["source_domain"] == "www.zillow.com"
    )
    assert (
        result.payload["analysis"]["web_listing_candidates"][0]["classification"]
        == "likely_vacant_land"
    )
    assert result.payload["analysis"]["web_listing_candidates"][0]["confidence"] == 0.93
    assert result.payload["analysis"]["web_listing_candidates"][0]["search_category"] == "sold_land"
    assert result.payload["analysis"]["web_listing_candidates"][0]["search_window_months"] == 6
    assert (
        result.payload["analysis"]["web_listing_candidates"][1]["title"]
        == "125 Example St sold lot"
    )
    assert result.payload["analysis"]["web_listing_candidates"][1]["search_window_months"] == 12


def test_tool_router_runs_fixture_browser_comp_capture() -> None:
    request = HarnessToolCallRequest(
        tool_name="capture_public_listing_comps",
        args={
            "address": "45 NW 209 ST, Miami Gardens, FL 33169",
            "county": "Miami-Dade",
            "municipality": "Miami Gardens",
            "state": "FL",
            "lot_size_sqft": 10105.0,
            "zoning_code": "R-1",
        },
        context=ToolContext(
            workspace_id="ws_fixture",
            actor_user_id="analyst_fixture",
            run_id="run_fixture_browser_capture",
            live_network_allowed=False,
        ),
        source_mode=SourceMode.FIXTURE,
        execution_mode=ExecutionMode.CLI,
    )

    result = default_tool_router().call(request)

    assert result.ok is True
    assert result.status == "completed"
    assert result.payload["status"] == "success"
    assert result.payload["provider"] == "browser_use"
    assert len(result.payload["candidates"]) >= 1
    assert result.payload["candidates"][0]["captured_by"] == "browser_use"
    assert result.payload["candidates"][0]["classification"] == "likely_vacant_land"
    assert len(result.payload["evidence"]) == 2


def test_tool_router_continues_past_non_local_land_hits_until_local_candidates_arrive() -> None:
    comp_analysis = CompAnalysis(
        comparables=[],
        unit_comparables=[],
        estimated_land_value=0.0,
        adv_per_unit=None,
        adv_source="",
        confidence=0.0,
    )
    broad_search_result = WebSearchResult(
        status=WebLookupStatus.SUCCESS,
        provider=WebSearchProvider.EXA,
        results=[
            WebSearchResultItem(
                title="10 Broad St, Miami, FL 33150 | Zillow",
                url="https://www.zillow.com/homedetails/broad-1",
                description="Public listing candidate for a sold vacant lot.",
                content="Sold vacant lot in Miami.",
            ),
            WebSearchResultItem(
                title="20 Broad St, Opa-locka, FL 33054 | Zillow",
                url="https://www.zillow.com/homedetails/broad-2",
                description="Public listing candidate for a sold vacant lot.",
                content="Sold vacant lot in Opa-locka.",
            ),
        ],
    )
    local_search_result = WebSearchResult(
        status=WebLookupStatus.SUCCESS,
        provider=WebSearchProvider.EXA,
        results=[
            WebSearchResultItem(
                title="17605 NW 19th Avenue, Miami Gardens, FL 33056 | Zillow",
                url="https://www.zillow.com/homedetails/local-1",
                description="Public listing candidate for a sold vacant lot.",
                content="Sold vacant lot in Miami Gardens.",
            ),
            WebSearchResultItem(
                title="2940 NW 169th Ter, Miami Gardens, FL 33056 | Zillow",
                url="https://www.zillow.com/homedetails/local-2",
                description="Second public listing candidate for a sold vacant lot.",
                content="Sold vacant lot in Miami Gardens.",
            ),
        ],
    )

    request = HarnessToolCallRequest(
        tool_name="find_comparables",
        args={
            "address": "45 NW 209 ST, Miami Gardens, FL 33169",
            "county": "Miami-Dade",
            "municipality": "Miami Gardens",
            "state": "FL",
            "lat": 25.9684,
            "lng": -80.2135,
            "lot_size_sqft": 7500,
            "zoning_code": "R-1",
        },
        context=ToolContext(
            workspace_id="ws_fixture",
            actor_user_id="analyst_fixture",
            run_id="run_fixture_comps_live_miami_gardens",
            live_network_allowed=True,
        ),
        source_mode=SourceMode.LIVE,
        execution_mode=ExecutionMode.CLI,
    )

    with (
        patch(
            "plotlot.harness.tool_router_handlers.find_comparables",
            new=AsyncMock(return_value=comp_analysis),
        ),
        patch(
            "plotlot.harness.tool_router_handlers.execute_web_search",
            new=AsyncMock(side_effect=[broad_search_result, local_search_result]),
        ),
        patch("plotlot.harness.tool_router_handlers.settings") as mock_settings,
    ):
        mock_settings.exa_api_key = "test-exa-key"
        result = default_tool_router().call(request)

    assert result.ok is True
    assert len(result.payload["analysis"]["web_listing_search"]["attempts"]) == 2
    assert result.payload["analysis"]["web_listing_candidates"][0]["municipality_match"] is True
    assert result.payload["analysis"]["web_listing_candidates"][0]["title"].startswith(
        "17605 NW 19th Avenue"
    )
    assert result.payload["analysis"]["web_listing_candidates"][1]["title"].startswith(
        "2940 NW 169th Ter"
    )
    assert any(
        candidate["municipality_match"] is not True
        for candidate in result.payload["analysis"]["web_listing_candidates"]
    )


def test_tool_router_classifies_improved_listing_candidates_as_improved_sales() -> None:
    comp_analysis = CompAnalysis(
        comparables=[],
        unit_comparables=[],
        estimated_land_value=0.0,
        adv_per_unit=None,
        adv_source="",
        confidence=0.0,
    )
    search_result = WebSearchResult(
        status=WebLookupStatus.SUCCESS,
        provider=WebSearchProvider.EXA,
        results=[
            WebSearchResultItem(
                title="310 NW 205th Ter, Miami Gardens, FL 33169 | Zillow",
                url="https://www.zillow.com/homedetails/example-house",
                description="Sold for $460,000. 3 beds, 2 baths, 1,248 sqft. Single Family Residence. Built in 1990.",
                content="House listing candidate.",
            )
        ],
    )

    request = HarnessToolCallRequest(
        tool_name="find_comparables",
        args={
            "address": "45 NW 209 ST",
            "county": "Miami-Dade",
            "municipality": "Miami Gardens",
            "state": "FL",
            "lat": 25.7617,
            "lng": -80.1918,
            "lot_size_sqft": 8000,
            "zoning_code": "R-1",
        },
        context=ToolContext(
            workspace_id="ws_fixture",
            actor_user_id="analyst_fixture",
            run_id="run_fixture_comps_live_house",
            live_network_allowed=True,
        ),
        source_mode=SourceMode.LIVE,
        execution_mode=ExecutionMode.CLI,
    )

    with (
        patch(
            "plotlot.harness.tool_router_handlers.find_comparables",
            new=AsyncMock(return_value=comp_analysis),
        ),
        patch(
            "plotlot.harness.tool_router_handlers.execute_web_search",
            new=AsyncMock(
                side_effect=[
                    WebSearchResult(
                        status=WebLookupStatus.SUCCESS, provider=WebSearchProvider.EXA, results=[]
                    ),
                    WebSearchResult(
                        status=WebLookupStatus.SUCCESS, provider=WebSearchProvider.EXA, results=[]
                    ),
                    WebSearchResult(
                        status=WebLookupStatus.SUCCESS, provider=WebSearchProvider.EXA, results=[]
                    ),
                    search_result,
                ]
            ),
        ),
        patch("plotlot.harness.tool_router_handlers.settings") as mock_settings,
    ):
        mock_settings.exa_api_key = "test-exa-key"
        result = default_tool_router().call(request)

    assert result.ok is True
    assert result.payload["analysis"]["web_listing_search"]["land_candidate_count"] == 0
    assert result.payload["analysis"]["web_listing_search"]["improved_candidate_count"] == 1
    assert (
        result.payload["analysis"]["web_listing_search"]["selected_search_category"]
        == "new_build_houses"
    )
    assert result.payload["analysis"]["web_listing_search"]["selected_search_window_months"] == 12
    assert len(result.payload["analysis"]["web_listing_search"]["attempts"]) == 4
    assert (
        result.payload["analysis"]["web_listing_candidates"][0]["classification"]
        == "likely_improved_sale"
    )


def test_tool_router_filters_non_zillow_redfin_listing_candidates() -> None:
    comp_analysis = CompAnalysis(
        comparables=[],
        unit_comparables=[],
        estimated_land_value=0.0,
        adv_per_unit=None,
        adv_source="",
        confidence=0.0,
    )
    search_result = WebSearchResult(
        status=WebLookupStatus.SUCCESS,
        provider=WebSearchProvider.EXA,
        results=[
            WebSearchResultItem(
                title="123 Example St sold lot",
                url="https://example.com/listing/123-example-st",
                description="Public listing candidate for a sold vacant lot.",
                content="Sold vacant lot in Miami-Dade.",
            )
        ],
    )

    request = HarnessToolCallRequest(
        tool_name="find_comparables",
        args={
            "address": "123 Example St",
            "county": "Miami-Dade",
            "municipality": "Miami",
            "state": "FL",
            "lat": 25.7617,
            "lng": -80.1918,
            "lot_size_sqft": 8000,
            "zoning_code": "T6-8",
        },
        context=ToolContext(
            workspace_id="ws_fixture",
            actor_user_id="analyst_fixture",
            run_id="run_fixture_comps_live_domain_filter",
            live_network_allowed=True,
        ),
        source_mode=SourceMode.LIVE,
        execution_mode=ExecutionMode.CLI,
    )

    with (
        patch(
            "plotlot.harness.tool_router_handlers.find_comparables",
            new=AsyncMock(return_value=comp_analysis),
        ),
        patch(
            "plotlot.harness.tool_router_handlers.execute_web_search",
            new=AsyncMock(return_value=search_result),
        ),
        patch("plotlot.harness.tool_router_handlers.settings") as mock_settings,
    ):
        mock_settings.exa_api_key = "test-exa-key"
        result = default_tool_router().call(request)

    assert result.ok is True
    assert result.payload["analysis"]["web_listing_candidates"] == []
    assert (
        result.payload["analysis"]["web_listing_search"]["status"] == "no_usable_listing_candidates"
    )
    assert result.payload["analysis"]["web_listing_search"]["result_count"] == 0
    assert len(result.payload["analysis"]["web_listing_search"]["query_plan"]) == 5
    assert len(result.payload["analysis"]["web_listing_search"]["attempts"]) == 5
    assert result.payload["analysis"]["web_listing_search"]["attempts"][0]["result_count"] == 1


def test_tool_router_records_listing_query_plan_when_exa_is_unconfigured() -> None:
    comp_analysis = CompAnalysis(
        comparables=[],
        unit_comparables=[],
        estimated_land_value=0.0,
        adv_per_unit=None,
        adv_source="",
        confidence=0.0,
    )
    request = HarnessToolCallRequest(
        tool_name="find_comparables",
        args={
            "address": "45 NW 209 ST, Miami Gardens, FL 33169",
            "county": "Miami-Dade",
            "municipality": "Miami Gardens",
            "state": "FL",
            "lat": 25.967404,
            "lng": -80.202576,
            "lot_size_sqft": 10105,
            "zoning_code": "R-1",
        },
        context=ToolContext(
            workspace_id="ws_fixture",
            actor_user_id="analyst_fixture",
            run_id="run_fixture_comps_missing_exa",
            live_network_allowed=True,
        ),
        source_mode=SourceMode.LIVE,
        execution_mode=ExecutionMode.CLI,
    )
    mock_search = AsyncMock()
    with (
        patch(
            "plotlot.harness.tool_router_handlers.find_comparables",
            new=AsyncMock(return_value=comp_analysis),
        ),
        patch("plotlot.harness.tool_router_handlers.execute_web_search", new=mock_search),
        patch("plotlot.harness.tool_router_handlers.settings") as mock_settings,
    ):
        mock_settings.exa_api_key = ""
        result = default_tool_router().call(request)

    assert result.ok is True
    assert mock_search.await_count == 0
    search = result.payload["analysis"]["web_listing_search"]
    assert search["status"] == "skipped_missing_exa_api_key"
    assert search["provider_policy"] == "exa_only"
    assert search["attempts"] == []
    assert search["query_plan"][0]["purpose"] == "primary_recent_land_comp_search"
    assert search["query_plan"][0]["search_window_months"] == 6
    assert result.payload["analysis"]["web_listing_candidates"] == []


def test_tool_router_fetches_public_web_contents_through_shared_lookup_lane() -> None:
    request = HarnessToolCallRequest(
        tool_name="fetch_web_contents",
        args={"urls": ["https://www.zillow.com/homedetails/example-land"]},
        context=ToolContext(
            workspace_id="ws_fixture",
            actor_user_id="analyst_fixture",
            run_id="run_fixture_web_contents",
            live_network_allowed=True,
            risk_budget_cents=100,
        ),
        source_mode=SourceMode.LIVE,
        execution_mode=ExecutionMode.CLI,
    )
    search_result = WebSearchResult(
        status=WebLookupStatus.SUCCESS,
        provider=WebSearchProvider.EXA,
        results=[
            WebSearchResultItem(
                title="17605 NW 19th Avenue, Miami Gardens, FL 33056 | Zillow",
                url="https://www.zillow.com/homedetails/example-land",
                description="Sold for $135,000. Lot size: 9,000 sqft.",
                content="Public sold listing. Sold for $135,000. Lot size 9,000 sqft.",
            )
        ],
    )

    with patch(
        "plotlot.harness.tool_router_handlers.execute_web_contents",
        new=AsyncMock(return_value=search_result),
    ):
        result = default_tool_router().call(request)

    assert result.ok is True
    assert result.status == "completed"
    assert result.payload["results"][0]["title"].startswith("17605 NW 19th Avenue")
    assert result.payload["evidence"][0]["tool_name"] == "fetch_web_contents"


def test_tool_router_runs_pro_forma_calculator() -> None:
    result = default_tool_router().call(
        _request(
            "run_pro_forma",
            {
                "state": "FL",
                "county": "Miami-Dade",
                "max_units": 16,
                "adv_per_unit": 275000,
                "avg_unit_size_sqft": 900,
            },
        )
    )

    assert result.ok is True
    assert result.status == "completed"
    assert result.payload["calculation_type"] == "pro_forma"
    assert result.payload["market"] == "South Florida"
    assert result.payload["max_units"] == 16
    assert [event.type for event in result.events] == [
        "tool.requested",
        "tool.policy_checked",
        "tool.started",
        "tool.completed",
    ]


def test_tool_router_loads_underwriting_market_profile() -> None:
    result = default_tool_router().call(
        _request(
            "load_underwriting_market_profile",
            {
                "state": "FL",
                "county": "Broward",
                "municipality": "Fort Lauderdale",
                "assumptions": {},
            },
        )
    )

    assert result.ok is True
    assert result.status == "completed"
    assert result.payload["profile"]["market"] == "South Florida"
    assert result.payload["profile"]["monthly_rent_per_unit"] == 2250.0
    assert result.payload["profile"]["requires_income_assumption_verification"] is True
    assert result.payload["evidence"][0]["tool_name"] == "load_underwriting_market_profile"
    assert [event.type for event in result.events] == [
        "tool.requested",
        "tool.policy_checked",
        "tool.started",
        "tool.completed",
    ]


def test_tool_router_loads_rental_market_evidence() -> None:
    result = default_tool_router().call(
        _request(
            "load_rental_market_evidence",
            {
                "state": "FL",
                "county": "Broward",
                "municipality": "Fort Lauderdale",
                "assumptions": {},
            },
        )
    )

    assert result.ok is True
    assert result.status == "completed"
    assert result.payload["rental_market_evidence"]["market"] == "South Florida"
    assert result.payload["rental_market_evidence"]["monthly_rent_per_unit"] == 2250.0
    assert (
        result.payload["rental_market_evidence"]["requires_income_assumption_verification"] is True
    )
    assert result.payload["evidence"][0]["tool_name"] == "load_rental_market_evidence"


def test_tool_router_web_search_forwards_exa_provider_configuration() -> None:
    request = HarnessToolCallRequest(
        tool_name="web_search",
        args={"query": "Miami zoning update"},
        context=ToolContext(
            workspace_id="ws_fixture",
            actor_user_id="analyst_fixture",
            run_id="run_fixture_web_search_exa",
            live_network_allowed=True,
            risk_budget_cents=100,
        ),
        source_mode=SourceMode.FIXTURE,
        execution_mode=ExecutionMode.CLI,
    )

    with (
        patch("plotlot.harness.tool_router_handlers.settings") as mock_settings,
        patch(
            "plotlot.harness.tool_router_handlers.execute_web_search",
            new=AsyncMock(return_value=WebSearchResult(status=WebLookupStatus.SUCCESS)),
        ) as mock_search,
    ):
        mock_settings.exa_api_key = "exa-test-key"

        result = default_tool_router().call(request)

    assert result.ok is True
    assert mock_search.await_args is not None
    assert mock_search.await_args.kwargs["provider"] == WebSearchProvider.EXA
    assert mock_search.await_args.kwargs["exa_api_key"] == "exa-test-key"
