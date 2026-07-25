from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch

from plotlot.api.main import app
from plotlot.core.types import CompAnalysis, ComparableSale, PropertyRecord
from plotlot.mcp.harness_server import (
    HarnessMCPToolInput,
    call_harness_tool_payload_async,
)


@pytest.fixture(autouse=True)
def harness_store_path(tmp_path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("PLOTLOT_HARNESS_STORE_PATH", str(tmp_path / "harness-runs.json"))
    monkeypatch.setenv("PLOTLOT_HARNESS_JOB_STORE_PATH", str(tmp_path / "harness-jobs.json"))
    monkeypatch.setenv(
        "PLOTLOT_HARNESS_CALCULATION_STORE_PATH",
        str(tmp_path / "harness-calculations.json"),
    )
    monkeypatch.setenv(
        "PLOTLOT_HARNESS_EVIDENCE_STORE_PATH", str(tmp_path / "harness-evidence.json")
    )
    monkeypatch.setenv("PLOTLOT_HARNESS_REPORT_STORE_PATH", str(tmp_path / "harness-reports.json"))
    monkeypatch.setenv(
        "PLOTLOT_HARNESS_VERIFICATION_STORE_PATH",
        str(tmp_path / "harness-verifications.json"),
    )
    monkeypatch.setenv("PLOTLOT_HARNESS_TOOL_CALL_STORE_PATH", str(tmp_path / "tool-calls.json"))


@pytest.fixture
def transport() -> ASGITransport:
    return ASGITransport(app=app)


@pytest.fixture
async def client(transport: ASGITransport):
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_harness_tool_call_api_matches_mcp_payload_for_shared_success(
    client: AsyncClient,
) -> None:
    api_response = await client.post(
        "/api/v1/harness/tools/search_municode/call",
        json={
            "workspace_id": "ws_fixture",
            "run_id": "run_fixture_api_parity",
            "args": {"jurisdiction": "miami", "query": "parking"},
            "source_mode": "fixture",
        },
    )

    mcp_payload = await call_harness_tool_payload_async(
        HarnessMCPToolInput(
            tool_name="search_municode",
            arguments={"jurisdiction": "miami", "query": "parking"},
            workspace_id="ws_fixture",
            run_id="run_fixture_api_parity",
        )
    )

    assert api_response.status_code == 200
    api_payload = api_response.json()
    assert api_payload["ok"] == mcp_payload["ok"]
    assert api_payload["status"] == mcp_payload["status"]
    assert api_payload["tool_name"] == mcp_payload["tool_name"]
    assert api_payload["source_mode"] == mcp_payload["source_mode"]
    assert api_payload["payload"] == mcp_payload["payload"]
    assert api_payload["policy_decision"]["approval_required"] is False
    assert [event["type"] for event in api_payload["events"]] == [
        event["type"] for event in mcp_payload["events"]
    ]


@pytest.mark.asyncio
async def test_harness_tool_call_api_matches_mcp_payload_for_shared_failure(
    client: AsyncClient,
) -> None:
    api_response = await client.post(
        "/api/v1/harness/tools/get_municode_section/call",
        json={
            "workspace_id": "ws_fixture",
            "run_id": "run_fixture_api_failure_parity",
            "args": {"section_id": "municode_missing_fixture"},
            "source_mode": "fixture",
        },
    )

    mcp_payload = await call_harness_tool_payload_async(
        HarnessMCPToolInput(
            tool_name="get_municode_section",
            arguments={"section_id": "municode_missing_fixture"},
            workspace_id="ws_fixture",
            run_id="run_fixture_api_failure_parity",
        )
    )

    assert api_response.status_code == 422
    api_payload = api_response.json()
    assert api_payload["ok"] == mcp_payload["ok"] is False
    assert api_payload["status"] == mcp_payload["status"] == "failed"
    assert api_payload["tool_name"] == mcp_payload["tool_name"] == "get_municode_section"
    assert api_payload["source_mode"] == mcp_payload["source_mode"] == "fixture"
    assert api_payload["error"]["code"] == mcp_payload["error"]["code"] == "tool_call_failed"
    assert "municode_missing_fixture" in api_payload["error"]["message"]
    assert api_payload["error"]["message"] == mcp_payload["error"]["message"]
    assert [event["type"] for event in api_payload["events"]] == [
        event["type"] for event in mcp_payload["events"]
    ]


@pytest.mark.asyncio
async def test_harness_tool_call_api_matches_mcp_payload_for_web_search(
    client: AsyncClient,
) -> None:
    from unittest.mock import AsyncMock, patch

    from plotlot.harness.web_lookup import WebLookupStatus, WebSearchResult, WebSearchResultItem

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

    with patch(
        "plotlot.harness.tool_router_handlers.execute_web_search",
        new=AsyncMock(return_value=search_result),
    ):
        api_response = await client.post(
            "/api/v1/harness/tools/web_search/call",
            json={
                "workspace_id": "ws_fixture",
                "run_id": "run_fixture_api_web_search",
                "args": {"query": "Miami zoning update"},
                "source_mode": "fixture",
                "risk_budget_cents": 100,
                "live_network_allowed": True,
            },
        )

        mcp_payload = await call_harness_tool_payload_async(
            HarnessMCPToolInput(
                tool_name="web_search",
                arguments={"query": "Miami zoning update"},
                workspace_id="ws_fixture",
                run_id="run_fixture_api_web_search",
                risk_budget_cents=100,
                live_network_allowed=True,
            )
        )

    assert api_response.status_code == 200
    api_payload = api_response.json()
    assert api_payload["ok"] is True
    assert api_payload["status"] == mcp_payload["status"] == "completed"
    assert api_payload["tool_name"] == mcp_payload["tool_name"] == "web_search"
    assert api_payload["payload"]["results"][0]["evidence_id"]
    assert api_payload["payload"]["results"][0]["title"] == "Miami zoning update"
    assert mcp_payload["payload"]["results"][0]["title"] == "Miami zoning update"
    assert api_payload["payload"]["results"][0]["url"] == "https://example.com/miami-zoning"
    assert mcp_payload["payload"]["results"][0]["url"] == "https://example.com/miami-zoning"
    assert api_payload["payload"]["evidence"][0]["tool_name"] == "web_search"
    assert mcp_payload["payload"]["evidence"][0]["tool_name"] == "web_search"
    assert [event["type"] for event in api_payload["events"]] == [
        event["type"] for event in mcp_payload["events"]
    ]


@pytest.mark.asyncio
async def test_harness_tool_call_api_matches_mcp_payload_for_geocode_address(
    client: AsyncClient,
) -> None:
    with patch(
        "plotlot.retrieval.geocode.geocode_address",
        new=AsyncMock(
            return_value={
                "address": "171 NE 209th Ter, Miami, FL 33179",
                "municipality": "Miami Gardens",
                "county": "Miami-Dade",
                "state": "FL",
                "lat": 25.968,
                "lng": -80.188,
            }
        ),
    ):
        api_response = await client.post(
            "/api/v1/harness/tools/geocode_address/call",
            json={
                "workspace_id": "ws_fixture",
                "run_id": "run_fixture_api_geocode",
                "args": {"address": "171 NE 209th Ter, Miami, FL 33179"},
                "source_mode": "live",
                "live_network_allowed": True,
                "risk_budget_cents": 100,
            },
        )

        mcp_payload = await call_harness_tool_payload_async(
            HarnessMCPToolInput(
                tool_name="geocode_address",
                arguments={"address": "171 NE 209th Ter, Miami, FL 33179"},
                workspace_id="ws_fixture",
                run_id="run_fixture_api_geocode",
                source_mode="live",
                live_network_allowed=True,
                risk_budget_cents=100,
            )
        )

    assert api_response.status_code == 200
    api_payload = api_response.json()
    assert api_payload["ok"] is True
    assert api_payload["status"] == mcp_payload["status"] == "completed"
    assert api_payload["tool_name"] == mcp_payload["tool_name"] == "geocode_address"
    assert api_payload["source_mode"] == mcp_payload["source_mode"] == "live"
    assert api_payload["payload"]["result"]["county"] == "Miami-Dade"
    assert mcp_payload["payload"]["result"]["county"] == "Miami-Dade"
    assert [event["type"] for event in api_payload["events"]] == [
        event["type"] for event in mcp_payload["events"]
    ]


@pytest.mark.asyncio
async def test_harness_tool_call_api_resolves_broward_site_boundary_context(
    client: AsyncClient,
) -> None:
    api_response = await client.post(
        "/api/v1/harness/tools/resolve_site_boundary_context/call",
        json={
            "workspace_id": "ws_fixture",
            "run_id": "run_fixture_api_boundary_context",
            "args": {
                "county": "Broward",
                "municipality": "Hollywood",
            },
            "source_mode": "fixture",
        },
    )

    assert api_response.status_code == 200
    api_payload = api_response.json()
    assert api_payload["ok"] is True
    assert api_payload["tool_name"] == "resolve_site_boundary_context"
    assert api_payload["payload"]["county"] == "Broward"
    assert api_payload["payload"]["municipality"] == "Hollywood"
    assert api_payload["payload"]["is_unincorporated_or_bmsd"] is False
    assert "municipal zoning" in api_payload["payload"]["warning"].lower()


@pytest.mark.asyncio
async def test_harness_tool_call_api_lookup_property_info_includes_gis_site_context(
    client: AsyncClient,
) -> None:
    with patch(
        "plotlot.retrieval.property.lookup_property",
        new=AsyncMock(
            return_value=PropertyRecord(
                folio="123",
                address="100 Example St",
                municipality="Hollywood",
                county="Broward",
                owner="Owner",
                zoning_code="RS-6",
                zoning_description="Single-family",
                land_use_code="001",
                land_use_description="VACANT RESIDENTIAL",
                lot_size_sqft=7500.0,
                lot_dimensions="75x100",
                last_sale_price=215000.0,
                last_sale_date="2026-02-01",
                lat=26.01,
                lng=-80.15,
                parcel_geometry=[[[-80.15, 26.01], [-80.149, 26.01], [-80.149, 26.011], [-80.15, 26.011], [-80.15, 26.01]]],
            )
        ),
    ):
        api_response = await client.post(
            "/api/v1/harness/tools/lookup_property_info/call",
            json={
                "workspace_id": "ws_fixture",
                "run_id": "run_fixture_api_property_context",
                "args": {
                    "address": "100 Example St, Hollywood, FL",
                    "county": "Broward",
                    "state": "FL",
                    "lat": 26.01,
                    "lng": -80.15,
                },
                "source_mode": "live",
                "live_network_allowed": True,
                "risk_budget_cents": 100,
            },
        )

    assert api_response.status_code == 200
    api_payload = api_response.json()
    result = api_payload["payload"]["result"]
    assert api_payload["tool_name"] == "lookup_property_info"
    assert result["county"] == "Broward"
    assert result["lot_dimensions"] == "75x100"
    assert result["last_sale_price"] == pytest.approx(215000.0)
    assert result["last_sale_date"] == "2026-02-01"
    assert result["parcel_geometry"]
    assert result["gis_site_context"]["municipality"] == "Hollywood"
    assert result["gis_site_context"]["is_unincorporated_or_bmsd"] is False
    assert result["gis_site_context"]["controlling_zoning_authority"] == "municipal"
    assert result["gis_site_context"]["controlling_zoning_jurisdiction"] == "Hollywood"
    assert result["gis_site_context"]["zoning_record_applicability"] == (
        "requires_municipal_verification"
    )
    assert "municipal zoning" in result["gis_site_context"]["warning"].lower()


@pytest.mark.asyncio
async def test_harness_tool_call_api_matches_mcp_payload_for_find_comparables(
    client: AsyncClient,
) -> None:
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

    request_body = {
        "workspace_id": "ws_fixture",
        "run_id": "run_fixture_api_comps",
        "args": {
            "address": "123 Example St",
            "county": "Miami-Dade",
            "municipality": "Miami",
            "state": "FL",
            "lat": 25.7617,
            "lng": -80.1918,
            "lot_size_sqft": 8000,
            "zoning_code": "T6-8",
        },
        "source_mode": "fixture",
    }

    with patch(
        "plotlot.harness.tool_router_handlers.find_comparables",
        new=AsyncMock(return_value=comp_analysis),
    ):
        api_response = await client.post(
            "/api/v1/harness/tools/find_comparables/call",
            json=request_body,
        )

        mcp_payload = await call_harness_tool_payload_async(
            HarnessMCPToolInput(
                tool_name="find_comparables",
                arguments=request_body["args"],
                workspace_id="ws_fixture",
                run_id="run_fixture_api_comps",
            )
        )

    assert api_response.status_code == 200
    api_payload = api_response.json()
    assert api_payload["ok"] is True
    assert api_payload["status"] == mcp_payload["status"] == "completed"
    assert api_payload["tool_name"] == mcp_payload["tool_name"] == "find_comparables"
    assert api_payload["payload"]["analysis"]["estimated_land_value"] == 210000.0
    assert api_payload["payload"]["analysis"]["comparables"][0]["evidence_id"]
    assert mcp_payload["payload"]["analysis"]["unit_comparables"][0]["evidence_id"]
    assert len(api_payload["payload"]["evidence"]) == 2
    assert len(mcp_payload["payload"]["evidence"]) == 2
    assert [event["type"] for event in api_payload["events"]] == [
        event["type"] for event in mcp_payload["events"]
    ]


@pytest.mark.asyncio
async def test_harness_tool_call_api_loads_rental_market_evidence(
    client: AsyncClient,
) -> None:
    api_response = await client.post(
        "/api/v1/harness/tools/load_rental_market_evidence/call",
        json={
            "workspace_id": "ws_fixture",
            "run_id": "run_fixture_api_rental_market",
            "args": {
                "state": "FL",
                "county": "Broward",
                "municipality": "Fort Lauderdale",
                "assumptions": {},
            },
            "source_mode": "fixture",
        },
    )

    assert api_response.status_code == 200
    api_payload = api_response.json()
    assert api_payload["ok"] is True
    assert api_payload["tool_name"] == "load_rental_market_evidence"
    assert api_payload["payload"]["rental_market_evidence"]["market"] == "South Florida"
    assert api_payload["payload"]["rental_market_evidence"]["monthly_rent_per_unit"] == 2250.0
    assert api_payload["payload"]["evidence"][0]["tool_name"] == "load_rental_market_evidence"


@pytest.mark.asyncio
async def test_harness_tool_call_api_runs_live_find_comparables_with_new_build_priority(
    client: AsyncClient,
) -> None:
    features = [
        {
            "attributes": {
                "SALE_PRICE": 710000,
                "SALE_DATE": "2026-04-30",
                "ADDRESS": "200 NE 213 ST",
                "TRUE_SITE_CITY": "Miami Gardens",
                "LOT_SIZE": 7600.0,
                "UNIT_COUNT": 1,
                "BUILDING_ACTUAL_AREA": 1950.0,
                "YEAR_BUILT": 2025,
            },
            "geometry": {"x": -80.204, "y": 25.971},
        },
        {
            "attributes": {
                "SALE_PRICE": 699000,
                "SALE_DATE": "2026-04-21",
                "ADDRESS": "105 NE 213 ST",
                "TRUE_SITE_CITY": "Miami Gardens",
                "LOT_SIZE": 7500.0,
                "UNIT_COUNT": 1,
                "BUILDING_ACTUAL_AREA": 1800.0,
                "YEAR_BUILT": 2026,
            },
            "geometry": {"x": -80.204, "y": 25.971},
        },
        {
            "attributes": {
                "SALE_PRICE": 505000,
                "SALE_DATE": "2026-05-05",
                "ADDRESS": "220 NE 211 ST",
                "TRUE_SITE_CITY": "Miami Gardens",
                "LOT_SIZE": 3007.0,
                "UNIT_COUNT": 1,
                "BUILDING_ACTUAL_AREA": 1550.0,
                "YEAR_BUILT": 1980,
            },
            "geometry": {"x": -80.204, "y": 25.970},
        },
    ]

    with (
        patch(
            "plotlot.pipeline.comps_sources.resolve_sales_dataset",
            new=AsyncMock(
                return_value=(
                    "https://example.test/sales",
                    [
                        "SALE_PRICE",
                        "SALE_DATE",
                        "ADDRESS",
                        "TRUE_SITE_CITY",
                        "LOT_SIZE",
                        "UNIT_COUNT",
                        "BUILDING_ACTUAL_AREA",
                        "YEAR_BUILT",
                    ],
                )
            ),
        ),
        patch(
            "plotlot.pipeline.comps._query_nearby_sales",
            new=AsyncMock(return_value=features),
        ),
    ):
        api_response = await client.post(
            "/api/v1/harness/tools/find_comparables/call",
            json={
                "workspace_id": "ws_fixture",
                "run_id": "run_fixture_api_live_comps",
                "args": {
                    "address": "45 NW 209 ST, Miami Gardens, FL 33169",
                    "county": "Miami-Dade",
                    "municipality": "Miami Gardens",
                    "state": "FL",
                    "lat": 25.967404,
                    "lng": -80.202576,
                    "lot_size_sqft": 10105,
                    "zoning_code": "R-1",
                    "land_use_description": "VACANT RESIDENTIAL",
                },
                "source_mode": "live",
            },
        )

    assert api_response.status_code == 200
    api_payload = api_response.json()
    assert api_payload["ok"] is True
    assert api_payload["tool_name"] == "find_comparables"
    assert [comp["address"] for comp in api_payload["payload"]["analysis"]["unit_comparables"]] == [
        "200 NE 213 ST",
        "105 NE 213 ST",
    ]
    assert api_payload["payload"]["analysis"]["adv_per_unit"] == pytest.approx(704500.0)
    assert not any(
        "renovated or older improved sales" in note
        for note in api_payload["payload"]["analysis"]["notes"]
    )


@pytest.mark.asyncio
async def test_harness_tool_call_api_rejects_oversized_live_new_build_exit_outliers(
    client: AsyncClient,
) -> None:
    features = [
        {
            "attributes": {
                "SALE_PRICE": 890000,
                "SALE_DATE": "2026-04-30",
                "ADDRESS": "320 Premium Build Way",
                "TRUE_SITE_CITY": "Miami Gardens",
                "LOT_SIZE": 22000.0,
                "UNIT_COUNT": 1,
                "BUILDING_ACTUAL_AREA": 3100.0,
                "YEAR_BUILT": 2025,
            },
            "geometry": {"x": -80.204, "y": 25.971},
        },
        {
            "attributes": {
                "SALE_PRICE": 905000,
                "SALE_DATE": "2026-04-21",
                "ADDRESS": "340 Premium Build Way",
                "TRUE_SITE_CITY": "Miami Gardens",
                "LOT_SIZE": 24500.0,
                "UNIT_COUNT": 1,
                "BUILDING_ACTUAL_AREA": 3300.0,
                "YEAR_BUILT": 2026,
            },
            "geometry": {"x": -80.204, "y": 25.971},
        },
        {
            "attributes": {
                "SALE_PRICE": 505000,
                "SALE_DATE": "2026-05-05",
                "ADDRESS": "220 NE 211 ST",
                "TRUE_SITE_CITY": "Miami Gardens",
                "LOT_SIZE": 3007.0,
                "UNIT_COUNT": 1,
                "BUILDING_ACTUAL_AREA": 1550.0,
                "YEAR_BUILT": 1980,
            },
            "geometry": {"x": -80.204, "y": 25.970},
        },
        {
            "attributes": {
                "SALE_PRICE": 465000,
                "SALE_DATE": "2026-04-23",
                "ADDRESS": "221 NE 212 ST",
                "TRUE_SITE_CITY": "Miami Gardens",
                "LOT_SIZE": 3023.0,
                "UNIT_COUNT": 1,
                "BUILDING_ACTUAL_AREA": 1525.0,
                "YEAR_BUILT": 1985,
            },
            "geometry": {"x": -80.203, "y": 25.970},
        },
    ]

    with (
        patch(
            "plotlot.pipeline.comps_sources.resolve_sales_dataset",
            new=AsyncMock(
                return_value=(
                    "https://example.test/sales",
                    [
                        "SALE_PRICE",
                        "SALE_DATE",
                        "ADDRESS",
                        "TRUE_SITE_CITY",
                        "LOT_SIZE",
                        "UNIT_COUNT",
                        "BUILDING_ACTUAL_AREA",
                        "YEAR_BUILT",
                    ],
                )
            ),
        ),
        patch(
            "plotlot.pipeline.comps._query_nearby_sales",
            new=AsyncMock(return_value=features),
        ),
    ):
        api_response = await client.post(
            "/api/v1/harness/tools/find_comparables/call",
            json={
                "workspace_id": "ws_fixture",
                "run_id": "run_fixture_api_live_comps_outlier",
                "args": {
                    "address": "45 NW 209 ST, Miami Gardens, FL 33169",
                    "county": "Miami-Dade",
                    "municipality": "Miami Gardens",
                    "state": "FL",
                    "lat": 25.967404,
                    "lng": -80.202576,
                    "lot_size_sqft": 10105,
                    "zoning_code": "R-1",
                    "land_use_description": "VACANT RESIDENTIAL",
                },
                "source_mode": "live",
            },
        )

    assert api_response.status_code == 200
    api_payload = api_response.json()
    assert api_payload["ok"] is True
    assert {comp["address"] for comp in api_payload["payload"]["analysis"]["unit_comparables"]} == {
        "220 NE 211 ST",
        "221 NE 212 ST",
    }
    assert api_payload["payload"]["analysis"]["adv_per_unit"] == pytest.approx(485000.0)
    assert any(
        "No recent same-market new-build sales were available" in note
        for note in api_payload["payload"]["analysis"]["notes"]
    )


@pytest.mark.asyncio
async def test_harness_tool_call_api_prefers_nearby_local_exit_cluster(
    client: AsyncClient,
) -> None:
    features = [
        {
            "attributes": {
                "SALE_PRICE": 505000,
                "SALE_DATE": "2026-05-05",
                "ADDRESS": "220 NE 211 ST",
                "TRUE_SITE_CITY": "Miami Gardens",
                "LOT_SIZE": 3007.0,
                "UNIT_COUNT": 1,
                "BUILDING_ACTUAL_AREA": 1550.0,
                "YEAR_BUILT": 1980,
            },
            "geometry": {"x": -80.204, "y": 25.970},
        },
        {
            "attributes": {
                "SALE_PRICE": 465000,
                "SALE_DATE": "2026-04-23",
                "ADDRESS": "221 NE 212 ST",
                "TRUE_SITE_CITY": "Miami Gardens",
                "LOT_SIZE": 3023.0,
                "UNIT_COUNT": 1,
                "BUILDING_ACTUAL_AREA": 1525.0,
                "YEAR_BUILT": 1985,
            },
            "geometry": {"x": -80.203, "y": 25.970},
        },
        {
            "attributes": {
                "SALE_PRICE": 590000,
                "SALE_DATE": "2026-05-01",
                "ADDRESS": "450 NW 183 ST",
                "TRUE_SITE_CITY": "Miami Gardens",
                "LOT_SIZE": 3200.0,
                "UNIT_COUNT": 1,
                "BUILDING_ACTUAL_AREA": 1650.0,
                "YEAR_BUILT": 1988,
            },
            "geometry": {"x": -80.227, "y": 25.944},
        },
    ]

    with (
        patch(
            "plotlot.pipeline.comps_sources.resolve_sales_dataset",
            new=AsyncMock(
                return_value=(
                    "https://example.test/sales",
                    [
                        "SALE_PRICE",
                        "SALE_DATE",
                        "ADDRESS",
                        "TRUE_SITE_CITY",
                        "LOT_SIZE",
                        "UNIT_COUNT",
                        "BUILDING_ACTUAL_AREA",
                        "YEAR_BUILT",
                    ],
                )
            ),
        ),
        patch(
            "plotlot.pipeline.comps._query_nearby_sales",
            new=AsyncMock(return_value=features),
        ),
    ):
        api_response = await client.post(
            "/api/v1/harness/tools/find_comparables/call",
            json={
                "workspace_id": "ws_fixture",
                "run_id": "run_fixture_api_live_comps_cluster",
                "args": {
                    "address": "45 NW 209 ST, Miami Gardens, FL 33169",
                    "county": "Miami-Dade",
                    "municipality": "Miami Gardens",
                    "state": "FL",
                    "lat": 25.967404,
                    "lng": -80.202576,
                    "lot_size_sqft": 10105,
                    "zoning_code": "R-1",
                    "land_use_description": "VACANT RESIDENTIAL",
                },
                "source_mode": "live",
            },
        )

    assert api_response.status_code == 200
    api_payload = api_response.json()
    assert api_payload["ok"] is True
    assert {comp["address"] for comp in api_payload["payload"]["analysis"]["unit_comparables"]} == {
        "220 NE 211 ST",
        "221 NE 212 ST",
    }
    assert api_payload["payload"]["analysis"]["adv_per_unit"] == pytest.approx(485000.0)


@pytest.mark.asyncio
async def test_harness_tool_call_api_prefers_nearby_local_exit_cluster_over_premium_new_build_micro_market(
    client: AsyncClient,
) -> None:
    features = [
        {
            "attributes": {
                "SALE_PRICE": 710000,
                "SALE_DATE": "2026-04-30",
                "ADDRESS": "200 Premium Build Ct",
                "TRUE_SITE_CITY": "Miami Gardens",
                "LOT_SIZE": 7600.0,
                "UNIT_COUNT": 1,
                "BUILDING_ACTUAL_AREA": 1950.0,
                "YEAR_BUILT": 2025,
            },
            "geometry": {"x": -80.225, "y": 25.956},
        },
        {
            "attributes": {
                "SALE_PRICE": 699000,
                "SALE_DATE": "2026-04-21",
                "ADDRESS": "105 Premium Build Ct",
                "TRUE_SITE_CITY": "Miami Gardens",
                "LOT_SIZE": 7500.0,
                "UNIT_COUNT": 1,
                "BUILDING_ACTUAL_AREA": 1800.0,
                "YEAR_BUILT": 2026,
            },
            "geometry": {"x": -80.223, "y": 25.957},
        },
        {
            "attributes": {
                "SALE_PRICE": 505000,
                "SALE_DATE": "2026-05-05",
                "ADDRESS": "220 NE 211 ST",
                "TRUE_SITE_CITY": "Miami Gardens",
                "LOT_SIZE": 3007.0,
                "UNIT_COUNT": 1,
                "BUILDING_ACTUAL_AREA": 1550.0,
                "YEAR_BUILT": 1980,
            },
            "geometry": {"x": -80.204, "y": 25.970},
        },
        {
            "attributes": {
                "SALE_PRICE": 465000,
                "SALE_DATE": "2026-04-23",
                "ADDRESS": "221 NE 212 ST",
                "TRUE_SITE_CITY": "Miami Gardens",
                "LOT_SIZE": 3023.0,
                "UNIT_COUNT": 1,
                "BUILDING_ACTUAL_AREA": 1525.0,
                "YEAR_BUILT": 1985,
            },
            "geometry": {"x": -80.203, "y": 25.970},
        },
    ]

    with (
        patch(
            "plotlot.pipeline.comps_sources.resolve_sales_dataset",
            new=AsyncMock(
                return_value=(
                    "https://example.test/sales",
                    [
                        "SALE_PRICE",
                        "SALE_DATE",
                        "ADDRESS",
                        "TRUE_SITE_CITY",
                        "LOT_SIZE",
                        "UNIT_COUNT",
                        "BUILDING_ACTUAL_AREA",
                        "YEAR_BUILT",
                    ],
                )
            ),
        ),
        patch(
            "plotlot.pipeline.comps._query_nearby_sales",
            new=AsyncMock(return_value=features),
        ),
    ):
        api_response = await client.post(
            "/api/v1/harness/tools/find_comparables/call",
            json={
                "workspace_id": "ws_fixture",
                "run_id": "run_fixture_api_live_comps_micro_market",
                "args": {
                    "address": "45 NW 209 ST, Miami Gardens, FL 33169",
                    "county": "Miami-Dade",
                    "municipality": "Miami Gardens",
                    "state": "FL",
                    "lat": 25.967404,
                    "lng": -80.202576,
                    "lot_size_sqft": 10105,
                    "zoning_code": "R-1",
                    "land_use_description": "VACANT RESIDENTIAL",
                },
                "source_mode": "live",
            },
        )

    assert api_response.status_code == 200
    api_payload = api_response.json()
    assert api_payload["ok"] is True
    assert {comp["address"] for comp in api_payload["payload"]["analysis"]["unit_comparables"]} == {
        "220 NE 211 ST",
        "221 NE 212 ST",
    }
    assert api_payload["payload"]["analysis"]["adv_per_unit"] == pytest.approx(485000.0)
    assert any(
        "higher-priced nearby micro-market" in note
        for note in api_payload["payload"]["analysis"]["notes"]
    )
