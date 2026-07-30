from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch

from plotlot.api.main import app
from plotlot.domain.types import PolicyDecision
from plotlot.harness.calculation_runner import execute_underwriting_calculation
from plotlot.harness.contracts import (
    EvidenceSourceType,
    ExecutionMode,
    PlotLotEvent,
    PlotLotEventSource,
    PlotLotEventStatus,
    PlotLotEventType,
    RunId,
    SourceMode,
    ToolCallId,
)
from plotlot.harness.contracts.base import EventId
from plotlot.harness.tool_router import HarnessToolCallResult, ToolRouteStatus


class FakeLifecycleSession:
    def __init__(self) -> None:
        self._workspaces: dict[str, object] = {}
        self._projects: dict[str, object] = {}
        self._sites: dict[str, object] = {}
        self._analyses: dict[str, object] = {}
        self._runs: dict[str, object] = {}

    async def get(self, model, key):  # noqa: ANN001
        name = getattr(model, "__name__", "")
        if name == "Workspace":
            return self._workspaces.get(key)
        if name == "Project":
            return self._projects.get(key)
        if name == "Site":
            return self._sites.get(key)
        if name == "Analysis":
            return self._analyses.get(key)
        if name == "AnalysisRun":
            return self._runs.get(key)
        return None

    def add(self, obj) -> None:  # noqa: ANN001
        if obj.__class__.__name__ == "AnalysisRun":
            self._runs[getattr(obj, "id")] = obj

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def close(self) -> None:
        return None


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


async def test_noi_valuation_calculator_is_available_through_api(client: AsyncClient):
    response = await client.post(
        "/api/v1/deal-analysis/noi-valuation",
        json={
            "input": {
                "unit_count": 4,
                "monthly_rent_per_unit": 2500,
                "vacancy_pct": 0.05,
                "operating_expense_pct": 0.35,
                "cap_rate": 0.06,
            }
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["calculation_type"] == "noi_valuation"
    assert payload["formula_version"] == "noi_valuation.v1"
    assert payload["annual_noi"] == 74_100
    assert payload["as_built_value"] == 1_235_000


def _live_tool_payload(tool_name: str, args: dict[str, object]) -> dict[str, object]:
    if tool_name == "geocode_address":
        return {
            "status": "success",
            "result": {
                "address": str(args["address"]),
                "municipality": "Miami",
                "county": "Miami-Dade",
                "state": "FL",
                "lat": 25.9284,
                "lng": -80.1467,
            },
        }
    if tool_name == "lookup_property_info":
        return {
            "status": "success",
            "result": {
                "folio": "30-2206-013-0310",
                "address": str(args["address"]),
                "municipality": "Miami",
                "county": "Miami-Dade",
                "zoning_code": "T4-R",
                "ordinance_district_code": "T4-R",
                "zoning_description": "General Urban Residential",
                "lot_size_sqft": 8000,
                "living_units": 8,
                "zoning_layer_url": "https://example.test/zoning",
            },
        }
    if tool_name == "search_zoning_ordinance":
        return {
            "status": "success",
            "results": [
                {
                    "section": "Sec. 1",
                    "title": "T4-R standards",
                    "text": "Setbacks, density, height, and parking standards for T4-R.",
                    "citation": {"url": "https://library.municode.com/fl/miami/codes/miami_21"},
                }
            ],
        }
    if tool_name == "search_municode_live":
        return {
            "status": "success",
            "results": [
                {
                    "section": "Sec. 1",
                    "title": "General zoning standards",
                    "text": "General setbacks, density, height, and parking standards.",
                    "citation": {
                        "url": "https://library.municode.com/fl/example",
                        "jurisdiction": str(args.get("municipality") or "Unknown"),
                    },
                }
            ],
        }
    if tool_name == "web_search":
        return {
            "status": "success",
            "provider": "exa",
            "results": [
                {
                    "title": "View City of Miami Zoning Code (Miami 21)",
                    "url": "https://www.miami.gov/Planning-Zoning-Land-Use/View-City-of-Miami-Zoning-Code-Miami-21",
                    "description": "Official City of Miami Miami 21 code page.",
                    "content": "Official Miami 21 zoning reference.",
                    "citation": {
                        "url": "https://www.miami.gov/Planning-Zoning-Land-Use/View-City-of-Miami-Zoning-Code-Miami-21",
                        "jurisdiction": "Miami",
                    },
                }
            ],
        }
    if tool_name == "find_comparables":
        return {
            "analysis": {
                "comparables": [
                    {
                        "address": "100 Miami Land Ave",
                        "sale_price": 315000,
                        "sale_date": "2026-03-15",
                        "lot_size_sqft": 8100,
                        "zoning_code": "T4-R",
                        "distance_miles": 0.4,
                        "price_per_acre": 1692000.0,
                        "price_per_unit": None,
                        "adjustments": {"qualification_score": 0.91},
                        "citation": {"jurisdiction": "Miami-Dade"},
                    }
                ],
                "unit_comparables": [
                    {
                        "address": "350 Miami Built Blvd",
                        "sale_price": 2520000,
                        "sale_date": "2026-02-10",
                        "lot_size_sqft": 9500,
                        "zoning_code": "T4-R",
                        "distance_miles": 0.9,
                        "price_per_acre": 0.0,
                        "price_per_unit": 252000.0,
                        "adjustments": {"qualification_score": 0.87},
                        "citation": {"jurisdiction": "Miami-Dade"},
                    }
                ],
                "estimated_land_value": 315371.9,
                "adv_per_unit": 246000.0,
                "confidence": 0.78,
            }
        }
    if tool_name == "compute_feasibility":
        return {
            "calculation_type": "feasibility",
            "formula_version": "feasibility.v1",
            "max_gross_buildable_sf": 16000.0,
            "net_rentable_sf": 13600.0,
            "estimated_units": 16,
            "parking_required": 24,
            "major_constraints": [],
            "feasibility_warnings": [],
        }
    if tool_name == "load_underwriting_market_profile":
        assumption_payload = args.get("assumptions")
        explicit_income_keys = isinstance(assumption_payload, dict) and all(
            isinstance(assumption_payload.get(key), int | float)
            for key in ("monthlyRentPerUnit", "vacancyPct", "operatingExpensePct", "capRate")
        )
        return {
            "profile": {
                "market": "South Florida",
                "source": "market:south_florida",
                "state": "FL",
                "county": str(args.get("county") or "Miami-Dade"),
                "municipality": str(args.get("municipality") or "Miami"),
                "construction_cost_psf": 225.0,
                "avg_unit_size_sqft": 1000.0,
                "soft_cost_pct": 20.0,
                "builder_margin_pct": 25.0,
                "impact_fees_per_unit": 25000.0,
                "adv_per_unit": 450000.0,
                "monthly_rent_per_unit": (
                    float(assumption_payload["monthlyRentPerUnit"])
                    if isinstance(assumption_payload, dict)
                    and isinstance(assumption_payload.get("monthlyRentPerUnit"), int | float)
                    else 2250.0
                ),
                "vacancy_pct": (
                    float(assumption_payload["vacancyPct"])
                    if isinstance(assumption_payload, dict)
                    and isinstance(assumption_payload.get("vacancyPct"), int | float)
                    else 0.05
                ),
                "operating_expense_pct": (
                    float(assumption_payload["operatingExpensePct"])
                    if isinstance(assumption_payload, dict)
                    and isinstance(assumption_payload.get("operatingExpensePct"), int | float)
                    else 0.35
                ),
                "cap_rate": (
                    float(assumption_payload["capRate"])
                    if isinstance(assumption_payload, dict)
                    and isinstance(assumption_payload.get("capRate"), int | float)
                    else 0.06
                ),
                "requires_official_verification": False,
                "requires_income_assumption_verification": not explicit_income_keys,
                "income_inferred_fields": (
                    []
                    if explicit_income_keys
                    else [
                        "monthly_rent_per_unit",
                        "vacancy_pct",
                        "operating_expense_pct",
                        "cap_rate",
                    ]
                ),
                "income_assumption_source": "user_assumptions"
                if explicit_income_keys
                else "market:south_florida",
                "overridden_fields": (
                    ["monthly_rent_per_unit", "vacancy_pct", "operating_expense_pct", "cap_rate"]
                    if explicit_income_keys
                    else []
                ),
                "assumptions_snapshot": dict(assumption_payload or {}),
            }
        }
    if tool_name == "run_noi_valuation":
        return {
            "calculation_type": "noi_valuation",
            "formula_version": "noi_valuation.v1",
            "gross_scheduled_income": 225600.0,
            "effective_gross_income": 214320.0,
            "operating_expenses": 72868.8,
            "annual_noi": 141451.2,
            "as_built_value": 2460020.87,
            "warnings": [],
        }
    if tool_name == "run_residual_land_value":
        return {
            "calculation_type": "residual_land_value",
            "formula_version": "residual_land_value.v1",
            "total_project_costs_excluding_land": 4400000.0,
            "max_supportable_land_price": 125000.0,
            "spread_to_asking_price": -5000.0,
            "go_no_go_signal": "watch",
            "warnings": [],
        }
    if tool_name == "run_pro_forma":
        return execute_underwriting_calculation("pro-forma", args).model_dump(mode="json")
    if tool_name == "capture_public_listing_comps":
        return {
            "status": "success",
            "provider": "browser_use",
            "strategy": "public_sold_listing_capture",
            "candidates": [],
            "warnings": [],
        }
    raise AssertionError(f"Unexpected tool: {tool_name}")


def _empty_live_comps_payload() -> dict[str, object]:
    return {
        "analysis": {
            "comparables": [],
            "unit_comparables": [],
            "estimated_land_value": 0.0,
            "adv_per_unit": None,
            "confidence": 0.0,
            "notes": [
                "No qualifying comps within 3.0 mi over the last 12 mo (checked 200 sales)",
            ],
        }
    }


def _land_only_live_comps_payload() -> dict[str, object]:
    return {
        "analysis": {
            "comparables": [
                {
                    "address": "100 Miami Land Ave",
                    "sale_price": 315000,
                    "sale_date": "2026-03-15",
                    "lot_size_sqft": 8100,
                    "zoning_code": "T4-R",
                    "distance_miles": 0.4,
                    "price_per_acre": 1692000.0,
                    "price_per_unit": None,
                    "adjustments": {},
                    "citation": {"jurisdiction": "Miami-Dade"},
                }
            ],
            "unit_comparables": [],
            "estimated_land_value": 315371.9,
            "adv_per_unit": None,
            "confidence": 0.5,
            "notes": [
                "No nearby improved sales found — ADV per unit unavailable from comps",
            ],
        }
    }


def _live_tool_result(
    tool_name: str, run_id: str, args: dict[str, object], source_mode: SourceMode
) -> HarnessToolCallResult:
    return HarnessToolCallResult(
        ok=True,
        tool_call_id=ToolCallId(f"tool_call_{tool_name}"),
        tool_name=tool_name,
        run_id=RunId(run_id),
        args=args,
        status=ToolRouteStatus.COMPLETED,
        policy_decision=PolicyDecision(allowed=True, reason="test"),
        payload=_live_tool_payload(tool_name, args),
        events=[
            PlotLotEvent(
                event_id=EventId(f"evt_{tool_name}_requested"),
                run_id=RunId(run_id),
                sequence=1,
                type=PlotLotEventType.TOOL_REQUESTED,
                payload={"tool_name": tool_name},
                source=PlotLotEventSource.TOOL,
                status=PlotLotEventStatus.PENDING,
                source_mode=source_mode,
                execution_mode=ExecutionMode.API,
            ),
            PlotLotEvent(
                event_id=EventId(f"evt_{tool_name}_policy"),
                run_id=RunId(run_id),
                sequence=2,
                type=PlotLotEventType.TOOL_POLICY_CHECKED,
                payload={"tool_name": tool_name},
                source=PlotLotEventSource.POLICY,
                status=PlotLotEventStatus.COMPLETED,
                source_mode=source_mode,
                execution_mode=ExecutionMode.API,
            ),
            PlotLotEvent(
                event_id=EventId(f"evt_{tool_name}_started"),
                run_id=RunId(run_id),
                sequence=3,
                type=PlotLotEventType.TOOL_STARTED,
                payload={"tool_name": tool_name},
                source=PlotLotEventSource.TOOL,
                status=PlotLotEventStatus.PENDING,
                source_mode=source_mode,
                execution_mode=ExecutionMode.API,
            ),
            PlotLotEvent(
                event_id=EventId(f"evt_{tool_name}_completed"),
                run_id=RunId(run_id),
                sequence=4,
                type=PlotLotEventType.TOOL_COMPLETED,
                payload={"tool_name": tool_name},
                source=PlotLotEventSource.TOOL,
                status=PlotLotEventStatus.COMPLETED,
                source_mode=source_mode,
                execution_mode=ExecutionMode.API,
            ),
        ],
        source_mode=source_mode,
    )


@pytest.mark.asyncio
async def test_harness_skills_api_exposes_training_and_gis_skills(client: AsyncClient) -> None:
    response = await client.get("/api/v1/harness/skills")

    assert response.status_code == 200
    names = {item["name"] for item in response.json()["skills"]}
    assert "zoning_research" in names
    assert "training_ingestion" in names
    assert "comparable_comping" in names


@pytest.mark.asyncio
async def test_harness_registry_api_exposes_tools_skills_and_agent_roles(
    client: AsyncClient,
) -> None:
    roles_response = await client.get("/api/v1/harness/roles")
    registry_response = await client.get("/api/v1/harness/registry")

    assert roles_response.status_code == 200
    assert registry_response.status_code == 200
    role_names = {item["name"] for item in roles_response.json()["roles"]}
    registry = registry_response.json()
    tool_names = {item["name"] for item in registry["tools"]}
    skill_names = {item["name"] for item in registry["skills"]}
    assert "development_underwriter" in role_names
    assert "comping_analyst" in role_names
    assert "run_residual_land_value" in tool_names
    assert "acquisition_memo" in skill_names
    assert "comparable_comping" in skill_names
    assert registry["counts"]["roles"] == len(registry["roles"])


@pytest.mark.asyncio
async def test_harness_tool_inspect_and_call_api_use_shared_router(client: AsyncClient) -> None:
    inspect_response = await client.get("/api/v1/harness/tools/search_municode")
    call_response = await client.post(
        "/api/v1/harness/tools/search_municode/call",
        json={
            "workspace_id": "ws_fixture",
            "run_id": "run_fixture_api_tool",
            "args": {"jurisdiction": "miami", "query": "parking"},
            "source_mode": "fixture",
        },
    )

    assert inspect_response.status_code == 200
    assert call_response.status_code == 200
    assert inspect_response.json()["tool"]["name"] == "search_municode"
    assert call_response.json()["ok"] is True
    assert call_response.json()["events"][1]["type"] == "tool.policy_checked"
    assert (
        call_response.json()["payload"]["results"][0]["section_id"]
        == "municode_miami_parking_fixture"
    )


@pytest.mark.asyncio
async def test_harness_tool_call_api_exposes_approval_required_status(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/harness/tools/export_report/call",
        json={
            "workspace_id": "ws_fixture",
            "run_id": "run_fixture_api_tool",
            "args": {"report_id": "report_fixture"},
            "source_mode": "fixture",
        },
    )

    assert response.status_code == 409
    assert response.json()["status"] == "approval_required"
    assert response.json()["policy_decision"]["approval_required"] is True


@pytest.mark.asyncio
async def test_harness_tool_call_api_rejects_spoofed_approval_ids(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/harness/tools/export_report/call",
        json={
            "workspace_id": "ws_fixture",
            "run_id": "run_fixture_api_tool",
            "args": {"report_id": "report_fixture"},
            "source_mode": "fixture",
            "approved_approval_ids": ["apr_run_fixture_api_tool_export_report"],
        },
    )

    assert response.status_code == 409
    assert response.json()["status"] == "approval_required"
    assert response.json()["policy_decision"]["approval_required"] is True


@pytest.mark.asyncio
async def test_harness_tool_call_api_persists_tool_call_and_appends_events(
    client: AsyncClient,
) -> None:
    create_response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "example Miami-Dade fixture address",
            "analysis_type": "acquisition_memo",
            "source_mode": "fixture",
        },
    )
    run_id = create_response.json()["run_id"]

    call_response = await client.post(
        "/api/v1/harness/tools/search_municode/call",
        json={
            "workspace_id": "ws_fixture",
            "run_id": run_id,
            "args": {"jurisdiction": "miami", "query": "parking"},
            "source_mode": "fixture",
        },
    )
    calls_response = await client.get(f"/api/v1/harness/runs/{run_id}/tool-calls")
    events_response = await client.get(f"/api/v1/harness/runs/{run_id}/events")

    assert create_response.status_code == 200
    assert call_response.status_code == 200
    assert calls_response.status_code == 200
    assert events_response.status_code == 200
    assert (
        calls_response.json()["tool_calls"][0]["tool_call_id"]
        == call_response.json()["tool_call_id"]
    )
    assert events_response.json()["events"][-1]["type"] == "tool.completed"


@pytest.mark.asyncio
async def test_harness_tool_call_api_rejects_live_mode_for_fixture_only_tools(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/harness/tools/search_municode/call",
        json={
            "workspace_id": "ws_fixture",
            "run_id": "run_fixture_api_tool",
            "args": {"jurisdiction": "miami", "query": "parking"},
            "source_mode": "live",
        },
    )

    assert response.status_code == 501
    assert response.json()["detail"] == "Only fixture source mode is wired for this harness tool"


@pytest.mark.asyncio
async def test_gis_search_api_uses_shared_south_florida_catalog(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/gis/search",
        json={"query": "zoning", "county": "Broward", "source_mode": "fixture"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["source_mode"] == "fixture"
    assert data["results"]
    assert data["results"][0]["provider"] == "broward_geohub"


@pytest.mark.asyncio
async def test_fixture_backed_harness_endpoints_reject_live_source_mode(
    client: AsyncClient,
) -> None:
    source_catalog = await client.get("/api/v1/source-catalog", params={"source_mode": "live"})
    gis_search = await client.post(
        "/api/v1/gis/search",
        json={"query": "zoning", "county": "Broward", "source_mode": "live"},
    )
    gis_source = await client.get(
        "/api/v1/gis/sources/src_broward_bmsd_zoning",
        params={"source_mode": "live"},
    )
    training_discover = await client.post(
        "/api/v1/training/discover",
        json={"url": "https://www.youtube.com/watch?v=0IS1iFMJ8sQ", "source_mode": "live"},
    )
    training_search = await client.post(
        "/api/v1/training/search",
        json={"keyword": "max land purchase price", "source_mode": "live"},
    )

    for response in (
        source_catalog,
        gis_search,
        gis_source,
        training_discover,
        training_search,
    ):
        assert response.status_code == 501
        assert (
            response.json()["detail"] == "Only fixture source mode is wired in this harness slice"
        )


@pytest.mark.asyncio
async def test_source_catalog_api_includes_cost_assumption_sources(client: AsyncClient) -> None:
    response = await client.get("/api/v1/source-catalog", params={"source_mode": "fixture"})

    assert response.status_code == 200
    data = response.json()
    cost_sources = [item for item in data["sources"] if item["lane"] == "cost_assumptions"]
    assert len(cost_sources) >= 2
    assert any(item["source_type"] == "cost_assumption_config" for item in cost_sources)
    assert any(item["source_type"] == "rental_market_profile" for item in cost_sources)


@pytest.mark.asyncio
async def test_training_discover_api_classifies_youtube_arv_source(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/training/discover",
        json={
            "url": "https://www.youtube.com/watch?v=0IS1iFMJ8sQ",
            "source_mode": "fixture",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["videos"][0]["platform_video_id"] == "0IS1iFMJ8sQ"
    assert "ARV" in data["videos"][0]["metadata"]["tags"]


@pytest.mark.asyncio
async def test_deal_analysis_fixture_run_returns_evented_preliminary_response(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "example Miami-Dade fixture address",
            "analysis_type": "acquisition_memo",
            "source_mode": "fixture",
            "assumptions": {
                "avgUnitSizeSf": 850,
                "efficiencyFactor": 0.85,
                "targetProfitPct": 0.18,
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["run_id"].startswith("run_fixture_")
    assert data["status"] == "completed"
    assert data["source_mode"] == "fixture"
    assert data["verification_status"] == "passed_with_warnings"
    assert data["events_url"].startswith("/api/v1/harness/runs/")
    assert data["events"][0]["type"] == "run.created"
    assert data["events"][-1]["type"] == "run.completed"
    assert len(data["tool_calls"]) >= 6
    assert len(data["calculations"]) == 3
    assert data["artifacts"]["underwriting_stage"]["status"] == "completed"
    assert [stage["key"] for stage in data["pipeline_stages"]] == [
        "site_identification",
        "zoning_evidence",
        "comparables",
        "feasibility",
        "underwriting",
    ]


@pytest.mark.asyncio
async def test_deal_analysis_live_run_uses_shared_executor_with_mocked_tools(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    async def _fake_tool_result(request) -> HarnessToolCallResult:
        return _live_tool_result(
            tool_name=request.tool_name,
            run_id=str(request.run_id),
            args=dict(request.args),
            source_mode=request.source_mode,
        )

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "171 NE 209th Ter, Miami, FL 33179",
            "analysis_type": "acquisition_memo",
            "source_mode": "live",
            "assumptions": {
                "maxFar": 2.0,
                "maxUnits": 16,
                "avgUnitSizeSf": 850,
                "efficiencyFactor": 0.85,
                "monthlyRentPerUnit": 2350,
                "operatingExpensePct": 0.34,
                "capRate": 0.0575,
                "hardCosts": 2900000,
                "softCosts": 580000,
                "contingency": 180000,
                "developerFee": 210000,
                "closingCosts": 65000,
                "financingCosts": 230000,
                "holdingCosts": 95000,
                "sellingCosts": 140000,
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["source_mode"] == "live"
    assert data["verification_status"] == "passed_with_warnings"
    assert data["tool_calls"][0]["tool_name"] == "geocode_address"
    assert len(data["calculations"]) == 4
    assert data["artifacts"]["pipeline_stage_statuses"]["underwriting"] == "completed"
    assert data["artifacts"]["underwriting_stage"]["status"] == "completed"
    assert data["artifacts"]["underwriting_mode"]["mode"] == "income_cap_rate"
    assert data["artifacts"]["cost_assumptions"]["market"] == "South Florida"
    assert data["artifacts"]["cost_assumptions"]["source"] == "market:south_florida"
    assert data["artifacts"]["cost_assumptions"]["requires_official_verification"] is False
    assert data["pipeline_stages"][0]["key"] == "site_identification"
    assert data["pipeline_stages"][-1]["key"] == "underwriting"
    assert any(claim["claim_type"] == "max_supportable_land_price" for claim in data["claims"])
    zoning_claim = next(claim for claim in data["claims"] if claim["claim_type"] == "zoning_code")
    comp_claim = next(
        claim for claim in data["claims"] if claim["claim_type"] == "comp_value_signal"
    )
    evidence_by_id = {item["evidence_id"]: item for item in data["evidence_items"]}
    zoning_claim_source_types = {
        evidence_by_id[evidence_id]["source_type"] for evidence_id in zoning_claim["evidence_ids"]
    }
    comp_claim_source_types = {
        evidence_by_id[evidence_id]["source_type"] for evidence_id in comp_claim["evidence_ids"]
    }
    assert EvidenceSourceType.PARCEL_RECORD.value in zoning_claim_source_types
    assert EvidenceSourceType.ZONING_BOUNDARY.value in zoning_claim_source_types
    assert EvidenceSourceType.ORDINANCE_TEXT.value in zoning_claim_source_types
    assert comp_claim_source_types <= {
        EvidenceSourceType.MARKET_COMP.value,
        EvidenceSourceType.RENTAL_COMP.value,
    }
    assert EvidenceSourceType.MARKET_COMP.value in comp_claim_source_types
    assert EvidenceSourceType.RENTAL_COMP.value in comp_claim_source_types
    evidence_types = {item["source_type"] for item in data["evidence_items"]}
    assert EvidenceSourceType.COST_ASSUMPTION_CONFIG.value in evidence_types
    assert EvidenceSourceType.MARKET_COMP.value in evidence_types
    assert EvidenceSourceType.RENTAL_COMP.value in evidence_types
    underwriting_section = next(
        section
        for section in data["report"]["sections"]
        if section["section_id"] == "underwriting_summary"
    )
    assert underwriting_section["underwriting_mode"]["mode"] == "income_cap_rate"


@pytest.mark.asyncio
async def test_deal_analysis_run_accepts_camel_case_live_request_fields(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    async def _fake_tool_result(request) -> HarnessToolCallResult:
        return _live_tool_result(
            tool_name=request.tool_name,
            run_id=str(request.run_id),
            args=dict(request.args),
            source_mode=request.source_mode,
        )

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "171 NE 209th Ter, Miami, FL 33179",
            "analysisType": "acquisition_memo",
            "sourceMode": "live",
            "assumptions": {
                "maxFar": 2.0,
                "maxUnits": 16,
                "avgUnitSizeSf": 850,
                "efficiencyFactor": 0.85,
                "monthlyRentPerUnit": 2350,
                "operatingExpensePct": 0.34,
                "capRate": 0.0575,
                "hardCosts": 2900000,
                "softCosts": 580000,
                "contingency": 180000,
                "developerFee": 210000,
                "closingCosts": 65000,
                "financingCosts": 230000,
                "holdingCosts": 95000,
                "sellingCosts": 140000,
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["source_mode"] == "live"
    assert data["tool_calls"][0]["tool_name"] == "geocode_address"


@pytest.mark.asyncio
async def test_deal_analysis_live_run_omits_comp_signal_without_qualifying_comp_evidence(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    async def _fake_tool_result(request) -> HarnessToolCallResult:
        payload = (
            _empty_live_comps_payload()
            if request.tool_name == "find_comparables"
            else _live_tool_payload(
                request.tool_name,
                dict(request.args),
            )
        )
        return HarnessToolCallResult(
            ok=True,
            tool_call_id=ToolCallId(f"tool_call_{request.tool_name}"),
            tool_name=request.tool_name,
            run_id=RunId(str(request.run_id)),
            args=dict(request.args),
            status=ToolRouteStatus.COMPLETED,
            policy_decision=PolicyDecision(allowed=True, reason="test"),
            payload=payload,
            events=[],
            source_mode=request.source_mode,
        )

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "171 NE 209th Ter, Miami, FL 33179",
            "analysis_type": "acquisition_memo",
            "source_mode": "live",
            "assumptions": {
                "maxFar": 2.0,
                "maxUnits": 16,
                "avgUnitSizeSf": 850,
                "efficiencyFactor": 0.85,
                "monthlyRentPerUnit": 2350,
                "operatingExpensePct": 0.34,
                "capRate": 0.0575,
                "hardCosts": 2900000,
                "softCosts": 580000,
                "contingency": 180000,
                "developerFee": 210000,
                "closingCosts": 65000,
                "financingCosts": 230000,
                "holdingCosts": 95000,
                "sellingCosts": 140000,
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["source_mode"] == "live"
    assert not any(claim["claim_type"] == "comp_value_signal" for claim in data["claims"])
    assert any(
        "did not return qualifying comps" in warning
        for warning in data["artifacts"].get("warnings", [])
    )


@pytest.mark.asyncio
async def test_deal_analysis_live_run_uses_ordinance_rules_for_feasibility_defaults(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    async def _fake_tool_result(request) -> HarnessToolCallResult:
        if request.tool_name == "geocode_address":
            payload = {
                "status": "success",
                "result": {
                    "address": str(request.args["address"]),
                    "municipality": "Exampleville",
                    "county": "Miami-Dade",
                    "state": "FL",
                    "lat": 25.9001,
                    "lng": -80.2101,
                },
            }
        elif request.tool_name == "lookup_property_info":
            payload = {
                "status": "success",
                "result": {
                    "folio": "0000000000001",
                    "address": "100 Example Ave",
                    "municipality": "Exampleville",
                    "county": "Miami-Dade",
                    "zoning_code": "MXD-1",
                    "ordinance_district_code": "MXD-1",
                    "zoning_description": "Mixed use district",
                    "lot_size_sqft": 12000.0,
                    "living_units": 0,
                    "zoning_layer_url": "https://example.test/exampleville-zoning",
                },
            }
        elif request.tool_name == "search_zoning_ordinance":
            payload = {
                "status": "success",
                "results": [
                    {
                        "section": "Sec. 12-34",
                        "section_id": "sec_12_34",
                        "title": "MXD-1 development standards",
                        "text": "Mixed use standards for MXD-1.",
                        "zone_codes": ["MXD-1"],
                        "rules": {
                            "far": 1.25,
                            "max_density_units_per_acre": 10.0,
                            "min_lot_width_ft": 80.0,
                            "setback_front_ft": 12.0,
                            "setback_side_ft": 6.0,
                            "setback_rear_ft": 18.0,
                            "max_lot_coverage_pct": 55.0,
                            "requires_official_verification": True,
                        },
                        "citation": {
                            "url": "https://library.municode.com/fl/exampleville",
                            "jurisdiction": "Exampleville",
                        },
                    }
                ],
            }
        elif request.tool_name == "compute_feasibility":
            assert request.args["max_far"] == pytest.approx(1.25)
            assert request.args["max_units"] == 2
            assert request.args["lot_frontage_ft"] == pytest.approx(80.0)
            assert request.args["setback_front_ft"] == pytest.approx(12.0)
            assert request.args["setback_side_ft"] == pytest.approx(6.0)
            assert request.args["setback_rear_ft"] == pytest.approx(18.0)
            assert request.args["max_lot_coverage_pct"] == pytest.approx(55.0)
            payload = {
                "result": {
                    "calculation_type": "feasibility",
                    "formula_version": "feasibility.v2",
                    "max_gross_buildable_sf": 15000.0,
                    "net_rentable_sf": 12750.0,
                    "estimated_units": 2,
                    "parking_required": 3,
                    "major_constraints": ["density"],
                    "feasibility_warnings": [],
                }
            }
        else:
            payload = _live_tool_payload(request.tool_name, dict(request.args))
        return HarnessToolCallResult(
            ok=True,
            tool_call_id=ToolCallId(f"tool_call_{request.tool_name}"),
            tool_name=request.tool_name,
            run_id=RunId(str(request.run_id)),
            args=dict(request.args),
            status=ToolRouteStatus.COMPLETED,
            policy_decision=PolicyDecision(allowed=True, reason="test"),
            payload=payload,
            events=[],
            source_mode=request.source_mode,
        )

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "100 Example Ave, Exampleville, FL 33000",
            "analysis_type": "acquisition_memo",
            "source_mode": "live",
            "assumptions": {
                "avgUnitSizeSf": 900,
                "efficiencyFactor": 0.85,
                "monthlyRentPerUnit": 2400,
                "operatingExpensePct": 0.35,
                "capRate": 0.06,
                "hardCosts": 450000,
                "softCosts": 90000,
                "contingency": 30000,
                "developerFee": 40000,
                "closingCosts": 15000,
                "financingCosts": 35000,
                "holdingCosts": 18000,
                "sellingCosts": 25000,
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["artifacts"]["ordinance_rules"]["far"] == pytest.approx(1.25)
    assert data["artifacts"]["ordinance_rules"]["max_density_units_per_acre"] == pytest.approx(10.0)
    assert data["artifacts"]["ordinance_rules"]["min_lot_width_ft"] == pytest.approx(80.0)
    assert data["artifacts"]["feasibility"]["result"]["estimated_units"] == 2
    underwriting_section = next(
        section
        for section in data["report"]["sections"]
        if section["section_id"] == "underwriting_summary"
    )
    assert underwriting_section["zoning_support_summary"]["status"] == "warning"
    assert underwriting_section["zoning_support_summary"]["ordinance_rules_resolved"] is True
    assert underwriting_section["zoning_support_summary"]["requires_official_verification"] is True
    assert underwriting_section["zoning_support_summary"]["ordinance_source"] == "ordinance_search"
    assert (
        underwriting_section["zoning_support_summary"]["authority_confidence"]
        == "indexed_official_reference"
    )
    assert underwriting_section["zoning_support_summary"]["authority_is_live"] is False
    assert any(
        "ordinance-derived dimensional defaults" in warning
        for warning in data["artifacts"].get("warnings", [])
    )


@pytest.mark.asyncio
async def test_deal_analysis_live_run_uses_property_municipality_for_comps_lookup(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    async def _fake_tool_result(request) -> HarnessToolCallResult:
        if request.tool_name == "lookup_property_info":
            payload = {
                "status": "success",
                "result": {
                    "folio": "30-2206-013-0310",
                    "address": str(request.args["address"]),
                    "municipality": "Miami Gardens",
                    "county": "Miami-Dade",
                    "zoning_code": "R-1",
                    "ordinance_district_code": "R-1",
                    "zoning_description": "Single Family Residential",
                    "lot_size_sqft": 7500,
                    "living_units": 1,
                    "zoning_layer_url": "https://example.test/zoning",
                },
            }
        else:
            payload = _live_tool_payload(request.tool_name, dict(request.args))
        if request.tool_name == "find_comparables":
            assert request.args["municipality"] == "Miami Gardens"
            assert request.args["living_units"] == 1
        return HarnessToolCallResult(
            ok=True,
            tool_call_id=ToolCallId(f"tool_call_{request.tool_name}"),
            tool_name=request.tool_name,
            run_id=RunId(str(request.run_id)),
            args=dict(request.args),
            status=ToolRouteStatus.COMPLETED,
            policy_decision=PolicyDecision(allowed=True, reason="test"),
            payload=payload,
            events=[],
            source_mode=request.source_mode,
        )

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "171 NE 209th Ter, Miami, FL 33179",
            "analysis_type": "acquisition_memo",
            "source_mode": "live",
            "assumptions": {
                "maxFar": 2.0,
                "maxUnits": 16,
                "avgUnitSizeSf": 850,
                "efficiencyFactor": 0.85,
                "monthlyRentPerUnit": 2350,
                "operatingExpensePct": 0.34,
                "capRate": 0.0575,
                "hardCosts": 2900000,
                "softCosts": 580000,
                "contingency": 180000,
                "developerFee": 210000,
                "closingCosts": 65000,
                "financingCosts": 230000,
                "holdingCosts": 95000,
                "sellingCosts": 140000,
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    comp_call = next(call for call in data["tool_calls"] if call["tool_name"] == "find_comparables")
    assert comp_call["args"]["municipality"] == "Miami Gardens"


@pytest.mark.asyncio
async def test_deal_analysis_live_run_uses_pro_forma_when_noi_inputs_are_missing(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    async def _fake_tool_result(request) -> HarnessToolCallResult:
        payload = _live_tool_payload(request.tool_name, dict(request.args))
        if request.tool_name == "run_pro_forma":
            assert request.args["max_units"] == 16
            assert request.args["state"] == "FL"
            assert request.args["county"] == "Miami-Dade"
        return HarnessToolCallResult(
            ok=True,
            tool_call_id=ToolCallId(f"tool_call_{request.tool_name}"),
            tool_name=request.tool_name,
            run_id=RunId(str(request.run_id)),
            args=dict(request.args),
            status=ToolRouteStatus.COMPLETED,
            policy_decision=PolicyDecision(allowed=True, reason="test"),
            payload=payload,
            events=[],
            source_mode=request.source_mode,
        )

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "171 NE 209th Ter, Miami, FL 33179",
            "analysis_type": "acquisition_memo",
            "source_mode": "live",
            "assumptions": {
                "maxUnits": 16,
                "avgUnitSizeSf": 850,
                "efficiencyFactor": 0.85,
                "monthlyRentPerUnit": 2350,
                "operatingExpensePct": 0.34,
                "capRate": 0.0575,
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert any(call["tool_name"] == "run_pro_forma" for call in data["tool_calls"])
    assert "pro_forma" in data["artifacts"]
    assert any(claim["claim_type"] == "max_supportable_land_price" for claim in data["claims"])
    assert not any(
        "NOI valuation skipped" in warning for warning in data["artifacts"].get("warnings", [])
    )
    assert "noi_valuation" in data["artifacts"]


@pytest.mark.asyncio
async def test_deal_analysis_live_run_skips_pro_forma_when_only_land_comps_exist(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    async def _fake_tool_result(request) -> HarnessToolCallResult:
        payload = (
            _land_only_live_comps_payload()
            if request.tool_name == "find_comparables"
            else _live_tool_payload(request.tool_name, dict(request.args))
        )
        if request.tool_name == "run_pro_forma":
            raise AssertionError(
                "run_pro_forma should not be called without qualified sold-unit comps"
            )
        return HarnessToolCallResult(
            ok=True,
            tool_call_id=ToolCallId(f"tool_call_{request.tool_name}"),
            tool_name=request.tool_name,
            run_id=RunId(str(request.run_id)),
            args=dict(request.args),
            status=ToolRouteStatus.COMPLETED,
            policy_decision=PolicyDecision(allowed=True, reason="test"),
            payload=payload,
            events=[],
            source_mode=request.source_mode,
        )

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "171 NE 209th Ter, Miami, FL 33179",
            "analysis_type": "acquisition_memo",
            "source_mode": "live",
            "assumptions": {
                "maxUnits": 4,
                "avgUnitSizeSf": 850,
                "efficiencyFactor": 0.85,
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert not any(call["tool_name"] == "run_pro_forma" for call in data["tool_calls"])
    assert "pro_forma" not in data["artifacts"]
    assert any(
        "did not establish a qualified after-development value per unit" in warning
        for warning in data["artifacts"].get("warnings", [])
    )


@pytest.mark.asyncio
async def test_deal_analysis_live_run_uses_market_income_defaults_for_multifamily(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    observed_noi_args: dict[str, object] = {}

    async def _fake_tool_result(request) -> HarnessToolCallResult:
        payload = _live_tool_payload(request.tool_name, dict(request.args))
        if request.tool_name == "compute_feasibility":
            payload = {
                "result": {
                    "calculation_type": "feasibility",
                    "formula_version": "feasibility.v1",
                    "max_gross_buildable_sf": 16000.0,
                    "net_rentable_sf": 13600.0,
                    "estimated_units": 16,
                    "parking_required": 24,
                    "major_constraints": [],
                    "feasibility_warnings": [],
                }
            }
        if request.tool_name == "run_noi_valuation":
            observed_noi_args.update(dict(request.args))
        return HarnessToolCallResult(
            ok=True,
            tool_call_id=ToolCallId(f"tool_call_{request.tool_name}"),
            tool_name=request.tool_name,
            run_id=RunId(str(request.run_id)),
            args=dict(request.args),
            status=ToolRouteStatus.COMPLETED,
            policy_decision=PolicyDecision(allowed=True, reason="test"),
            payload=payload,
            events=[],
            source_mode=request.source_mode,
        )

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "171 NE 209th Ter, Miami, FL 33179",
            "analysis_type": "acquisition_memo",
            "source_mode": "live",
            "assumptions": {
                "maxUnits": 16,
                "avgUnitSizeSf": 850,
                "efficiencyFactor": 0.85,
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["verification_status"] == "passed_with_warnings"
    assert any(call["tool_name"] == "run_pro_forma" for call in data["tool_calls"])
    assert any(call["tool_name"] == "run_noi_valuation" for call in data["tool_calls"])
    assert observed_noi_args["monthly_rent_per_unit"] == pytest.approx(2250.0)
    assert observed_noi_args["vacancy_pct"] == pytest.approx(0.05)
    assert observed_noi_args["operating_expense_pct"] == pytest.approx(0.35)
    assert observed_noi_args["cap_rate"] == pytest.approx(0.06)
    assert "pro_forma" in data["artifacts"]
    assert "noi_valuation" in data["artifacts"]
    assert data["artifacts"]["underwriting_stage"]["status"] == "partial"
    assert data["artifacts"]["underwriting_mode"]["mode"] == "income_cap_rate"
    assert data["artifacts"]["cost_assumptions"]["monthly_rent_per_unit"] == pytest.approx(2250.0)
    assert data["artifacts"]["cost_assumptions"]["cap_rate"] == pytest.approx(0.06)
    assert data["artifacts"]["cost_assumptions"]["requires_income_assumption_verification"] is True
    underwriting_section = next(
        section
        for section in data["report"]["sections"]
        if section["section_id"] == "underwriting_summary"
    )
    assert underwriting_section["underwriting_mode"]["mode"] == "income_cap_rate"
    assert any(
        "market rent or cap-rate defaults" in warning
        for warning in data["artifacts"].get("warnings", [])
    )


@pytest.mark.asyncio
async def test_deal_analysis_live_run_uses_feasibility_units_for_noi_when_income_inputs_exist(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    async def _fake_tool_result(request) -> HarnessToolCallResult:
        payload = _live_tool_payload(request.tool_name, dict(request.args))
        if request.tool_name == "lookup_property_info":
            payload = {
                "status": "success",
                "result": {
                    "folio": "0131360600010",
                    "address": "1603 NW 7 AVE",
                    "municipality": "Miami",
                    "county": "Miami-Dade",
                    "zoning_code": "CI-HD",
                    "zoning_description": "",
                    "lot_size_sqft": 43560,
                    "living_units": 0,
                    "lat": 25.790642,
                    "lng": -80.20681,
                    "zoning_layer_url": "",
                },
            }
        if request.tool_name == "web_search":
            payload = {
                "status": "success",
                "provider": "exa",
                "results": [
                    {
                        "title": "View City of Miami Zoning Code (Miami 21)",
                        "url": "https://www.miami.gov/Planning-Zoning-Land-Use/View-City-of-Miami-Zoning-Code-Miami-21",
                        "description": "Official City of Miami Miami 21 code page.",
                        "content": "CI-HD official Miami 21 zoning code reference.",
                        "citation": {
                            "url": "https://www.miami.gov/Planning-Zoning-Land-Use/View-City-of-Miami-Zoning-Code-Miami-21",
                            "jurisdiction": "Miami",
                        },
                    }
                ],
            }
        if request.tool_name == "compute_feasibility":
            payload = {
                "result": {
                    "calculation_type": "feasibility",
                    "formula_version": "feasibility.v1",
                    "max_gross_buildable_sf": 348480.0,
                    "net_rentable_sf": 296208.0,
                    "estimated_units": 150,
                    "parking_required": 225,
                    "major_constraints": ["max_units"],
                    "feasibility_warnings": [],
                }
            }
        if request.tool_name == "run_noi_valuation":
            assert request.args["unit_count"] == 150
        return HarnessToolCallResult(
            ok=True,
            tool_call_id=ToolCallId(f"tool_call_{request.tool_name}"),
            tool_name=request.tool_name,
            run_id=RunId(str(request.run_id)),
            args=dict(request.args),
            status=ToolRouteStatus.COMPLETED,
            policy_decision=PolicyDecision(allowed=True, reason="test"),
            payload=payload,
            events=[],
            source_mode=request.source_mode,
        )

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "1600 NW 7th Ave, Miami, FL 33136",
            "analysis_type": "acquisition_memo",
            "source_mode": "live",
            "assumptions": {
                "avgUnitSizeSf": 850,
                "efficiencyFactor": 0.85,
                "monthlyRentPerUnit": 2800,
                "operatingExpensePct": 0.35,
                "capRate": 0.06,
                "hardCosts": 45000000,
                "softCosts": 9000000,
                "contingency": 4500000,
                "developerFee": 6000000,
                "closingCosts": 1200000,
                "financingCosts": 7000000,
                "holdingCosts": 2500000,
                "sellingCosts": 3500000,
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert any(call["tool_name"] == "run_noi_valuation" for call in data["tool_calls"])
    assert "noi_valuation" in data["artifacts"]
    assert data["artifacts"]["underwriting_stage"]["status"] == "completed"
    assert data["artifacts"]["underwriting_mode"]["mode"] == "income_cap_rate"
    assert data["artifacts"]["cost_assumptions"]["market"] == "South Florida"
    assert data["artifacts"]["cost_assumptions"]["source"] == "market:south_florida"
    underwriting_section = next(
        section
        for section in data["report"]["sections"]
        if section["section_id"] == "underwriting_summary"
    )
    assert underwriting_section["underwriting_mode"]["mode"] == "income_cap_rate"


@pytest.mark.asyncio
async def test_deal_analysis_live_run_uses_south_florida_market_income_defaults_for_broward(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    observed_noi_args: dict[str, object] = {}

    async def _fake_tool_result(request) -> HarnessToolCallResult:
        if request.tool_name == "geocode_address":
            payload = {
                "status": "success",
                "result": {
                    "address": str(request.args["address"]),
                    "municipality": "Fort Lauderdale",
                    "county": "Broward",
                    "state": "FL",
                    "lat": 26.1404,
                    "lng": -80.1592,
                },
            }
        elif request.tool_name == "lookup_property_info":
            payload = {
                "status": "success",
                "result": {
                    "folio": "494233281490",
                    "address": str(request.args["address"]),
                    "municipality": "Fort Lauderdale",
                    "county": "Broward",
                    "zoning_code": "RMM-25",
                    "ordinance_district_code": "RMM-25",
                    "zoning_description": "Residential multifamily",
                    "lot_size_sqft": 12000,
                    "living_units": 0,
                    "lat": 26.1404,
                    "lng": -80.1592,
                    "zoning_layer_url": "https://example.test/ftl-zoning",
                },
            }
        elif request.tool_name == "compute_feasibility":
            payload = {
                "result": {
                    "calculation_type": "feasibility",
                    "formula_version": "feasibility.v1",
                    "max_gross_buildable_sf": 24000.0,
                    "net_rentable_sf": 20400.0,
                    "estimated_units": 12,
                    "parking_required": 18,
                    "major_constraints": ["max_units"],
                    "feasibility_warnings": [],
                }
            }
        elif request.tool_name == "run_noi_valuation":
            observed_noi_args.update(dict(request.args))
            payload = _live_tool_payload(request.tool_name, dict(request.args))
        else:
            payload = _live_tool_payload(request.tool_name, dict(request.args))

        return HarnessToolCallResult(
            ok=True,
            tool_call_id=ToolCallId(f"tool_call_{request.tool_name}"),
            tool_name=request.tool_name,
            run_id=RunId(str(request.run_id)),
            args=dict(request.args),
            status=ToolRouteStatus.COMPLETED,
            policy_decision=PolicyDecision(allowed=True, reason="test"),
            payload=payload,
            events=[],
            source_mode=request.source_mode,
        )

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "1234 NW 15th St, Fort Lauderdale, FL 33311",
            "analysis_type": "acquisition_memo",
            "source_mode": "live",
            "assumptions": {
                "maxFar": 2.0,
                "maxUnits": 12,
                "avgUnitSizeSf": 850,
                "efficiencyFactor": 0.85,
                "hardCosts": 3900000,
                "softCosts": 780000,
                "contingency": 240000,
                "developerFee": 320000,
                "closingCosts": 90000,
                "financingCosts": 260000,
                "holdingCosts": 110000,
                "sellingCosts": 170000,
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert any(call["tool_name"] == "run_noi_valuation" for call in data["tool_calls"])
    assert any(call["tool_name"] == "run_residual_land_value" for call in data["tool_calls"])
    assert observed_noi_args["unit_count"] == 12
    assert observed_noi_args["monthly_rent_per_unit"] == pytest.approx(2250.0)
    assert observed_noi_args["vacancy_pct"] == pytest.approx(0.05)
    assert observed_noi_args["operating_expense_pct"] == pytest.approx(0.35)
    assert observed_noi_args["cap_rate"] == pytest.approx(0.06)
    assert data["artifacts"]["underwriting_stage"]["status"] == "completed"
    assert data["artifacts"]["underwriting_mode"]["mode"] == "income_cap_rate"
    assert data["artifacts"]["cost_assumptions"]["market"] == "South Florida"
    assert data["artifacts"]["cost_assumptions"]["monthly_rent_per_unit"] == pytest.approx(2250.0)
    assert data["artifacts"]["cost_assumptions"]["operating_expense_pct"] == pytest.approx(0.35)
    assert data["artifacts"]["cost_assumptions"]["cap_rate"] == pytest.approx(0.06)
    assert data["artifacts"]["cost_assumptions"]["requires_income_assumption_verification"] is True
    assert any(
        "market rent or cap-rate defaults" in warning
        for warning in data["artifacts"].get("warnings", [])
    )


@pytest.mark.asyncio
async def test_deal_analysis_live_income_path_keeps_cost_assumptions_when_pro_forma_is_skipped(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    observed_noi_args: dict[str, object] = {}

    async def _fake_tool_result(request) -> HarnessToolCallResult:
        if request.tool_name == "find_comparables":
            payload = _empty_live_comps_payload()
        elif request.tool_name == "compute_feasibility":
            payload = {
                "result": {
                    "calculation_type": "feasibility",
                    "formula_version": "feasibility.v1",
                    "max_gross_buildable_sf": 16000.0,
                    "net_rentable_sf": 13600.0,
                    "estimated_units": 16,
                    "parking_required": 24,
                    "major_constraints": [],
                    "feasibility_warnings": [],
                }
            }
        elif request.tool_name == "run_noi_valuation":
            observed_noi_args.update(dict(request.args))
            payload = _live_tool_payload(request.tool_name, dict(request.args))
        else:
            payload = _live_tool_payload(request.tool_name, dict(request.args))
        return HarnessToolCallResult(
            ok=True,
            tool_call_id=ToolCallId(f"tool_call_{request.tool_name}"),
            tool_name=request.tool_name,
            run_id=RunId(str(request.run_id)),
            args=dict(request.args),
            status=ToolRouteStatus.COMPLETED,
            policy_decision=PolicyDecision(allowed=True, reason="test"),
            payload=payload,
            events=[],
            source_mode=request.source_mode,
        )

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "171 NE 209th Ter, Miami, FL 33179",
            "analysis_type": "acquisition_memo",
            "source_mode": "live",
            "assumptions": {
                "maxUnits": 16,
                "avgUnitSizeSf": 850,
                "efficiencyFactor": 0.85,
                "hardCosts": 2900000,
                "softCosts": 580000,
                "contingency": 180000,
                "developerFee": 210000,
                "closingCosts": 65000,
                "financingCosts": 230000,
                "holdingCosts": 95000,
                "sellingCosts": 140000,
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "pro_forma" not in data["artifacts"]
    assert data["artifacts"]["underwriting_mode"]["mode"] == "blocked_by_comping_gate"
    assert observed_noi_args == {}
    assert "cost_assumptions" in data["artifacts"]
    evidence_types = {item["source_type"] for item in data["evidence_items"]}
    assert EvidenceSourceType.COST_ASSUMPTION_CONFIG.value in evidence_types


@pytest.mark.asyncio
async def test_deal_analysis_live_run_infers_single_unit_for_vacant_r1_lot(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    observed_pro_forma_args: dict[str, object] = {}
    observed_noi_args: dict[str, object] = {}

    async def _fake_tool_result(request) -> HarnessToolCallResult:
        if request.tool_name == "geocode_address":
            address = str(request.args["address"])
            if "17605 NW 19th Avenue" in address:
                payload = {
                    "status": "success",
                    "result": {
                        "address": address,
                        "municipality": "Miami Gardens",
                        "county": "Miami-Dade",
                        "state": "FL",
                        "lat": 25.9361,
                        "lng": -80.2322,
                    },
                }
            else:
                payload = {
                    "status": "success",
                    "result": {
                        "address": address,
                        "municipality": "Miami Gardens",
                        "county": "Miami-Dade",
                        "state": "FL",
                        "lat": 25.967404,
                        "lng": -80.202576,
                    },
                }
        elif request.tool_name == "lookup_property_info":
            address = str(request.args["address"])
            if "17605 NW 19th Avenue" in address:
                payload = {
                    "status": "success",
                    "result": {
                        "folio": "3412110001000",
                        "address": "17605 NW 19th Avenue",
                        "municipality": "Miami Gardens",
                        "county": "Miami-Dade",
                        "zoning_code": "R-1",
                        "ordinance_district_code": "R-1",
                        "zoning_description": "Single-family dwelling residential district",
                        "land_use_code": "0066",
                        "land_use_description": "VACANT RESIDENTIAL",
                        "lot_size_sqft": 9000.0,
                        "living_units": 0,
                        "lat": 25.9361,
                        "lng": -80.2322,
                        "last_sale_price": 135000.0,
                        "zoning_layer_url": "https://example.test/miami-gardens-zoning",
                    },
                }
            else:
                payload = {
                    "status": "success",
                    "result": {
                        "folio": "3411360031910",
                        "address": "45 NW 209 ST",
                        "municipality": "Miami Gardens",
                        "county": "Miami-Dade",
                        "zoning_code": "R-1",
                        "ordinance_district_code": "R-1",
                        "zoning_description": "Single-family dwelling residential district",
                        "land_use_code": "0066",
                        "land_use_description": "VACANT RESIDENTIAL",
                        "lot_size_sqft": 10105.0,
                        "living_units": 0,
                        "lat": 25.967404,
                        "lng": -80.202576,
                        "zoning_layer_url": "https://example.test/miami-gardens-zoning",
                    },
                }
        elif request.tool_name == "find_comparables":
            payload = {
                "analysis": {
                    "comparables": [],
                    "median_price_per_acre": 0.0,
                    "estimated_land_value": 0.0,
                    "price_per_acre_low": 0.0,
                    "price_per_acre_high": 0.0,
                    "estimated_land_value_low": 0.0,
                    "estimated_land_value_high": 0.0,
                    "adv_per_unit": 505000.0,
                    "adv_per_unit_low": 485000.0,
                    "adv_per_unit_high": 602000.0,
                    "adv_source": "comps",
                    "unit_comparables": [
                        {
                            "address": "105 NE 213 ST",
                            "sale_price": 699000.0,
                            "sale_date": "2026-04-21",
                            "lot_size_sqft": 7500.0,
                            "zoning_code": "",
                            "distance_miles": 0.34,
                            "price_per_acre": 0.0,
                            "price_per_unit": 699000.0,
                            "adjustments": {},
                        },
                        {
                            "address": "220 NE 211 ST",
                            "sale_price": 505000.0,
                            "sale_date": "2026-05-05",
                            "lot_size_sqft": 3007.0,
                            "zoning_code": "",
                            "distance_miles": 0.38,
                            "price_per_acre": 0.0,
                            "price_per_unit": 505000.0,
                            "adjustments": {},
                        },
                        {
                            "address": "221 NE 212 ST",
                            "sale_price": 465000.0,
                            "sale_date": "2026-04-23",
                            "lot_size_sqft": 3023.0,
                            "zoning_code": "",
                            "distance_miles": 0.42,
                            "price_per_acre": 0.0,
                            "price_per_unit": 465000.0,
                            "adjustments": {},
                        },
                    ],
                    "confidence": 0.55,
                    "notes": [
                        "No reliable vacant-land comps within 24 months; using nearby improved single-family sales for exit pricing only."
                    ],
                }
            }
        elif request.tool_name == "run_pro_forma":
            observed_pro_forma_args.update(dict(request.args))
            payload = _live_tool_payload(request.tool_name, dict(request.args))
        elif request.tool_name == "run_noi_valuation":
            observed_noi_args.update(dict(request.args))
            payload = _live_tool_payload(request.tool_name, dict(request.args))
        else:
            payload = _live_tool_payload(request.tool_name, dict(request.args))
        return HarnessToolCallResult(
            ok=True,
            tool_call_id=ToolCallId(f"tool_call_{request.tool_name}"),
            tool_name=request.tool_name,
            run_id=RunId(str(request.run_id)),
            args=dict(request.args),
            status=ToolRouteStatus.COMPLETED,
            policy_decision=PolicyDecision(allowed=True, reason="test"),
            payload=payload,
            events=[],
            source_mode=request.source_mode,
        )

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "45 NW 209 ST, Miami Gardens, FL 33169",
            "analysis_type": "acquisition_memo",
            "source_mode": "live",
            "assumptions": {
                "avgUnitSizeSf": 1800,
                "monthlyRentPerUnit": 3200,
                "operatingExpensePct": 0.35,
                "capRate": 0.06,
                "hardCosts": 265000,
                "softCosts": 53000,
                "contingency": 20000,
                "developerFee": 25000,
                "closingCosts": 12000,
                "financingCosts": 18000,
                "holdingCosts": 12000,
                "sellingCosts": 35000,
                "targetProfitPct": 0.18,
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["artifacts"]["feasibility"]["estimated_units"] > 0
    assert observed_noi_args == {}
    assert data["artifacts"]["underwriting_mode"]["mode"] == "blocked_by_comping_gate"
    assert observed_pro_forma_args == {}
    assert not any(call["tool_name"] == "run_residual_land_value" for call in data["tool_calls"])
    assert any(
        "No reliable vacant-land comps" in note for note in data["artifacts"]["comps"]["notes"]
    )


@pytest.mark.asyncio
async def test_deal_analysis_live_run_uses_staged_vacant_lot_comp_search_and_guidance(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    observed_searches: list[tuple[int, float]] = []

    async def _fake_tool_result(request) -> HarnessToolCallResult:
        if request.tool_name == "geocode_address":
            payload = {
                "status": "success",
                "result": {
                    "address": str(request.args["address"]),
                    "municipality": "Miami Gardens",
                    "county": "Miami-Dade",
                    "state": "FL",
                    "lat": 25.967404,
                    "lng": -80.202576,
                },
            }
        elif request.tool_name == "lookup_property_info":
            payload = {
                "status": "success",
                "result": {
                    "folio": "3411360031910",
                    "address": "45 NW 209 ST",
                    "municipality": "Miami Gardens",
                    "county": "Miami-Dade",
                    "zoning_code": "R-1",
                    "ordinance_district_code": "R-1",
                    "zoning_description": "Single-family dwelling residential district",
                    "land_use_code": "0066",
                    "land_use_description": "VACANT RESIDENTIAL",
                    "lot_size_sqft": 10105.0,
                    "living_units": 0,
                    "lat": 25.967404,
                    "lng": -80.202576,
                    "zoning_layer_url": "https://example.test/miami-gardens-zoning",
                },
            }
        elif request.tool_name == "find_comparables":
            observed_searches.append(
                (int(request.args["months"]), float(request.args["radius_miles"]))
            )
            months = int(request.args["months"])
            radius_miles = float(request.args["radius_miles"])
            if months in {6, 12} or (months == 24 and radius_miles == 3.0):
                payload = {"analysis": _empty_live_comps_payload()}
            else:
                payload = {
                    "analysis": {
                        "comparables": [
                            {
                                "address": "17605 NW 19th Avenue",
                                "sale_price": 145000.0,
                                "sale_date": "2026-02-01",
                                "lot_size_sqft": 9500.0,
                                "zoning_code": "R-1",
                                "distance_miles": 4.12,
                                "price_per_acre": 665789.47,
                                "adjustments": {},
                            }
                        ],
                        "median_price_per_acre": 665789.47,
                        "estimated_land_value": 154391.78,
                        "price_per_acre_low": 665789.47,
                        "price_per_acre_high": 665789.47,
                        "estimated_land_value_low": 154391.78,
                        "estimated_land_value_high": 154391.78,
                        "adv_per_unit": 505000.0,
                        "adv_per_unit_low": 485000.0,
                        "adv_per_unit_high": 602000.0,
                        "adv_source": "comps",
                        "unit_comparables": [
                            {
                                "address": "105 NE 213 ST",
                                "sale_price": 699000.0,
                                "sale_date": "2026-04-21",
                                "lot_size_sqft": 7500.0,
                                "zoning_code": "",
                                "distance_miles": 0.34,
                                "price_per_acre": 0.0,
                                "price_per_unit": 699000.0,
                                "adjustments": {"qualification_score": 0.92},
                            },
                            {
                                "address": "220 NE 211 ST",
                                "sale_price": 505000.0,
                                "sale_date": "2026-05-05",
                                "lot_size_sqft": 3007.0,
                                "zoning_code": "",
                                "distance_miles": 0.38,
                                "price_per_acre": 0.0,
                                "price_per_unit": 505000.0,
                                "adjustments": {"qualification_score": 0.88},
                            },
                        ],
                        "confidence": 0.55,
                        "notes": [
                            "No reliable vacant-land comps within 24 months; using nearby improved single-family sales for exit pricing only."
                        ],
                    }
                }
        elif request.tool_name == "run_residual_land_value":
            payload = {
                "result": {
                    "calculation_type": "residual_land_value",
                    "formula_version": "residual_land_value.v1",
                    "total_project_costs_excluding_land": 425000.0,
                    "max_supportable_land_price": -95000.0,
                    "spread_to_asking_price": -95000.0,
                    "go_no_go_signal": "no_go",
                    "warnings": [
                        "Negative residual land value: costs and profit exceed as-built value."
                    ],
                }
            }
        else:
            payload = _live_tool_payload(request.tool_name, dict(request.args))

        return HarnessToolCallResult(
            ok=True,
            tool_call_id=ToolCallId(f"tool_call_{request.tool_name}_{len(observed_searches)}"),
            tool_name=request.tool_name,
            run_id=RunId(str(request.run_id)),
            args=dict(request.args),
            status=ToolRouteStatus.COMPLETED,
            policy_decision=PolicyDecision(allowed=True, reason="test"),
            payload=payload,
            events=[],
            source_mode=request.source_mode,
        )

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "45 NW 209 ST, Miami Gardens, FL 33169",
            "analysis_type": "acquisition_memo",
            "source_mode": "live",
            "assumptions": {
                "maxUnits": 1,
                "maxFar": 0.8,
                "avgUnitSizeSf": 1800,
                "monthlyRentPerUnit": 3200,
                "operatingExpensePct": 0.35,
                "capRate": 0.06,
                "hardCosts": 265000,
                "softCosts": 53000,
                "contingency": 20000,
                "developerFee": 25000,
                "closingCosts": 12000,
                "financingCosts": 18000,
                "holdingCosts": 12000,
                "sellingCosts": 35000,
                "targetProfitPct": 0.18,
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert observed_searches == [(6, 3.0), (12, 3.0), (24, 3.0), (24, 6.0)]
    assert data["artifacts"]["comp_search_strategy"]["selected_months"] == 24
    assert (
        data["artifacts"]["comp_search_strategy"]["selected_reason"]
        == "qualified_exit_comp_fallback"
    )
    assert data["artifacts"]["comp_search_strategy"]["attempts"][-1][
        "radius_miles"
    ] == pytest.approx(6.0)
    assert data["artifacts"]["comp_search_strategy"]["attempts"][-1]["land_comp_count"] == 1
    assert data["artifacts"]["comp_search_strategy"]["attempts"][-1]["scored_land_comp_count"] == 0
    assert data["artifacts"]["comp_search_strategy"]["attempts"][-1]["strong_land_comp_count"] == 0
    assert (
        data["artifacts"]["comp_search_strategy"]["attempts"][-1]["direct_land_comp_signal"]
        is False
    )
    assert data["artifacts"]["comp_search_strategy"]["attempts"][-1]["scored_unit_comp_count"] == 2
    assert data["artifacts"]["comp_search_strategy"]["attempts"][-1]["strong_unit_comp_count"] == 2
    assert (
        data["artifacts"]["comp_search_strategy"]["attempts"][-1]["qualified_exit_comp_signal"]
        is True
    )
    assert (
        data["artifacts"]["comp_search_strategy"]["attempts"][-1]["selection_reason"]
        == "qualified_exit_comp_fallback"
    )
    assert data["artifacts"]["acquisition_guidance"]["recommended_action"] == "no_offer"
    assert data["artifacts"]["acquisition_guidance"]["basis"] == "negative_residual"
    assert data["artifacts"]["acquisition_guidance"]["land_comp_signal_available"] is False
    assert data["artifacts"]["acquisition_guidance"]["exit_comp_signal_available"] is True
    assert data["artifacts"]["acquisition_guidance"]["market_land_value_low"] == pytest.approx(
        154391.78
    )
    assert data["artifacts"]["acquisition_guidance"]["market_land_value_high"] == pytest.approx(
        154391.78
    )
    assert data["artifacts"]["acquisition_guidance"]["market_to_residual_gap"] == pytest.approx(
        249391.78
    )
    assert data["artifacts"]["comp_search_strategy"]["attempts"][-1][
        "adv_per_unit"
    ] == pytest.approx(505000.0)


@pytest.mark.asyncio
async def test_deal_analysis_live_run_prefers_sold_unit_exit_for_vacant_lot_without_explicit_income_inputs(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    observed_noi_args: dict[str, object] = {}
    observed_residual_args: dict[str, object] = {}

    async def _fake_tool_result(request) -> HarnessToolCallResult:
        if request.tool_name == "geocode_address":
            requested_address = str(request.args["address"])
            if "17605 NW 19th" in requested_address:
                payload = {
                    "status": "success",
                    "result": {
                        "address": requested_address,
                        "municipality": "Miami Gardens",
                        "county": "Miami-Dade",
                        "state": "FL",
                        "lat": 25.936991,
                        "lng": -80.235842,
                    },
                }
            else:
                payload = {
                    "status": "success",
                    "result": {
                        "address": requested_address,
                        "municipality": "Miami Gardens",
                        "county": "Miami-Dade",
                        "state": "FL",
                        "lat": 25.967404,
                        "lng": -80.202576,
                    },
                }
        elif request.tool_name == "lookup_property_info":
            requested_address = str(request.args["address"])
            if "17605 NW 19th" in requested_address:
                payload = {
                    "status": "success",
                    "result": {
                        "folio": "3412110001000",
                        "address": "17605 NW 19th Avenue",
                        "municipality": "Miami Gardens",
                        "county": "Miami-Dade",
                        "zoning_code": "R-1",
                        "ordinance_district_code": "R-1",
                        "zoning_description": "Single-family dwelling residential district",
                        "land_use_code": "0066",
                        "land_use_description": "VACANT RESIDENTIAL",
                        "lot_size_sqft": 9000.0,
                        "living_units": 0,
                        "last_sale_price": 135000.0,
                        "last_sale_date": "2026-04-30",
                        "lat": 25.936991,
                        "lng": -80.235842,
                        "zoning_layer_url": "https://example.test/miami-gardens-zoning",
                    },
                }
            else:
                payload = {
                    "status": "success",
                    "result": {
                        "folio": "3411360031910",
                        "address": "45 NW 209 ST",
                        "municipality": "Miami Gardens",
                        "county": "Miami-Dade",
                        "zoning_code": "R-1",
                        "ordinance_district_code": "R-1",
                        "zoning_description": "Single-family dwelling residential district",
                        "land_use_code": "0066",
                        "land_use_description": "VACANT RESIDENTIAL",
                        "lot_size_sqft": 10105.0,
                        "living_units": 0,
                        "lat": 25.967404,
                        "lng": -80.202576,
                        "zoning_layer_url": "https://example.test/miami-gardens-zoning",
                    },
                }
        elif request.tool_name == "find_comparables":
            payload = {
                "analysis": {
                    "comparables": [],
                    "unit_comparables": [
                        {
                            "address": "105 NE 213 ST",
                            "sale_price": 699000.0,
                            "sale_date": "2026-04-21",
                            "lot_size_sqft": 7500.0,
                            "zoning_code": "",
                            "distance_miles": 0.34,
                            "price_per_acre": 0.0,
                            "price_per_unit": 699000.0,
                            "adjustments": {"qualification_score": 0.92},
                        },
                        {
                            "address": "220 NE 211 ST",
                            "sale_price": 505000.0,
                            "sale_date": "2026-05-05",
                            "lot_size_sqft": 3007.0,
                            "zoning_code": "",
                            "distance_miles": 0.38,
                            "price_per_acre": 0.0,
                            "price_per_unit": 505000.0,
                            "adjustments": {"qualification_score": 0.88},
                        },
                    ],
                    "estimated_land_value": 0.0,
                    "adv_per_unit": 505000.0,
                    "adv_per_unit_low": 505000.0,
                    "adv_per_unit_high": 699000.0,
                    "confidence": 0.55,
                    "notes": ["Fallback improved-sale signal inside 3 miles."],
                }
            }
        elif request.tool_name == "run_noi_valuation":
            observed_noi_args.update(dict(request.args))
            payload = _live_tool_payload(request.tool_name, dict(request.args))
        elif request.tool_name == "run_residual_land_value":
            observed_residual_args.update(dict(request.args))
            payload = _live_tool_payload(request.tool_name, dict(request.args))
        else:
            payload = _live_tool_payload(request.tool_name, dict(request.args))

        return HarnessToolCallResult(
            ok=True,
            tool_call_id=ToolCallId(f"tool_call_{request.tool_name}"),
            tool_name=request.tool_name,
            run_id=RunId(str(request.run_id)),
            args=dict(request.args),
            status=ToolRouteStatus.COMPLETED,
            policy_decision=PolicyDecision(allowed=True, reason="test"),
            payload=payload,
            events=[],
            source_mode=request.source_mode,
        )

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "45 NW 209 ST, Miami Gardens, FL 33169",
            "analysis_type": "acquisition_memo",
            "source_mode": "live",
            "assumptions": {
                "maxUnits": 1,
                "maxLotCoveragePct": 40,
                "lotFrontageFt": 75,
                "frontSetbackFt": 25,
                "sideSetbackFt": 7.5,
                "avgUnitSizeSf": 1700,
                "hardCosts": 265000,
                "softCosts": 53000,
                "contingency": 20000,
                "developerFee": 25000,
                "closingCosts": 12000,
                "financingCosts": 18000,
                "holdingCosts": 12000,
                "sellingCosts": 35000,
                "targetProfitPct": 0.18,
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["artifacts"]["underwriting_mode"]["mode"] == "blocked_by_comping_gate"
    assert data["artifacts"]["underwriting_mode"]["status"] == "blocked"
    assert observed_noi_args == {}
    assert observed_residual_args == {}
    assert not any(call["tool_name"] == "run_noi_valuation" for call in data["tool_calls"])
    assert not any(call["tool_name"] == "run_residual_land_value" for call in data["tool_calls"])
    assert (
        data["artifacts"]["acquisition_guidance"]["underwriting_mode"] == "blocked_by_comping_gate"
    )
    assert data["artifacts"]["acquisition_guidance"]["exit_comp_signal_available"] is True


@pytest.mark.asyncio
async def test_deal_analysis_live_run_persists_web_listing_candidates_when_land_signal_is_thin(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    async def _fake_tool_result(request) -> HarnessToolCallResult:
        if request.tool_name == "geocode_address":
            requested_address = str(request.args["address"])
            payload = {
                "status": "success",
                "result": {
                    "address": requested_address,
                    "municipality": "Miami Gardens",
                    "county": "Miami-Dade",
                    "state": "FL",
                    "lat": 25.936991 if "17605 NW 19th" in requested_address else 25.967404,
                    "lng": -80.235842 if "17605 NW 19th" in requested_address else -80.202576,
                },
            }
        elif request.tool_name == "lookup_property_info":
            requested_address = str(request.args["address"])
            if "17605 NW 19th" in requested_address:
                payload = {
                    "status": "success",
                    "result": {
                        "folio": "3412110001000",
                        "address": "17605 NW 19th Avenue",
                        "municipality": "Miami Gardens",
                        "county": "Miami-Dade",
                        "zoning_code": "R-1",
                        "ordinance_district_code": "R-1",
                        "zoning_description": "Single-family dwelling residential district",
                        "land_use_code": "0066",
                        "land_use_description": "VACANT RESIDENTIAL",
                        "lot_size_sqft": 9000.0,
                        "living_units": 0,
                        "last_sale_price": 135000.0,
                        "lat": 25.936991,
                        "lng": -80.235842,
                        "zoning_layer_url": "https://example.test/miami-gardens-zoning",
                    },
                }
            else:
                payload = {
                    "status": "success",
                    "result": {
                        "folio": "3411360031910",
                        "address": "45 NW 209 ST",
                        "municipality": "Miami Gardens",
                        "county": "Miami-Dade",
                        "zoning_code": "R-1",
                        "ordinance_district_code": "R-1",
                        "zoning_description": "Single-family dwelling residential district",
                        "land_use_code": "0066",
                        "land_use_description": "VACANT RESIDENTIAL",
                        "lot_size_sqft": 10105.0,
                        "living_units": 0,
                        "lat": 25.967404,
                        "lng": -80.202576,
                        "zoning_layer_url": "https://example.test/miami-gardens-zoning",
                    },
                }
        elif request.tool_name == "find_comparables":
            payload = {
                "analysis": {
                    "comparables": [],
                    "unit_comparables": [
                        {
                            "address": "105 NE 213 ST",
                            "sale_price": 699000.0,
                            "sale_date": "2026-04-21",
                            "lot_size_sqft": 7500.0,
                            "zoning_code": "",
                            "distance_miles": 0.34,
                            "price_per_acre": 0.0,
                            "price_per_unit": 699000.0,
                            "adjustments": {"qualification_score": 0.92},
                        }
                    ],
                    "estimated_land_value": 0.0,
                    "adv_per_unit": 699000.0,
                    "confidence": 0.55,
                    "web_listing_search": {
                        "query": "miami gardens sold vacant land comps",
                        "provider": "exa",
                        "status": "success",
                        "result_count": 1,
                        "selected_search_window_months": 12,
                    },
                    "web_listing_candidates": [
                        {
                            "title": "17605 NW 19th Avenue, Miami Gardens, FL 33056 | Zillow",
                            "url": "https://www.zillow.com/homedetails/example",
                            "address_hint": "17605 NW 19th Avenue, Miami Gardens, FL 33056",
                            "source_domain": "www.zillow.com",
                            "query": "miami gardens sold vacant land comps",
                            "description": "Public sold listing candidate.",
                            "candidate_kind": "listing_candidate",
                            "classification": "likely_vacant_land",
                            "confidence": 0.85,
                            "search_window_months": 12,
                            "fit_score": 0.92,
                            "lot_size_variance_ratio": 0.08,
                        }
                    ],
                }
            }
        elif request.tool_name == "fetch_web_contents":
            payload = {
                "status": "success",
                "provider": "exa",
                "results": [
                    {
                        "title": "17605 NW 19th Avenue, Miami Gardens, FL 33056 | Zillow",
                        "url": "https://www.zillow.com/homedetails/example",
                        "description": "Sold for $135,000 on 2026-04-21. Lot size: 9,000 sqft.",
                        "content": "Public sold listing. Sold for $135,000 on 2026-04-21. Lot size 9,000 sqft.",
                    }
                ],
            }
        elif request.tool_name == "capture_public_listing_comps":
            payload = {
                "status": "success",
                "provider": "browser_use",
                "strategy": "public_sold_listing_capture",
                "candidates": [
                    {
                        "title": "2940 NW 169th Ter, Miami Gardens, FL 33056 | Zillow",
                        "url": "https://www.zillow.com/homedetails/browser-example",
                        "address_hint": "2940 NW 169th Ter, Miami Gardens, FL 33056",
                        "source_domain": "www.zillow.com",
                        "description": "Browser-captured public sold listing candidate.",
                        "candidate_kind": "browser_listing_candidate",
                        "classification": "likely_vacant_land",
                        "confidence": 0.94,
                        "parsing_confidence": 0.98,
                        "search_category": "sold_land",
                        "search_window_months": 12,
                        "fit_score": 0.86,
                        "lot_size_variance_ratio": 0.14,
                        "municipality": "Miami Gardens",
                        "municipality_match": True,
                        "zip_code": "33056",
                        "zip_match": False,
                        "captured_by": "browser_use",
                    }
                ],
                "warnings": [],
            }
        else:
            payload = _live_tool_payload(request.tool_name, dict(request.args))

        return HarnessToolCallResult(
            ok=True,
            tool_call_id=ToolCallId(f"tool_call_{request.tool_name}"),
            tool_name=request.tool_name,
            run_id=RunId(str(request.run_id)),
            args=dict(request.args),
            status=ToolRouteStatus.COMPLETED,
            policy_decision=PolicyDecision(allowed=True, reason="test"),
            payload=payload,
            events=[],
            source_mode=request.source_mode,
        )

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "45 NW 209 ST, Miami Gardens, FL 33169",
            "analysis_type": "acquisition_memo",
            "source_mode": "live",
            "assumptions": {
                "maxUnits": 1,
                "avgUnitSizeSf": 1700,
                "hardCosts": 265000,
                "softCosts": 53000,
                "contingency": 20000,
                "developerFee": 25000,
                "closingCosts": 12000,
                "financingCosts": 18000,
                "holdingCosts": 12000,
                "sellingCosts": 35000,
                "targetProfitPct": 0.18,
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["artifacts"]["comps"]["web_listing_search"]["provider"] == "exa"
    assert data["artifacts"]["comps"]["web_listing_search"]["result_count"] == 1
    assert data["artifacts"]["comps"]["web_listing_search"]["browser_candidate_count"] == 1
    assert (
        data["artifacts"]["comps"]["web_listing_search"]["browser_capture_provider"]
        == "browser_use"
    )
    assert data["artifacts"]["comps"]["web_listing_search"]["land_candidate_count"] == 1
    assert data["artifacts"]["comps"]["web_listing_search"]["improved_candidate_count"] == 0
    assert data["artifacts"]["comps"]["browser_listing_capture"]["status"] == "success"
    assert (
        data["artifacts"]["comps"]["browser_listing_candidates"][0]["captured_by"] == "browser_use"
    )
    assert (
        data["artifacts"]["comps"]["web_listing_candidates"][0]["source_domain"] == "www.zillow.com"
    )
    assert (
        data["artifacts"]["comps"]["web_listing_candidates"][0]["classification"]
        == "likely_vacant_land"
    )
    assert data["artifacts"]["acquisition_guidance"]["recommended_action"] == "insufficient_support"
    assert data["artifacts"]["acquisition_guidance"]["basis"] == "comping_underwriting_not_ready"
    assert (
        data["artifacts"]["acquisition_guidance"]["underwriting_mode"] == "blocked_by_comping_gate"
    )
    assert data["artifacts"]["underwriting_mode"]["mode"] == "blocked_by_comping_gate"
    assert data["artifacts"]["underwriting_mode"]["status"] == "blocked"
    assert data["artifacts"]["underwriting_calculation_gate"]["status"] == "blocked"
    assert not any(
        call["tool_name"] in {"run_pro_forma", "run_noi_valuation", "run_residual_land_value"}
        for call in data["tool_calls"]
    )
    assert data["artifacts"]["acquisition_guidance"]["recommended_offer"] == pytest.approx(0.0)
    assert "recommended_offer_low" not in data["artifacts"]["acquisition_guidance"]
    assert "recommended_offer_high" not in data["artifacts"]["acquisition_guidance"]
    assert data["artifacts"]["acquisition_guidance"]["contextual_web_land_candidate_count"] == 2
    assert data["artifacts"]["acquisition_guidance"]["contextual_web_improved_candidate_count"] == 0
    assert (
        data["artifacts"]["acquisition_guidance"]["contextual_verified_land_candidate_count"] == 1
    )
    assert data["artifacts"]["acquisition_guidance"][
        "contextual_land_value_signal"
    ] == pytest.approx(151575.0)
    assert data["artifacts"]["acquisition_guidance"][
        "contextual_market_land_value_low"
    ] == pytest.approx(151575.0)
    assert data["artifacts"]["acquisition_guidance"][
        "contextual_market_land_value_high"
    ] == pytest.approx(151575.0)
    assert data["artifacts"]["acquisition_guidance"]["county_reconciled_land_candidate_count"] == 0
    assert data["artifacts"]["acquisition_guidance"][
        "county_reconciled_land_value_signal"
    ] == pytest.approx(0.0)
    assert data["artifacts"]["acquisition_guidance"][
        "county_reconciled_market_land_value_low"
    ] == pytest.approx(0.0)
    assert data["artifacts"]["acquisition_guidance"][
        "county_reconciled_market_land_value_high"
    ] == pytest.approx(0.0)
    assert (
        data["artifacts"]["acquisition_guidance"]["land_signal_source"]
        == "contextual_public_listing"
    )
    assert data["artifacts"]["acquisition_guidance"]["land_signal_strength"] == "contextual"
    assert (
        data["artifacts"]["acquisition_guidance"]["market_signal_verification_status"]
        == "contextual_verified"
    )
    assert data["artifacts"]["acquisition_guidance"]["requires_market_signal_validation"] is True
    assert data["artifacts"]["acquisition_guidance"]["recommendation_confidence"] == "low"
    assert (
        data["artifacts"]["comp_search_strategy"]["land_signal_tier"] == "contextual_public_listing"
    )
    assert data["artifacts"]["comp_search_strategy"]["county_reconciled_candidate_count"] == 0
    assert (
        data["artifacts"]["comp_search_strategy"]["public_listing_signal_tier"]
        == "contextual_verified"
    )
    assert data["artifacts"]["comp_search_strategy"]["public_listing_land_comp_count"] == 1
    assert data["artifacts"]["comp_search_strategy"][
        "best_public_listing_fit_score"
    ] == pytest.approx(0.891)
    assert data["artifacts"]["comp_search_strategy"][
        "best_public_listing_lot_size_variance_ratio"
    ] == pytest.approx(0.109)
    assert (
        data["artifacts"]["comp_search_strategy"]["best_public_listing_sale_date"] == "2026-04-21"
    )
    assert (
        data["artifacts"]["comp_search_strategy"]["public_listing_market_scope"]
        == "cross_zip_same_municipality"
    )
    assert data["artifacts"]["comp_search_strategy"]["public_listing_recency_tier"] == "recent_6m"
    assert data["artifacts"]["comp_search_strategy"][
        "best_public_listing_parse_confidence"
    ] == pytest.approx(1.0)
    assert data["artifacts"]["comp_search_strategy"]["public_listing_domains"] == ["www.zillow.com"]
    assert (
        data["artifacts"]["comps"]["public_listing_land_comparables"][0]["verification_status"]
        == "contextual_verified"
    )
    assert (
        data["artifacts"]["comps"]["public_listing_land_comparables"][0]["source_domain"]
        == "www.zillow.com"
    )
    public_listing_section = next(
        section
        for section in data["report"]["sections"]
        if section["section_id"] == "public_listing_comps"
    )
    assert public_listing_section["public_listing_signal_tier"] == "contextual_verified"
    assert public_listing_section["count"] == 1
    assert public_listing_section["preliminary"] is True
    assert (
        data["artifacts"]["contextual_land_listing_verification"]["verified_candidate_count"] == 1
    )
    workflow = data["artifacts"]["comping_workflow"]
    assert workflow["agent_role"] == "comping_analyst"
    assert workflow["subject_context"]["source_tool"] == "lookup_property_info"
    assert workflow["subject_context"]["municipality"] == "Miami Gardens"
    assert workflow["subject_context"]["zoning_code"] == "R-1"
    assert workflow["programmatic_reasoning"]["zoning_context_source"] == "lookup_property_info"
    assert workflow["programmatic_reasoning"]["official_zoning_verification_required"] is True
    assert workflow["programmatic_reasoning"]["no_cached_zoning_claim"] is True
    assert [entry["purpose"] for entry in workflow["search_plan"]] == [
        "primary_recent_land_comp_search",
        "expanded_recent_land_comp_search",
        "maximum_land_comp_lookback_search",
        "exit_value_new_build_fallback_search",
        "exit_value_renovated_sale_fallback_search",
    ]
    assert workflow["search_plan"][0]["search_window_months"] == 6
    assert workflow["search_plan"][1]["search_window_months"] == 12
    assert workflow["search_plan"][2]["search_window_months"] == 24
    assert workflow["contextual_public_listing_comps"][0]["address"] == (
        "17605 NW 19th Avenue, Miami Gardens, FL 33056"
    )
    assert workflow["trust_gates"]["underwriting_status"] == "blocked_pending_county_reconciliation"
    assert workflow["trust_gates"]["contextual_public_listing_count"] == 1
    assert workflow["trust_gates"]["county_reconciled_public_listing_count"] == 0
    underwriting_section = next(
        section
        for section in data["report"]["sections"]
        if section["section_id"] == "underwriting_summary"
    )
    comp_support_summary = underwriting_section["comp_support_summary"]
    assert (
        comp_support_summary["comping_underwriting_status"]
        == "blocked_pending_county_reconciliation"
    )
    assert comp_support_summary["comping_underwriting_blocker"] == (
        "public listing comps require county-record reconciliation before confident underwriting"
    )
    verification_event = next(
        event for event in data["events"] if event["type"] == "verification.completed"
    )
    assert verification_event["payload"]["checks"]["comping_underwriting_gate"] == "warning"
    assert any(call["tool_name"] == "capture_public_listing_comps" for call in data["tool_calls"])
    reconciliation = data["artifacts"]["contextual_land_listing_reconciliation"]
    assert reconciliation["status"] == "no_county_record_match"
    assert reconciliation["attempted_candidate_count"] == 1
    assert reconciliation["reconciled_candidate_count"] == 0
    assert reconciliation["rejected_candidate_count"] == 1
    assert reconciliation["rejected_candidates"][0]["reason"] == (
        "candidate_listing_facts_do_not_match_county_record"
    )
    web_evidence = [item for item in data["evidence_items"] if item["provider"] == "exa_web_search"]
    assert len(web_evidence) == 2
    assert web_evidence[0]["metadata"]["listing_candidate"] is True
    assert web_evidence[0]["metadata"]["classification"] == "likely_vacant_land"
    assert {item["structured_payload"]["address_hint"] for item in web_evidence} == {
        "17605 NW 19th Avenue, Miami Gardens, FL 33056",
        "2940 NW 169th Ter, Miami Gardens, FL 33056",
    }
    assert web_evidence[0]["structured_payload"]["query"] == "miami gardens sold vacant land comps"
    verified_listing_evidence = [
        item for item in data["evidence_items"] if item["provider"] == "exa_web_contents"
    ]
    assert len(verified_listing_evidence) == 1
    assert verified_listing_evidence[0]["metadata"]["listing_verified"] is True
    county_reconciled_evidence = [
        item
        for item in data["evidence_items"]
        if item["provider"] == "county_reconciled_public_listing"
    ]
    assert len(county_reconciled_evidence) == 0

    comp_only_response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "45 NW 209 ST, Miami Gardens, FL 33169",
            "analysis_type": "comparable_comping",
            "source_mode": "live",
        },
    )
    assert comp_only_response.status_code == 200
    comp_only_data = comp_only_response.json()
    assert comp_only_data["analysis_type"] == "comparable_comping"
    assert comp_only_data["artifacts"]["underwriting_mode"]["mode"] == "comping_only"
    assert "feasibility" not in comp_only_data["artifacts"]
    assert "pro_forma" not in comp_only_data["artifacts"]
    assert "residual_land_value" not in comp_only_data["artifacts"]
    assert not any(
        call["tool_name"] in {"compute_feasibility", "run_pro_forma", "run_residual_land_value"}
        for call in comp_only_data["tool_calls"]
    )
    comp_only_workflow = comp_only_data["artifacts"]["comping_workflow"]
    assert comp_only_workflow["subject_context"]["source_tool"] == "lookup_property_info"
    assert comp_only_workflow["programmatic_reasoning"]["no_cached_zoning_claim"] is True
    assert comp_only_workflow["search_plan"][0]["purpose"] == "primary_recent_land_comp_search"
    assert (
        comp_only_workflow["trust_gates"]["underwriting_status"]
        == "blocked_pending_county_reconciliation"
    )


@pytest.mark.asyncio
async def test_deal_analysis_live_run_prefers_direct_land_comps_without_contextual_listing_fetch(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    observed_tool_names: list[str] = []

    async def _fake_tool_result(request) -> HarnessToolCallResult:
        observed_tool_names.append(request.tool_name)
        if request.tool_name == "geocode_address":
            payload = {
                "status": "success",
                "result": {
                    "address": str(request.args["address"]),
                    "municipality": "Miami Gardens",
                    "county": "Miami-Dade",
                    "state": "FL",
                    "lat": 25.967404,
                    "lng": -80.202576,
                },
            }
        elif request.tool_name == "lookup_property_info":
            payload = {
                "status": "success",
                "result": {
                    "folio": "3411360031910",
                    "address": "45 NW 209 ST",
                    "municipality": "Miami Gardens",
                    "county": "Miami-Dade",
                    "zoning_code": "R-1",
                    "ordinance_district_code": "R-1",
                    "zoning_description": "Single-family dwelling residential district",
                    "land_use_code": "0066",
                    "land_use_description": "VACANT RESIDENTIAL",
                    "lot_size_sqft": 10105.0,
                    "living_units": 0,
                    "lat": 25.967404,
                    "lng": -80.202576,
                    "zoning_layer_url": "https://example.test/miami-gardens-zoning",
                },
            }
        elif request.tool_name == "find_comparables":
            payload = {
                "analysis": {
                    "comparables": [
                        {
                            "address": "17605 NW 19th Avenue",
                            "sale_price": 135000.0,
                            "sale_date": "2025-12-01",
                            "lot_size_sqft": 9000.0,
                            "distance_miles": 1.2,
                            "price_per_acre": 653400.0,
                            "adjustments": {"qualification_score": 0.89},
                        },
                        {
                            "address": "2940 NW 169th Ter",
                            "sale_price": 145000.0,
                            "sale_date": "2025-10-10",
                            "lot_size_sqft": 10000.0,
                            "distance_miles": 1.5,
                            "price_per_acre": 631620.0,
                            "adjustments": {"qualification_score": 0.9},
                        },
                    ],
                    "unit_comparables": [
                        {
                            "address": "105 NE 213 ST",
                            "sale_price": 699000.0,
                            "sale_date": "2026-04-21",
                            "lot_size_sqft": 7500.0,
                            "zoning_code": "",
                            "distance_miles": 0.34,
                            "price_per_acre": 0.0,
                            "price_per_unit": 699000.0,
                            "adjustments": {"qualification_score": 0.92},
                        }
                    ],
                    "estimated_land_value": 149048.75,
                    "estimated_land_value_low": 146524.85,
                    "estimated_land_value_high": 151572.65,
                    "adv_per_unit": 699000.0,
                    "sales_source_type": "curated_arcgis",
                    "exit_comp_source_type": "curated_arcgis",
                    "confidence": 0.78,
                    "web_listing_search": {
                        "query": "miami gardens sold vacant land comps",
                        "provider": "exa",
                        "status": "success",
                        "result_count": 0,
                    },
                }
            }
        elif request.tool_name == "compute_feasibility":
            payload = {
                "result": {
                    "calculation_type": "feasibility",
                    "formula_version": "feasibility.v2",
                    "max_gross_buildable_sf": 4042.0,
                    "net_rentable_sf": 3435.7,
                    "estimated_units": 1,
                    "parking_required": 2,
                    "major_constraints": ["max_units"],
                    "area_limiters": ["lot_coverage"],
                    "lot_depth_ft": 134.73,
                    "buildable_envelope_sf": 4468.2,
                    "lot_coverage_limited_sf": 4042.0,
                    "feasibility_warnings": [],
                }
            }
        elif request.tool_name == "run_pro_forma":
            payload = {
                "result": {
                    "calculation_type": "pro_forma",
                    "formula_version": "pro_forma.v1",
                    "gross_development_value": 699000.0,
                    "hard_costs": 265000.0,
                    "soft_costs": 53000.0,
                    "builder_margin": 25000.0,
                    "impact_fees": 0.0,
                    "impact_fees_per_unit": 0.0,
                    "max_supportable_land_price": 120000.0,
                    "cost_per_door": 343000.0,
                    "construction_cost_psf": 155.88,
                    "avg_unit_size_sqft": 1700.0,
                    "adv_per_unit": 699000.0,
                    "max_units": 1,
                    "soft_cost_pct": 0.2,
                    "builder_margin_pct": 0.05,
                    "adv_source": "auto_comps",
                    "market": "Miami-Dade",
                    "notes": [],
                }
            }
        else:
            payload = _live_tool_payload(request.tool_name, dict(request.args))

        return HarnessToolCallResult(
            ok=True,
            tool_call_id=ToolCallId(f"tool_call_{request.tool_name}"),
            tool_name=request.tool_name,
            run_id=RunId(str(request.run_id)),
            args=dict(request.args),
            status=ToolRouteStatus.COMPLETED,
            policy_decision=PolicyDecision(allowed=True, reason="test"),
            payload=payload,
            events=[],
            source_mode=request.source_mode,
        )

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "45 NW 209 ST, Miami Gardens, FL 33169",
            "analysis_type": "acquisition_memo",
            "source_mode": "live",
            "assumptions": {
                "maxUnits": 1,
                "maxLotCoveragePct": 40,
                "lotFrontageFt": 75,
                "frontSetbackFt": 25,
                "sideSetbackFt": 7.5,
                "avgUnitSizeSf": 1700,
                "hardCosts": 265000,
                "softCosts": 53000,
                "contingency": 20000,
                "developerFee": 25000,
                "closingCosts": 12000,
                "financingCosts": 18000,
                "holdingCosts": 12000,
                "sellingCosts": 35000,
                "targetProfitPct": 0.18,
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["artifacts"]["acquisition_guidance"]["recommended_action"] == "offer_range"
    assert data["artifacts"]["acquisition_guidance"]["basis"] == "residual_and_market_signal"
    assert data["artifacts"]["acquisition_guidance"]["land_signal_source"] == "direct_land_comps"
    assert data["artifacts"]["acquisition_guidance"]["land_signal_strength"] == "direct"
    assert (
        data["artifacts"]["acquisition_guidance"]["market_signal_verification_status"]
        == "direct_verified"
    )
    assert data["artifacts"]["acquisition_guidance"]["requires_market_signal_validation"] is False
    assert data["artifacts"]["acquisition_guidance"]["recommendation_confidence"] == "high"
    assert data["artifacts"]["comp_search_strategy"]["selected_reason"] == "direct_land_comp_signal"
    assert data["artifacts"]["comp_search_strategy"]["land_signal_tier"] == "direct_land_comps"
    assert data["artifacts"]["comp_search_strategy"]["sales_source_type"] == "curated_arcgis"
    assert data["artifacts"]["comp_search_strategy"]["exit_comp_source_type"] == "curated_arcgis"
    assert data["artifacts"]["comp_search_strategy"][
        "best_direct_land_comp_fit_score"
    ] == pytest.approx(0.99)
    assert data["artifacts"]["comp_search_strategy"][
        "best_direct_land_comp_lot_size_variance_ratio"
    ] == pytest.approx(0.01)
    assert data["artifacts"]["comp_search_strategy"][
        "best_direct_land_comp_qualification_score"
    ] == pytest.approx(0.9)
    underwriting_section = next(
        section
        for section in data["report"]["sections"]
        if section["section_id"] == "underwriting_summary"
    )
    assert underwriting_section["comp_support_summary"]["status"] == "passed"
    assert (
        underwriting_section["comp_support_summary"]["land_support_source"] == "direct_land_comps"
    )
    assert underwriting_section["comp_support_summary"]["land_support_fit_score"] == pytest.approx(
        0.99
    )
    assert underwriting_section["comp_support_summary"]["exit_support_fit_score"] == pytest.approx(
        1.0
    )
    assert (
        underwriting_section["comp_support_summary"]["exit_support_market_scope"]
        == "subject_municipality"
    )
    assert underwriting_section["comp_support_summary"]["exit_support_sale_date"] == "2026-04-21"
    assert underwriting_section["comp_support_summary"]["exit_support_recency_tier"] == "recent_6m"
    assert underwriting_section["comp_support_summary"]["combined_support_tier"] == "balanced"
    assert "fetch_web_contents" not in observed_tool_names
    assert "contextual_land_listing_verification" not in data["artifacts"]
    assert "contextual_land_listing_reconciliation" not in data["artifacts"]


@pytest.mark.asyncio
async def test_deal_analysis_live_run_keeps_contextual_land_signal_preliminary_when_county_reconciliation_fails(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    async def _fake_tool_result(request) -> HarnessToolCallResult:
        if request.tool_name == "geocode_address":
            requested_address = str(request.args["address"])
            payload = {
                "status": "success",
                "result": {
                    "address": requested_address,
                    "municipality": "Miami Gardens",
                    "county": "Miami-Dade",
                    "state": "FL",
                    "lat": 25.936991 if "17605 NW 19th" in requested_address else 25.967404,
                    "lng": -80.235842 if "17605 NW 19th" in requested_address else -80.202576,
                },
            }
        elif request.tool_name == "lookup_property_info":
            requested_address = str(request.args["address"])
            if "17605 NW 19th" in requested_address:
                payload = {
                    "status": "success",
                    "result": {
                        "folio": "3412110001000",
                        "address": "17605 NW 19th Avenue",
                        "municipality": "Miami Gardens",
                        "county": "Miami-Dade",
                        "zoning_code": "R-1",
                        "ordinance_district_code": "R-1",
                        "zoning_description": "Single-family dwelling residential district",
                        "land_use_code": "0066",
                        "land_use_description": "VACANT RESIDENTIAL",
                        "lot_size_sqft": 12_500.0,
                        "living_units": 0,
                        "last_sale_price": 190000.0,
                        "lat": 25.936991,
                        "lng": -80.235842,
                        "zoning_layer_url": "https://example.test/miami-gardens-zoning",
                    },
                }
            else:
                payload = {
                    "status": "success",
                    "result": {
                        "folio": "3411360031910",
                        "address": "45 NW 209 ST",
                        "municipality": "Miami Gardens",
                        "county": "Miami-Dade",
                        "zoning_code": "R-1",
                        "ordinance_district_code": "R-1",
                        "zoning_description": "Single-family dwelling residential district",
                        "land_use_code": "0066",
                        "land_use_description": "VACANT RESIDENTIAL",
                        "lot_size_sqft": 10105.0,
                        "living_units": 0,
                        "lat": 25.967404,
                        "lng": -80.202576,
                        "zoning_layer_url": "https://example.test/miami-gardens-zoning",
                    },
                }
        elif request.tool_name == "find_comparables":
            payload = {
                "analysis": {
                    "comparables": [],
                    "unit_comparables": [
                        {
                            "address": "105 NE 213 ST",
                            "sale_price": 699000.0,
                            "sale_date": "2026-04-21",
                            "lot_size_sqft": 7500.0,
                            "zoning_code": "",
                            "distance_miles": 0.34,
                            "price_per_acre": 0.0,
                            "price_per_unit": 699000.0,
                            "adjustments": {"qualification_score": 0.92},
                        }
                    ],
                    "estimated_land_value": 0.0,
                    "adv_per_unit": 699000.0,
                    "confidence": 0.55,
                    "web_listing_search": {
                        "query": "miami gardens sold vacant land comps",
                        "provider": "exa",
                        "status": "success",
                        "result_count": 1,
                        "selected_search_window_months": 12,
                    },
                    "web_listing_candidates": [
                        {
                            "title": "17605 NW 19th Avenue, Miami Gardens, FL 33056 | Zillow",
                            "url": "https://www.zillow.com/homedetails/example",
                            "address_hint": "17605 NW 19th Avenue, Miami Gardens, FL 33056",
                            "source_domain": "www.zillow.com",
                            "query": "miami gardens sold vacant land comps",
                            "description": "Public sold listing candidate.",
                            "candidate_kind": "listing_candidate",
                            "classification": "likely_vacant_land",
                            "confidence": 0.85,
                            "search_window_months": 12,
                            "fit_score": 0.89,
                            "lot_size_variance_ratio": 0.11,
                        }
                    ],
                }
            }
        elif request.tool_name == "fetch_web_contents":
            payload = {
                "status": "success",
                "provider": "exa",
                "results": [
                    {
                        "title": "17605 NW 19th Avenue, Miami Gardens, FL 33056 | Zillow",
                        "url": "https://www.zillow.com/homedetails/example",
                        "description": "Sold for $135,000 on 2026-04-21. Lot size: 9,000 sqft.",
                        "content": "Public sold listing. Sold for $135,000 on 2026-04-21. Lot size 9,000 sqft.",
                    }
                ],
            }
        elif request.tool_name == "capture_public_listing_comps":
            payload = {
                "status": "success",
                "provider": "browser_use",
                "strategy": "public_sold_listing_capture",
                "candidates": [],
                "warnings": [],
            }
        else:
            payload = _live_tool_payload(request.tool_name, dict(request.args))

        return HarnessToolCallResult(
            ok=True,
            tool_call_id=ToolCallId(f"tool_call_{request.tool_name}"),
            tool_name=request.tool_name,
            run_id=RunId(str(request.run_id)),
            args=dict(request.args),
            status=ToolRouteStatus.COMPLETED,
            policy_decision=PolicyDecision(allowed=True, reason="test"),
            payload=payload,
            events=[],
            source_mode=request.source_mode,
        )

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "45 NW 209 ST, Miami Gardens, FL 33169",
            "analysis_type": "acquisition_memo",
            "source_mode": "live",
            "assumptions": {
                "maxUnits": 1,
                "avgUnitSizeSf": 1700,
                "hardCosts": 265000,
                "softCosts": 53000,
                "contingency": 20000,
                "developerFee": 25000,
                "closingCosts": 12000,
                "financingCosts": 18000,
                "holdingCosts": 12000,
                "sellingCosts": 35000,
                "targetProfitPct": 0.18,
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["artifacts"]["acquisition_guidance"]["recommended_action"] == "insufficient_support"
    assert data["artifacts"]["acquisition_guidance"]["basis"] == "comping_underwriting_not_ready"
    assert data["artifacts"]["underwriting_mode"]["mode"] == "blocked_by_comping_gate"
    assert data["artifacts"]["underwriting_calculation_gate"]["status"] == "blocked"
    assert (
        data["artifacts"]["acquisition_guidance"]["land_signal_source"]
        == "contextual_public_listing"
    )
    assert data["artifacts"]["acquisition_guidance"]["land_signal_strength"] == "contextual"
    assert (
        data["artifacts"]["acquisition_guidance"]["market_signal_verification_status"]
        == "contextual_verified"
    )
    assert data["artifacts"]["acquisition_guidance"]["requires_market_signal_validation"] is True
    assert data["artifacts"]["acquisition_guidance"]["recommendation_confidence"] == "low"
    assert (
        data["artifacts"]["acquisition_guidance"]["contextual_verified_land_candidate_count"] == 1
    )
    assert data["artifacts"]["acquisition_guidance"]["county_reconciled_land_candidate_count"] == 0
    assert (
        data["artifacts"]["comp_search_strategy"]["land_signal_tier"] == "contextual_public_listing"
    )
    assert (
        data["artifacts"]["comp_search_strategy"]["public_listing_signal_tier"]
        == "contextual_verified"
    )
    assert data["artifacts"]["comp_search_strategy"]["public_listing_land_comp_count"] == 1
    assert data["artifacts"]["comp_search_strategy"][
        "best_public_listing_fit_score"
    ] == pytest.approx(0.891)
    assert data["artifacts"]["comp_search_strategy"][
        "best_public_listing_lot_size_variance_ratio"
    ] == pytest.approx(0.109)
    assert (
        data["artifacts"]["comps"]["public_listing_land_comparables"][0]["verification_status"]
        == "contextual_verified"
    )
    public_listing_section = next(
        section
        for section in data["report"]["sections"]
        if section["section_id"] == "public_listing_comps"
    )
    underwriting_section = next(
        section
        for section in data["report"]["sections"]
        if section["section_id"] == "underwriting_summary"
    )
    assert public_listing_section["public_listing_signal_tier"] == "contextual_verified"
    assert public_listing_section["count"] == 1
    assert public_listing_section["preliminary"] is True
    assert underwriting_section["comp_support_summary"]["status"] == "warning"
    assert (
        underwriting_section["comp_support_summary"]["land_support_source"]
        == "contextual_public_listing"
    )
    assert underwriting_section["comp_support_summary"]["land_support_fit_score"] == pytest.approx(
        0.891
    )
    assert (
        underwriting_section["comp_support_summary"]["land_support_market_scope"]
        == "cross_zip_same_municipality"
    )
    assert underwriting_section["comp_support_summary"]["land_support_sale_date"] == "2026-04-21"
    assert underwriting_section["comp_support_summary"]["land_support_recency_tier"] == "recent_6m"
    assert underwriting_section["comp_support_summary"][
        "land_support_parse_confidence"
    ] == pytest.approx(1.0)
    assert underwriting_section["comp_support_summary"]["land_micro_market_confidence"] == "medium"
    assert underwriting_section["comp_support_summary"]["exit_support_fit_score"] == pytest.approx(
        1.0
    )
    assert (
        underwriting_section["comp_support_summary"]["exit_support_market_scope"]
        == "subject_municipality"
    )
    assert underwriting_section["comp_support_summary"]["exit_support_sale_date"] == "2026-04-21"
    assert underwriting_section["comp_support_summary"]["exit_support_recency_tier"] == "recent_6m"
    assert underwriting_section["comp_support_summary"]["exit_micro_market_confidence"] == "medium"
    assert underwriting_section["comp_support_summary"]["combined_support_tier"] == "exit_only"
    assert underwriting_section["comp_support_summary"]["reason"] == (
        "live market support is too weak for a confident offer recommendation"
    )
    reconciliation = data["artifacts"]["contextual_land_listing_reconciliation"]
    assert reconciliation["status"] == "no_county_record_match"
    assert reconciliation["attempted_candidate_count"] == 1
    assert reconciliation["reconciled_candidate_count"] == 0
    assert reconciliation["rejected_candidate_count"] == 1


@pytest.mark.asyncio
async def test_deal_analysis_live_run_uses_browser_captured_county_reconciled_land_signal_for_underwriting(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    observed_pro_forma_args: dict[str, object] = {}

    async def _fake_tool_result(request) -> HarnessToolCallResult:
        if request.tool_name == "geocode_address":
            requested_address = str(request.args["address"])
            payload = {
                "status": "success",
                "result": {
                    "address": requested_address,
                    "municipality": "Miami Gardens",
                    "county": "Miami-Dade",
                    "state": "FL",
                    "lat": 25.936991 if "17605 NW 19th" in requested_address else 25.967404,
                    "lng": -80.235842 if "17605 NW 19th" in requested_address else -80.202576,
                },
            }
        elif request.tool_name == "lookup_property_info":
            requested_address = str(request.args["address"])
            if "17605 NW 19th" in requested_address:
                payload = {
                    "status": "success",
                    "result": {
                        "folio": "3412110001000",
                        "address": "17605 NW 19th Avenue",
                        "municipality": "Miami Gardens",
                        "county": "Miami-Dade",
                        "zoning_code": "R-1",
                        "ordinance_district_code": "R-1",
                        "zoning_description": "Single-family detached residential",
                        "land_use_description": "VACANT RESIDENTIAL",
                        "lot_size_sqft": 9000.0,
                        "living_units": 0,
                        "last_sale_price": 135000.0,
                        "last_sale_date": "2026-04-30",
                        "lat": 25.936991,
                        "lng": -80.235842,
                        "zoning_layer_url": "https://example.test/miami-gardens-zoning",
                    },
                }
            else:
                payload = {
                    "status": "success",
                    "result": {
                        "folio": "3411360031910",
                        "address": "45 NW 209 ST",
                        "municipality": "Miami Gardens",
                        "county": "Miami-Dade",
                        "zoning_code": "R-1",
                        "ordinance_district_code": "R-1",
                        "zoning_description": "Single-family detached residential",
                        "land_use_description": "VACANT RESIDENTIAL",
                        "lot_size_sqft": 10105.0,
                        "living_units": 0,
                        "lat": 25.967404,
                        "lng": -80.202576,
                        "zoning_layer_url": "https://example.test/miami-gardens-zoning",
                    },
                }
        elif request.tool_name == "find_comparables":
            payload = {
                "analysis": {
                    "comparables": [],
                    "unit_comparables": [
                        {
                            "address": "105 NE 213 ST",
                            "sale_price": 699000.0,
                            "sale_date": "2026-04-21",
                            "lot_size_sqft": 7500.0,
                            "zoning_code": "R-1",
                            "distance_miles": 0.34,
                            "price_per_acre": 0.0,
                            "price_per_unit": 699000.0,
                            "adjustments": {"qualification_score": 0.92},
                        }
                    ],
                    "estimated_land_value": 0.0,
                    "adv_per_unit": 699000.0,
                    "confidence": 0.55,
                    "web_listing_search": {
                        "query": "miami gardens sold vacant land comps",
                        "provider": "exa",
                        "status": "success",
                        "result_count": 0,
                        "selected_search_window_months": 12,
                    },
                    "web_listing_candidates": [],
                }
            }
        elif request.tool_name == "capture_public_listing_comps":
            payload = {
                "status": "success",
                "provider": "browser_use",
                "strategy": "public_sold_listing_capture",
                "candidates": [
                    {
                        "title": "17605 NW 19th Avenue, Miami Gardens, FL 33056 | Zillow",
                        "url": "https://www.zillow.com/homedetails/17605-NW-19th-Ave-Miami-Gardens-FL-33056/44106704_zpid/",
                        "address_hint": "17605 NW 19th Avenue, Miami Gardens, FL 33056",
                        "source_domain": "www.zillow.com",
                        "description": "Browser-captured public sold listing candidate.",
                        "candidate_kind": "browser_listing_candidate",
                        "classification": "likely_vacant_land",
                        "confidence": 0.94,
                        "search_category": "sold_land",
                        "search_window_months": 12,
                        "fit_score": 0.89,
                        "lot_size_variance_ratio": 0.109,
                        "municipality": "Miami Gardens",
                        "municipality_match": True,
                        "zip_code": "33056",
                        "zip_match": False,
                        "captured_by": "browser_use",
                    }
                ],
                "warnings": [],
            }
        elif request.tool_name == "fetch_web_contents":
            payload = {
                "status": "success",
                "provider": "exa",
                "results": [
                    {
                        "title": "17605 NW 19th Avenue, Miami Gardens, FL 33056 | Zillow",
                        "url": "https://www.zillow.com/homedetails/17605-NW-19th-Ave-Miami-Gardens-FL-33056/44106704_zpid/",
                        "description": "Zillow home details for the public property page.",
                        "content": "Public property page with address only.",
                    }
                ],
            }
        elif request.tool_name == "run_pro_forma":
            observed_pro_forma_args.update(dict(request.args))
            payload = {
                "result": {
                    "gross_development_value": 699000.0,
                    "hard_costs": 265000.0,
                    "soft_costs": 53000.0,
                    "builder_margin": 25000.0,
                    "impact_fees": 0.0,
                    "impact_fees_per_unit": 0.0,
                    "max_supportable_land_price": 120000.0,
                    "cost_per_door": 343000.0,
                    "construction_cost_psf": 155.88,
                    "avg_unit_size_sqft": 1700.0,
                    "adv_per_unit": 699000.0,
                    "max_units": 1,
                    "soft_cost_pct": 0.2,
                    "builder_margin_pct": 0.08,
                    "adv_source": "auto_comps",
                    "market": "South Florida",
                    "notes": [],
                }
            }
        else:
            payload = _live_tool_payload(request.tool_name, dict(request.args))

        return HarnessToolCallResult(
            ok=True,
            tool_call_id=ToolCallId(f"tool_call_{request.tool_name}"),
            tool_name=request.tool_name,
            run_id=RunId(str(request.run_id)),
            args=dict(request.args),
            status=ToolRouteStatus.COMPLETED,
            policy_decision=PolicyDecision(allowed=True, reason="test"),
            payload=payload,
            events=[],
            source_mode=request.source_mode,
        )

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "45 NW 209 ST, Miami Gardens, FL 33169",
            "analysis_type": "acquisition_memo",
            "source_mode": "live",
            "assumptions": {
                "maxUnits": 1,
                "avgUnitSizeSf": 1700,
                "hardCosts": 265000,
                "softCosts": 53000,
                "contingency": 20000,
                "developerFee": 25000,
                "closingCosts": 12000,
                "financingCosts": 18000,
                "holdingCosts": 12000,
                "sellingCosts": 35000,
                "targetProfitPct": 0.18,
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert observed_pro_forma_args["estimated_land_value"] == pytest.approx(151575.0, abs=0.01)
    assert any(call["tool_name"] == "run_pro_forma" for call in data["tool_calls"])
    assert data["artifacts"]["underwriting_calculation_gate"]["status"] == "available"
    assert data["artifacts"]["underwriting_mode"]["mode"] == "sold_unit_exit"
    assert data["artifacts"]["underwriting_mode"]["status"] == "completed"
    assert (
        data["artifacts"]["comp_search_strategy"]["land_signal_tier"]
        == "county_reconciled_public_listing"
    )
    assert (
        data["artifacts"]["comp_search_strategy"]["public_listing_signal_tier"]
        == "county_reconciled"
    )
    assert (
        data["artifacts"]["comping_workflow"]["trust_gates"]["underwriting_status"]
        == "available_to_underwriting"
    )
    assert data["artifacts"]["comping_workflow"]["county_reconciled_public_listing_comps"][0][
        "address"
    ] == ("17605 NW 19th Avenue, Miami Gardens, FL 33056")
    reconciliation = data["artifacts"]["contextual_land_listing_reconciliation"]
    assert reconciliation["status"] == "county_reconciled"
    assert reconciliation["reconciled_candidate_count"] == 1
    assert (
        reconciliation["reconciled_candidates"][0]["reconciliation_basis"]
        == "county_record_enriched"
    )
    public_listing_comp = data["artifacts"]["comps"]["public_listing_land_comparables"][0]
    assert public_listing_comp["verification_status"] == "county_reconciled"
    assert public_listing_comp["provider"] == "public_listing_county_reconciled"
    assert public_listing_comp["sale_price"] == pytest.approx(135000.0)
    guidance = data["artifacts"]["acquisition_guidance"]
    assert guidance["recommended_action"] == "offer_range"
    assert guidance["basis"] == "county_reconciled_land_signal"
    assert guidance["land_signal_source"] == "county_reconciled_public_listing"
    assert guidance["recommended_offer"] == pytest.approx(120000.0)
    assert guidance["land_value_signal"] == pytest.approx(151575.0, abs=0.01)
    assert guidance["market_land_value_low"] == pytest.approx(151575.0, abs=0.01)
    assert guidance["market_land_value_high"] == pytest.approx(151575.0, abs=0.01)
    county_evidence = [
        item
        for item in data["evidence_items"]
        if item["provider"] == "county_reconciled_public_listing"
    ]
    assert len(county_evidence) == 1


@pytest.mark.asyncio
async def test_deal_analysis_live_run_keeps_selected_attempt_in_sync_with_saved_comp_payload(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    observed_searches: list[tuple[int, float]] = []

    async def _fake_tool_result(request) -> HarnessToolCallResult:
        if request.tool_name == "geocode_address":
            payload = {
                "status": "success",
                "result": {
                    "address": str(request.args["address"]),
                    "municipality": "Miami Gardens",
                    "county": "Miami-Dade",
                    "state": "FL",
                    "lat": 25.967404,
                    "lng": -80.202576,
                },
            }
        elif request.tool_name == "lookup_property_info":
            payload = {
                "status": "success",
                "result": {
                    "folio": "3411360031910",
                    "address": "45 NW 209 ST",
                    "municipality": "Miami Gardens",
                    "county": "Miami-Dade",
                    "zoning_code": "R-1",
                    "ordinance_district_code": "R-1",
                    "zoning_description": "Single-family dwelling residential district",
                    "land_use_code": "0066",
                    "land_use_description": "VACANT RESIDENTIAL",
                    "lot_size_sqft": 10105.0,
                    "living_units": 0,
                    "lat": 25.967404,
                    "lng": -80.202576,
                    "zoning_layer_url": "https://example.test/miami-gardens-zoning",
                },
            }
        elif request.tool_name == "find_comparables":
            months = int(request.args["months"])
            radius_miles = float(request.args["radius_miles"])
            observed_searches.append((months, radius_miles))
            if months in {6, 12}:
                payload = {"analysis": _empty_live_comps_payload()}
            elif months == 24 and radius_miles == 3.0:
                payload = {
                    "analysis": {
                        "comparables": [],
                        "unit_comparables": [
                            {
                                "address": "105 NE 213 ST",
                                "sale_price": 699000.0,
                                "sale_date": "2026-04-21",
                                "lot_size_sqft": 7500.0,
                                "zoning_code": "",
                                "distance_miles": 0.34,
                                "price_per_acre": 0.0,
                                "price_per_unit": 446250.0,
                                "adjustments": {"qualification_score": 0.9},
                            }
                        ],
                        "estimated_land_value": 0.0,
                        "adv_per_unit": 446250.0,
                        "adv_per_unit_low": 446250.0,
                        "adv_per_unit_high": 446250.0,
                        "confidence": 0.55,
                        "notes": ["Fallback improved-sale signal inside 3 miles."],
                    }
                }
            else:
                payload = {
                    "analysis": {
                        "comparables": [],
                        "unit_comparables": [
                            {
                                "address": "220 NE 211 ST",
                                "sale_price": 594000.0,
                                "sale_date": "2026-05-05",
                                "lot_size_sqft": 3007.0,
                                "zoning_code": "",
                                "distance_miles": 4.91,
                                "price_per_acre": 0.0,
                                "price_per_unit": 594000.0,
                                "adjustments": {"qualification_score": 0.56},
                            }
                        ],
                        "estimated_land_value": 0.0,
                        "adv_per_unit": 594000.0,
                        "adv_per_unit_low": 594000.0,
                        "adv_per_unit_high": 594000.0,
                        "confidence": 0.45,
                        "notes": ["Wider-radius improved-sale signal inside 5 miles."],
                    }
                }
        elif request.tool_name == "run_noi_valuation":
            payload = {
                "calculation_type": "noi_valuation",
                "formula_version": "noi_valuation.v1",
                "gross_scheduled_income": 38400.0,
                "effective_gross_income": 36480.0,
                "operating_expenses": 12768.0,
                "annual_noi": 23712.0,
                "as_built_value": 395200.0,
                "warnings": [],
            }
        elif request.tool_name == "run_residual_land_value":
            payload = {
                "calculation_type": "residual_land_value",
                "formula_version": "residual_land_value.v1",
                "total_project_costs_excluding_land": 270000.0,
                "max_supportable_land_price": 125000.0,
                "spread_to_asking_price": 125000.0,
                "go_no_go_signal": "go",
                "warnings": [],
            }
        else:
            payload = _live_tool_payload(request.tool_name, dict(request.args))

        return HarnessToolCallResult(
            ok=True,
            tool_call_id=ToolCallId(f"tool_call_{request.tool_name}_{len(observed_searches)}"),
            tool_name=request.tool_name,
            run_id=RunId(str(request.run_id)),
            args=dict(request.args),
            status=ToolRouteStatus.COMPLETED,
            policy_decision=PolicyDecision(allowed=True, reason="test"),
            payload=payload,
            events=[],
            source_mode=request.source_mode,
        )

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "45 NW 209 ST, Miami Gardens, FL 33169",
            "analysis_type": "acquisition_memo",
            "source_mode": "live",
            "assumptions": {
                "maxUnits": 1,
                "maxLotCoveragePct": 40,
                "lotFrontageFt": 75,
                "frontSetbackFt": 25,
                "sideSetbackFt": 7.5,
                "avgUnitSizeSf": 1800,
                "monthlyRentPerUnit": 3200,
                "operatingExpensePct": 0.35,
                "capRate": 0.06,
                "hardCosts": 180000,
                "softCosts": 36000,
                "contingency": 12000,
                "developerFee": 10000,
                "closingCosts": 8000,
                "financingCosts": 12000,
                "holdingCosts": 7000,
                "sellingCosts": 5000,
                "targetProfitPct": 0.18,
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert observed_searches == [(6, 3.0), (12, 3.0), (24, 3.0), (24, 6.0)]
    selected_attempts = [
        attempt
        for attempt in data["artifacts"]["comp_search_strategy"]["attempts"]
        if attempt["selected"]
    ]
    assert len(selected_attempts) == 1
    assert selected_attempts[0]["radius_miles"] == pytest.approx(3.0)
    assert selected_attempts[0]["adv_per_unit"] == pytest.approx(446250.0)
    assert selected_attempts[0]["selection_reason"] == "qualified_exit_comp_fallback"
    assert selected_attempts[0]["best_exit_fit_score"] == pytest.approx(1.0)
    assert selected_attempts[0]["best_exit_price_variance_ratio"] == pytest.approx(0.0)
    assert selected_attempts[0]["best_exit_qualification_score"] == pytest.approx(0.9)
    assert data["artifacts"]["comps"]["adv_per_unit"] == pytest.approx(446250.0)
    assert (
        data["artifacts"]["comp_search_strategy"]["selected_reason"]
        == "qualified_exit_comp_fallback"
    )
    assert data["artifacts"]["comp_search_strategy"]["exit_signal_tier"] == "strict_improved_sales"
    assert data["artifacts"]["comp_search_strategy"]["best_exit_comp_fit_score"] == pytest.approx(
        1.0
    )
    assert data["artifacts"]["comp_search_strategy"][
        "best_exit_comp_price_variance_ratio"
    ] == pytest.approx(0.0)
    assert data["artifacts"]["comp_search_strategy"][
        "best_exit_comp_qualification_score"
    ] == pytest.approx(0.9)
    assert data["artifacts"]["comp_search_strategy"]["used_relaxed_unit_comps"] is False
    assert data["artifacts"]["acquisition_guidance"]["recommended_action"] == "insufficient_support"
    assert data["artifacts"]["acquisition_guidance"]["basis"] == "comping_underwriting_not_ready"
    assert data["artifacts"]["acquisition_guidance"]["land_comp_signal_available"] is False
    assert data["artifacts"]["acquisition_guidance"]["exit_comp_signal_available"] is True
    assert data["artifacts"]["acquisition_guidance"]["max_supportable_land_price"] == 0.0
    underwriting_section = next(
        section
        for section in data["report"]["sections"]
        if section["section_id"] == "underwriting_summary"
    )
    assert underwriting_section["comp_support_summary"]["land_support_source"] == "none"
    assert underwriting_section["comp_support_summary"]["exit_support_fit_score"] == pytest.approx(
        1.0
    )
    assert underwriting_section["comp_support_summary"]["combined_support_tier"] == "exit_only"


@pytest.mark.asyncio
async def test_deal_analysis_live_run_derives_feasibility_from_verified_dimensional_standard(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    parcel_geometry = [
        [-80.1592, 26.1404],
        [-80.159051, 26.1404],
        [-80.159051, 26.1407297],
        [-80.1592, 26.1407297],
        [-80.1592, 26.1404],
    ]

    async def _fake_tool_result(request) -> HarnessToolCallResult:
        if request.tool_name == "geocode_address":
            payload = {
                "status": "success",
                "result": {
                    "address": str(request.args["address"]),
                    "municipality": "Fort Lauderdale",
                    "county": "Broward",
                    "state": "FL",
                    "lat": 26.1404,
                    "lng": -80.1592,
                },
            }
        elif request.tool_name == "lookup_property_info":
            payload = {
                "status": "success",
                "result": {
                    "folio": "494233281490",
                    "address": str(request.args["address"]),
                    "municipality": "Fort Lauderdale",
                    "county": "Broward",
                    "zoning_code": "RS-8",
                    "ordinance_district_code": "RS-8",
                    "zoning_description": "Single Family Residential",
                    "lot_size_sqft": 6000,
                    "parcel_geometry": parcel_geometry,
                    "living_units": 1,
                    "zoning_layer_url": "https://example.test/ftl-zoning",
                },
            }
        elif request.tool_name == "compute_feasibility":
            assert request.args["max_far"] == pytest.approx(0.75)
            assert request.args["max_units"] == 1
            assert request.args["lot_frontage_ft"] == pytest.approx(48.69, abs=0.1)
            assert request.args["lot_depth_ft"] == pytest.approx(120.01, abs=0.1)
            assert request.args["setback_front_ft"] == pytest.approx(25.0)
            assert request.args["setback_side_ft"] == pytest.approx(5.0)
            assert request.args["setback_rear_ft"] == pytest.approx(15.0)
            assert request.args["max_lot_coverage_pct"] == pytest.approx(50.0)
            payload = {
                "result": {
                    "calculation_type": "feasibility",
                    "formula_version": "feasibility.v1",
                    "max_gross_buildable_sf": 3000.0,
                    "net_rentable_sf": 2550.0,
                    "estimated_units": 1,
                    "parking_required": 2,
                    "major_constraints": ["lot_coverage"],
                    "feasibility_warnings": [],
                }
            }
        else:
            payload = _live_tool_payload(request.tool_name, dict(request.args))

        return HarnessToolCallResult(
            ok=True,
            tool_call_id=ToolCallId(f"tool_call_{request.tool_name}"),
            tool_name=request.tool_name,
            run_id=RunId(str(request.run_id)),
            args=dict(request.args),
            status=ToolRouteStatus.COMPLETED,
            policy_decision=PolicyDecision(allowed=True, reason="test"),
            payload=payload,
            events=[],
            source_mode=request.source_mode,
        )

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "1234 NW 15th St, Fort Lauderdale, FL 33311",
            "analysis_type": "acquisition_memo",
            "source_mode": "live",
            "assumptions": {
                "avgUnitSizeSf": 850,
                "efficiencyFactor": 0.85,
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert any(call["tool_name"] == "compute_feasibility" for call in data["tool_calls"])
    assert "feasibility" in data["artifacts"]
    assert not any(
        "provide maxFar and maxUnits assumptions" in warning
        for warning in data["artifacts"].get("warnings", [])
    )
    assert any(
        "estimated lot frontage from parcel geometry" in warning
        for warning in data["artifacts"].get("warnings", [])
    )
    feasibility_stage = next(
        stage for stage in data["pipeline_stages"] if stage["key"] == "feasibility"
    )
    assert feasibility_stage["status"] == "completed"


@pytest.mark.asyncio
async def test_deal_analysis_live_run_uses_staged_miami_gardens_standard_when_ordinance_results_are_generic(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    async def _fake_tool_result(request) -> HarnessToolCallResult:
        if request.tool_name == "geocode_address":
            payload = {
                "status": "success",
                "result": {
                    "address": str(request.args["address"]),
                    "municipality": "Miami",
                    "county": "Miami-Dade",
                    "state": "FL",
                    "lat": 25.967404,
                    "lng": -80.202576,
                },
            }
        elif request.tool_name == "lookup_property_info":
            payload = {
                "status": "success",
                "result": {
                    "folio": "3411360031910",
                    "address": "45 NW 209 ST",
                    "municipality": "Miami Gardens",
                    "county": "Miami-Dade",
                    "zoning_code": "R-1",
                    "ordinance_district_code": "R-1",
                    "zoning_description": "Single-family detached residential",
                    "lot_size_sqft": 10105.0,
                    "lot_dimensions": "96.24 x 105",
                    "living_units": 0,
                    "last_sale_price": 80000.0,
                    "zoning_layer_url": "https://example.test/miami-gardens-zoning",
                },
            }
        elif request.tool_name == "search_zoning_ordinance":
            payload = {
                "status": "success",
                "results": [
                    {
                        "section": "Sec. 34-347.",
                        "title": "Maximum setbacks in certain districts.",
                        "zone_codes": ["R-1", "R-2"],
                        "text": "The front setback distance of the principal building in the R-1 and R-2 districts shall not exceed 50 feet.",
                        "citation": {
                            "jurisdiction": "Miami Gardens",
                            "url": "https://example.test/miami-gardens/sec-34-347",
                        },
                    }
                ],
            }
        elif request.tool_name == "compute_feasibility":
            assert request.args["max_units"] == 1
            assert request.args["lot_frontage_ft"] == pytest.approx(96.24)
            assert request.args["lot_depth_ft"] == pytest.approx(105.0)
            assert request.args["setback_front_ft"] == pytest.approx(25.0)
            assert request.args["setback_side_ft"] == pytest.approx(7.5)
            assert request.args["setback_rear_ft"] == pytest.approx(25.0)
            assert request.args["max_lot_coverage_pct"] == pytest.approx(40.0)
            payload = {
                "result": {
                    "calculation_type": "feasibility",
                    "formula_version": "feasibility.v2",
                    "max_gross_buildable_sf": 4042.0,
                    "net_rentable_sf": 3435.7,
                    "estimated_units": 1,
                    "parking_required": 2,
                    "major_constraints": ["max_units"],
                    "area_limiters": ["lot_coverage"],
                    "feasibility_warnings": [],
                }
            }
        elif request.tool_name in {"search_municode_live", "web_search"}:
            payload = {"status": "success", "results": []}
        else:
            payload = _live_tool_payload(request.tool_name, dict(request.args))

        return HarnessToolCallResult(
            ok=True,
            tool_call_id=ToolCallId(f"tool_call_{request.tool_name}"),
            tool_name=request.tool_name,
            run_id=RunId(str(request.run_id)),
            args=dict(request.args),
            status=ToolRouteStatus.COMPLETED,
            policy_decision=PolicyDecision(allowed=True, reason="test"),
            payload=payload,
            events=[],
            source_mode=request.source_mode,
        )

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "45 NW 209 ST, Miami Gardens, FL 33169",
            "analysis_type": "acquisition_memo",
            "source_mode": "live",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["artifacts"]["site"]["address"] == "45 NW 209 ST"
    assert data["artifacts"]["site"]["municipality"] == "Miami Gardens"
    assert data["artifacts"]["site"]["county"] == "Miami-Dade"
    assert data["artifacts"]["gis_site_context"]["municipality"] == "Miami Gardens"
    assert data["artifacts"]["ordinance_search"]["fallback_source"] == "staged_dimensional_standard"
    assert data["artifacts"]["ordinance_rules"]["zoning_district"] == "R-1"
    assert data["artifacts"]["ordinance_rules"]["min_lot_area_sqft"] == pytest.approx(7500.0)
    assert data["artifacts"]["ordinance_rules"]["setback_front_ft"] == pytest.approx(25.0)
    assert data["artifacts"]["ordinance_rules"]["setback_side_ft"] == pytest.approx(7.5)
    assert data["artifacts"]["ordinance_rules"]["setback_rear_ft"] == pytest.approx(25.0)
    assert data["artifacts"]["ordinance_rules"]["max_lot_coverage_pct"] == pytest.approx(40.0)
    assert data["artifacts"]["ordinance_rules"]["max_density_units_per_acre"] == pytest.approx(6.0)
    assert data["artifacts"]["feasibility"]["result"]["estimated_units"] == 1
    assert any(
        "preliminary staged zoning standards for Miami Gardens R-1" in warning
        for warning in data["artifacts"].get("warnings", [])
    )


@pytest.mark.asyncio
async def test_deal_analysis_live_run_accepts_manual_single_family_dimensional_inputs(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    async def _fake_tool_result(request) -> HarnessToolCallResult:
        if request.tool_name == "geocode_address":
            payload = {
                "status": "success",
                "result": {
                    "address": str(request.args["address"]),
                    "municipality": "Miami Gardens",
                    "county": "Miami-Dade",
                    "state": "FL",
                    "lat": 25.9696,
                    "lng": -80.2101,
                },
            }
        elif request.tool_name == "lookup_property_info":
            payload = {
                "status": "success",
                "result": {
                    "folio": "3411360031910",
                    "address": str(request.args["address"]),
                    "municipality": "Miami Gardens",
                    "county": "Miami-Dade",
                    "zoning_code": "R-1",
                    "ordinance_district_code": "R-1",
                    "zoning_description": "Single-family detached residential",
                    "land_use_description": "VACANT RESIDENTIAL",
                    "lot_size_sqft": 10105,
                    "living_units": 0,
                    "zoning_layer_url": "https://example.test/miami-gardens-zoning",
                },
            }
        elif request.tool_name == "compute_feasibility":
            assert request.args["max_units"] == 1
            assert request.args["max_lot_coverage_pct"] == pytest.approx(40.0)
            assert request.args["lot_frontage_ft"] == pytest.approx(75.0)
            assert request.args["setback_front_ft"] == pytest.approx(25.0)
            assert request.args["setback_side_ft"] == pytest.approx(7.5)
            assert request.args["setback_rear_ft"] == pytest.approx(25.0)
            payload = {
                "result": {
                    "calculation_type": "feasibility",
                    "formula_version": "feasibility.v2",
                    "max_gross_buildable_sf": 4042.0,
                    "net_rentable_sf": 3435.7,
                    "estimated_units": 1,
                    "parking_required": 2,
                    "major_constraints": ["max_units"],
                    "area_limiters": ["lot_coverage", "setback_envelope"],
                    "lot_depth_ft": 134.73,
                    "buildable_envelope_sf": 5084.0,
                    "lot_coverage_limited_sf": 4042.0,
                    "feasibility_warnings": [],
                }
            }
        else:
            payload = _live_tool_payload(request.tool_name, dict(request.args))

        return HarnessToolCallResult(
            ok=True,
            tool_call_id=ToolCallId(f"tool_call_{request.tool_name}"),
            tool_name=request.tool_name,
            run_id=RunId(str(request.run_id)),
            args=dict(request.args),
            status=ToolRouteStatus.COMPLETED,
            policy_decision=PolicyDecision(allowed=True, reason="test"),
            payload=payload,
            events=[],
            source_mode=request.source_mode,
        )

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "45 NW 209 ST, Miami Gardens, FL 33169",
            "analysis_type": "acquisition_memo",
            "source_mode": "live",
            "assumptions": {
                "maxDensityUnitsPerAcre": 6,
                "minLotAreaSf": 7500,
                "minLotFrontageFt": 75,
                "lotFrontageFt": 75,
                "frontSetbackFt": 25,
                "sideSetbackFt": 7.5,
                "rearSetbackFt": 25,
                "maxLotCoveragePct": 40,
                "maxHeightFt": 35,
                "maxStories": 2,
                "waterSetbackFt": 0,
                "accessorySeparationFt": 10,
                "parkingSpacesPerUnit": 2,
                "avgUnitSizeSf": 1700,
                "monthlyRentPerUnit": 3200,
                "operatingExpensePct": 0.35,
                "capRate": 0.06,
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["artifacts"]["feasibility"]["result"]["formula_version"] == "feasibility.v2"
    assert data["artifacts"]["gis_site_context"]["county"] == "Miami-Dade"
    assert data["artifacts"]["gis_site_context"]["municipality"] == "Miami Gardens"
    assert data["artifacts"]["gis_site_context"]["controlling_zoning_authority"] == "municipal"
    assert (
        data["artifacts"]["gis_site_context"]["controlling_zoning_jurisdiction"] == "Miami Gardens"
    )
    assert data["artifacts"]["gis_site_context"]["zoning_record_applicability"] == "direct"
    assert data["artifacts"]["gis_site_context"]["warning"] == ""
    assert data["artifacts"]["gis_site_context"]["recommended_zoning_source_ids"]
    assert data["artifacts"]["manual_dimensional_standards"][
        "max_lot_coverage_pct"
    ] == pytest.approx(40.0)
    assert data["artifacts"]["manual_dimensional_standards"][
        "min_lot_frontage_ft"
    ] == pytest.approx(75.0)
    assert data["artifacts"]["manual_dimensional_standards"]["rear_setback_ft"] == pytest.approx(
        25.0
    )
    assert data["artifacts"]["manual_dimensional_standards"]["max_height_ft"] == pytest.approx(35.0)
    assert data["artifacts"]["manual_dimensional_standards"]["max_stories"] == pytest.approx(2.0)
    assert data["artifacts"]["manual_dimensional_standards"]["water_setback_ft"] == pytest.approx(
        0.0
    )
    assert data["artifacts"]["manual_dimensional_standards"][
        "accessory_separation_ft"
    ] == pytest.approx(10.0)
    assert any(
        item["source_type"] == "user_assumption"
        and item["source_name"] == "User-supplied dimensional standards"
        and "minimum frontage 75.0 ft" in item["normalized_text"]
        and "rear setback 25.0 ft" in item["normalized_text"]
        and "maximum height 35.0 ft" in item["normalized_text"]
        for item in data["evidence_items"]
    )
    assert any(
        item["source_type"] == "gis_layer"
        and item["source_name"] == "South Florida GIS site context"
        and item["applicability"] == "direct"
        for item in data["evidence_items"]
    )
    assert any(
        claim["claim_type"] == "manual_dimensional_standards"
        and "minimum frontage 75.0 ft" in claim["claim_text"]
        and "lot coverage 40.0%" in claim["claim_text"]
        and "rear setback 25.0 ft" in claim["claim_text"]
        and "maximum height 35.0 ft" in claim["claim_text"]
        for claim in data["claims"]
    )
    assert data["report"]["sections"][1]["feasibility"]["result"][
        "max_gross_buildable_sf"
    ] == pytest.approx(4042.0)


@pytest.mark.asyncio
async def test_deal_analysis_live_run_uses_minimum_frontage_as_conservative_proxy(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    async def _fake_tool_result(request) -> HarnessToolCallResult:
        if request.tool_name == "geocode_address":
            payload = {
                "status": "success",
                "result": {
                    "address": str(request.args["address"]),
                    "municipality": "Miami Gardens",
                    "county": "Miami-Dade",
                    "state": "FL",
                    "lat": 25.9696,
                    "lng": -80.2101,
                },
            }
        elif request.tool_name == "lookup_property_info":
            payload = {
                "status": "success",
                "result": {
                    "folio": "3411360031910",
                    "address": str(request.args["address"]),
                    "municipality": "Miami Gardens",
                    "county": "Miami-Dade",
                    "zoning_code": "R-1",
                    "ordinance_district_code": "R-1",
                    "zoning_description": "Single-family detached residential",
                    "land_use_description": "VACANT RESIDENTIAL",
                    "lot_size_sqft": 10105,
                    "living_units": 0,
                    "zoning_layer_url": "https://example.test/miami-gardens-zoning",
                },
            }
        elif request.tool_name == "compute_feasibility":
            assert request.args["lot_frontage_ft"] == pytest.approx(75.0)
            assert request.args["setback_front_ft"] == pytest.approx(25.0)
            assert request.args["setback_side_ft"] == pytest.approx(7.5)
            assert request.args["setback_rear_ft"] == pytest.approx(25.0)
            payload = {
                "result": {
                    "calculation_type": "feasibility",
                    "formula_version": "feasibility.v2",
                    "max_gross_buildable_sf": 4042.0,
                    "net_rentable_sf": 3435.7,
                    "estimated_units": 1,
                    "parking_required": 2,
                    "major_constraints": ["max_units"],
                    "area_limiters": ["lot_coverage", "setback_envelope"],
                    "lot_depth_ft": None,
                    "buildable_envelope_sf": None,
                    "lot_coverage_limited_sf": 4042.0,
                    "feasibility_warnings": [],
                }
            }
        else:
            payload = _live_tool_payload(request.tool_name, dict(request.args))

        return HarnessToolCallResult(
            ok=True,
            tool_call_id=ToolCallId(f"tool_call_{request.tool_name}"),
            tool_name=request.tool_name,
            run_id=RunId(str(request.run_id)),
            args=dict(request.args),
            status=ToolRouteStatus.COMPLETED,
            policy_decision=PolicyDecision(allowed=True, reason="test"),
            payload=payload,
            events=[],
            source_mode=request.source_mode,
        )

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "45 NW 209 ST, Miami Gardens, FL 33169",
            "analysis_type": "acquisition_memo",
            "source_mode": "live",
            "assumptions": {
                "maxDensityUnitsPerAcre": 6,
                "minLotAreaSf": 7500,
                "minLotFrontageFt": 75,
                "frontSetbackFt": 25,
                "sideSetbackFt": 7.5,
                "rearSetbackFt": 25,
                "maxLotCoveragePct": 40,
                "avgUnitSizeSf": 1700,
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert any(
        "user-supplied minimum frontage as a conservative frontage proxy" in warning
        for warning in data["artifacts"].get("warnings", [])
    )


@pytest.mark.asyncio
async def test_deal_analysis_live_run_uses_manual_land_and_exit_comps(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    observed_pro_forma_args: dict[str, object] = {}

    async def _fake_tool_result(request) -> HarnessToolCallResult:
        nonlocal observed_pro_forma_args
        if request.tool_name == "geocode_address":
            payload = {
                "status": "success",
                "result": {
                    "address": str(request.args["address"]),
                    "municipality": "Miami Gardens",
                    "county": "Miami-Dade",
                    "state": "FL",
                    "lat": 25.9696,
                    "lng": -80.2101,
                },
            }
        elif request.tool_name == "lookup_property_info":
            payload = {
                "status": "success",
                "result": {
                    "folio": "3411360031910",
                    "address": str(request.args["address"]),
                    "municipality": "Miami Gardens",
                    "county": "Miami-Dade",
                    "zoning_code": "R-1",
                    "ordinance_district_code": "R-1",
                    "zoning_description": "Single-family detached residential",
                    "land_use_description": "VACANT RESIDENTIAL",
                    "lot_size_sqft": 10105,
                    "living_units": 0,
                    "zoning_layer_url": "https://example.test/miami-gardens-zoning",
                },
            }
        elif request.tool_name == "find_comparables":
            payload = {
                "status": "success",
                "analysis": {
                    "comparables": [],
                    "unit_comparables": [],
                    "estimated_land_value": 0.0,
                    "estimated_land_value_low": 0.0,
                    "estimated_land_value_high": 0.0,
                    "adv_per_unit": None,
                    "adv_per_unit_low": None,
                    "adv_per_unit_high": None,
                    "adv_source": "",
                    "confidence": 0.2,
                    "notes": ["No automated comps found."],
                },
            }
        elif request.tool_name == "compute_feasibility":
            payload = {
                "max_gross_buildable_sf": 4042.0,
                "net_rentable_sf": 3435.7,
                "estimated_units": 1,
                "parking_required": 2,
                "major_constraints": ["max_units"],
                "area_limiters": ["lot_coverage", "setback_envelope"],
                "lot_depth_ft": 134.73,
                "buildable_envelope_sf": 5084.0,
                "lot_coverage_limited_sf": 4042.0,
                "feasibility_warnings": [],
            }
        elif request.tool_name == "run_pro_forma":
            observed_pro_forma_args = dict(request.args)
            payload = {
                "result": {
                    "gross_development_value": 520000.0,
                    "hard_costs": 265000.0,
                    "soft_costs": 53000.0,
                    "builder_margin": 25000.0,
                    "impact_fees": 0.0,
                    "impact_fees_per_unit": 0.0,
                    "max_supportable_land_price": 120000.0,
                    "cost_per_door": 343000.0,
                    "construction_cost_psf": 180.0,
                    "avg_unit_size_sqft": 1700.0,
                    "adv_per_unit": 520000.0,
                    "max_units": 1,
                    "soft_cost_pct": 0.2,
                    "builder_margin_pct": 0.08,
                    "adv_source": "manual_comps",
                    "market": "South Florida",
                    "notes": [],
                }
            }
        else:
            payload = _live_tool_payload(request.tool_name, dict(request.args))

        return HarnessToolCallResult(
            ok=True,
            tool_call_id=ToolCallId(f"tool_call_{request.tool_name}"),
            tool_name=request.tool_name,
            run_id=RunId(str(request.run_id)),
            args=dict(request.args),
            status=ToolRouteStatus.COMPLETED,
            policy_decision=PolicyDecision(allowed=True, reason="test"),
            payload=payload,
            events=[],
            source_mode=request.source_mode,
        )

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "45 NW 209 ST, Miami Gardens, FL 33169",
            "analysis_type": "acquisition_memo",
            "source_mode": "live",
            "assumptions": {
                "maxDensityUnitsPerAcre": 6,
                "lotFrontageFt": 75,
                "frontSetbackFt": 25,
                "sideSetbackFt": 7.5,
                "rearSetbackFt": 25,
                "maxLotCoveragePct": 40,
                "avgUnitSizeSf": 1700,
                "manualLandComps": [
                    {
                        "address": "17605 NW 19th Avenue, Miami Gardens, FL 33056",
                        "salePrice": 135000,
                        "saleDate": "2025-12-01",
                        "lotSizeSqft": 9000,
                        "sourceUrl": "https://example.test/land-1",
                    },
                    {
                        "address": "2940 NW 169th Ter, Miami Gardens, FL 33056",
                        "salePrice": 145000,
                        "saleDate": "2025-10-10",
                        "lotSizeSqft": 10000,
                        "sourceUrl": "https://example.test/land-2",
                    },
                ],
                "manualExitComps": [
                    {
                        "address": "105 NE 213th St, Miami Gardens, FL 33179",
                        "salePrice": 699000,
                        "saleDate": "2026-01-20",
                        "units": 1,
                        "sourceUrl": "https://example.test/exit-1",
                    },
                    {
                        "address": "115 NE 213th St, Miami Gardens, FL 33179",
                        "salePrice": 500000,
                        "saleDate": "2025-11-05",
                        "units": 1,
                        "sourceUrl": "https://example.test/exit-2",
                    },
                    {
                        "address": "100 NW 208th St, Miami Gardens, FL 33169",
                        "salePrice": 500000,
                        "saleDate": "2025-09-12",
                        "units": 1,
                        "sourceUrl": "https://example.test/exit-3",
                    },
                ],
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert observed_pro_forma_args["adv_per_unit"] == pytest.approx(500000.0)
    assert observed_pro_forma_args["estimated_land_value"] == pytest.approx(149048.75)
    assert data["artifacts"]["manual_comparables"]["land_comp_count"] == 2
    assert data["artifacts"]["manual_comparables"]["exit_comp_count"] == 3
    assert data["artifacts"]["comps"]["manual_comp_override"] is True
    assert data["artifacts"]["underwriting_mode"]["pricing_source"] == "manual_comps"
    assert data["artifacts"]["acquisition_guidance"]["pricing_basis"] == "user_supplied_comps"
    assert data["artifacts"]["acquisition_guidance"]["pricing_source"] == "manual_comps"
    assert data["artifacts"]["acquisition_guidance"]["recommended_action"] == "offer_range"
    assert data["artifacts"]["acquisition_guidance"]["recommended_offer"] == pytest.approx(120000.0)
    assert data["artifacts"]["acquisition_guidance"]["recommended_offer_low"] == pytest.approx(
        120000.0
    )
    assert data["artifacts"]["acquisition_guidance"]["recommended_offer_high"] == pytest.approx(
        120000.0
    )
    assert data["artifacts"]["acquisition_guidance"]["land_value_signal"] == pytest.approx(
        149048.75
    )
    assert data["artifacts"]["acquisition_guidance"]["market_land_value_low"] == pytest.approx(
        147785.62, abs=0.01
    )
    assert data["artifacts"]["acquisition_guidance"]["market_land_value_high"] == pytest.approx(
        150311.88, abs=0.01
    )
    assert data["artifacts"]["acquisition_guidance"]["adv_per_unit"] == pytest.approx(500000.0)
    assert data["artifacts"]["acquisition_guidance"]["market_to_residual_gap"] == pytest.approx(
        29048.75
    )
    assert data["artifacts"]["feasibility"]["estimated_units"] == 1
    assert data["artifacts"]["feasibility"]["max_gross_buildable_sf"] == pytest.approx(4042.0)
    assert data["artifacts"]["feasibility"]["buildable_envelope_sf"] == pytest.approx(5084.0)
    assert data["artifacts"]["feasibility"]["lot_coverage_limited_sf"] == pytest.approx(4042.0)
    assert data["artifacts"]["feasibility"]["major_constraints"] == ["max_units"]
    assert all("rear setback" not in warning.lower() for warning in data["artifacts"]["warnings"])
    assert any(
        item["provider"] == "user_provided_comp"
        for item in data["evidence_items"]
        if item["source_type"] == "market_comp"
    )


@pytest.mark.asyncio
async def test_deal_analysis_live_run_surfaces_owner_basis_warning_for_miami_gardens_lot(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    async def _fake_tool_result(request) -> HarnessToolCallResult:
        if request.tool_name == "geocode_address":
            payload = {
                "status": "success",
                "result": {
                    "address": str(request.args["address"]),
                    "municipality": "Miami Gardens",
                    "county": "Miami-Dade",
                    "state": "FL",
                    "lat": 25.967404,
                    "lng": -80.202576,
                },
            }
        elif request.tool_name == "lookup_property_info":
            payload = {
                "status": "success",
                "result": {
                    "folio": "3411360031910",
                    "address": "45 NW 209 ST",
                    "municipality": "Miami Gardens",
                    "county": "Miami-Dade",
                    "zoning_code": "R-1",
                    "ordinance_district_code": "R-1",
                    "zoning_description": "Single-family detached residential",
                    "land_use_code": "0066",
                    "land_use_description": "VACANT RESIDENTIAL",
                    "lot_size_sqft": 10105.0,
                    "living_units": 0,
                    "last_sale_price": 80000.0,
                    "zoning_layer_url": "https://example.test/miami-gardens-zoning",
                },
            }
        elif request.tool_name == "find_comparables":
            payload = {
                "analysis": {
                    "comparables": [
                        {
                            "address": "17605 NW 19th Avenue",
                            "sale_price": 145000.0,
                            "sale_date": "2026-02-01",
                            "lot_size_sqft": 9500.0,
                            "zoning_code": "R-1",
                            "distance_miles": 4.12,
                            "price_per_acre": 665789.47,
                            "adjustments": {},
                        }
                    ],
                    "estimated_land_value": 154391.78,
                    "estimated_land_value_low": 154391.78,
                    "estimated_land_value_high": 154391.78,
                    "adv_per_unit": 505000.0,
                    "adv_per_unit_low": 485000.0,
                    "adv_per_unit_high": 602000.0,
                    "unit_comparables": [
                        {
                            "address": "105 NE 213 ST",
                            "sale_price": 699000.0,
                            "sale_date": "2026-04-21",
                            "lot_size_sqft": 7500.0,
                            "zoning_code": "",
                            "distance_miles": 0.34,
                            "price_per_acre": 0.0,
                            "price_per_unit": 699000.0,
                            "adjustments": {},
                        }
                    ],
                    "confidence": 0.55,
                    "notes": [
                        "Land comps suggest the seller may expect more than a residual buyer can support."
                    ],
                }
            }
        elif request.tool_name == "run_residual_land_value":
            payload = {
                "result": {
                    "calculation_type": "residual_land_value",
                    "formula_version": "residual_land_value.v1",
                    "total_project_costs_excluding_land": 425000.0,
                    "max_supportable_land_price": -95000.0,
                    "spread_to_asking_price": -95000.0,
                    "go_no_go_signal": "no_go",
                    "warnings": [
                        "Negative residual land value: costs and profit exceed as-built value."
                    ],
                }
            }
        else:
            payload = _live_tool_payload(request.tool_name, dict(request.args))

        return HarnessToolCallResult(
            ok=True,
            tool_call_id=ToolCallId(f"tool_call_{request.tool_name}"),
            tool_name=request.tool_name,
            run_id=RunId(str(request.run_id)),
            args=dict(request.args),
            status=ToolRouteStatus.COMPLETED,
            policy_decision=PolicyDecision(allowed=True, reason="test"),
            payload=payload,
            events=[],
            source_mode=request.source_mode,
        )

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "45 NW 209 ST, Miami Gardens, FL 33169",
            "analysis_type": "acquisition_memo",
            "source_mode": "live",
            "assumptions": {
                "maxUnits": 1,
                "maxLotCoveragePct": 40,
                "lotFrontageFt": 75,
                "frontSetbackFt": 25,
                "sideSetbackFt": 7.5,
                "avgUnitSizeSf": 1700,
                "monthlyRentPerUnit": 3200,
                "operatingExpensePct": 0.35,
                "capRate": 0.06,
                "hardCosts": 265000,
                "softCosts": 53000,
                "contingency": 20000,
                "developerFee": 25000,
                "closingCosts": 12000,
                "financingCosts": 18000,
                "holdingCosts": 12000,
                "sellingCosts": 35000,
                "targetProfitPct": 0.18,
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["artifacts"]["acquisition_guidance"]["recommended_action"] == "no_offer"
    assert data["artifacts"]["acquisition_guidance"]["owner_basis_warning"] == (
        "Prior recorded sale price was 80000; seller expectations may exceed supportable pricing."
    )
    assert data["artifacts"]["acquisition_guidance"]["market_to_residual_gap"] == pytest.approx(
        249391.78
    )


@pytest.mark.asyncio
async def test_deal_analysis_live_run_uses_miami21_preliminary_capacity_when_indexed_ordinance_is_misaligned(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    async def _fake_tool_result(request) -> HarnessToolCallResult:
        if request.tool_name == "geocode_address":
            payload = {
                "status": "success",
                "result": {
                    "address": str(request.args["address"]),
                    "municipality": "Miami",
                    "county": "Miami-Dade",
                    "state": "FL",
                    "lat": 25.790642,
                    "lng": -80.20681,
                },
            }
        elif request.tool_name == "lookup_property_info":
            payload = {
                "status": "success",
                "result": {
                    "folio": "0131360600010",
                    "address": "1603 NW 7 AVE",
                    "municipality": "Miami",
                    "county": "Miami-Dade",
                    "zoning_code": "CI-HD",
                    "zoning_description": "",
                    "lot_size_sqft": 43560,
                    "living_units": 0,
                    "lat": 25.790642,
                    "lng": -80.20681,
                    "zoning_layer_url": "",
                },
            }
        elif request.tool_name == "search_zoning_ordinance":
            payload = {
                "status": "success",
                "results": [
                    {
                        "section": "Sec. 33-284.62.",
                        "title": "Development parameters.",
                        "zone_codes": ["BU-1", "BU-2"],
                        "text": "Unincorporated Miami-Dade section that does not mention CI-HD.",
                        "citation": {
                            "url": "https://library.municode.com/fl/miami_dade",
                            "jurisdiction": "Unincorporated Miami-Dade",
                        },
                    }
                ],
            }
        elif request.tool_name == "web_search":
            payload = {
                "status": "success",
                "provider": "exa",
                "results": [
                    {
                        "title": "View City of Miami Zoning Code (Miami 21)",
                        "url": "https://www.miami.gov/Planning-Zoning-Land-Use/View-City-of-Miami-Zoning-Code-Miami-21",
                        "description": "Official City of Miami Miami 21 code page.",
                        "content": "CI-HD official Miami 21 zoning code reference.",
                        "citation": {
                            "url": "https://www.miami.gov/Planning-Zoning-Land-Use/View-City-of-Miami-Zoning-Code-Miami-21",
                            "jurisdiction": "Miami",
                        },
                    }
                ],
            }
        elif request.tool_name == "compute_feasibility":
            assert request.args["max_far"] == pytest.approx(8.0)
            assert request.args["max_units"] == 150
            payload = {
                "result": {
                    "calculation_type": "feasibility",
                    "formula_version": "feasibility.v1",
                    "max_gross_buildable_sf": 348480.0,
                    "net_rentable_sf": 296208.0,
                    "estimated_units": 150,
                    "parking_required": 225,
                    "major_constraints": ["max_units"],
                    "feasibility_warnings": [],
                }
            }
        else:
            payload = _live_tool_payload(request.tool_name, dict(request.args))

        return HarnessToolCallResult(
            ok=True,
            tool_call_id=ToolCallId(f"tool_call_{request.tool_name}"),
            tool_name=request.tool_name,
            run_id=RunId(str(request.run_id)),
            args=dict(request.args),
            status=ToolRouteStatus.COMPLETED,
            policy_decision=PolicyDecision(allowed=True, reason="test"),
            payload=payload,
            events=[],
            source_mode=request.source_mode,
        )

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "1600 NW 7th Ave, Miami, FL 33136",
            "analysis_type": "acquisition_memo",
            "source_mode": "live",
            "assumptions": {
                "avgUnitSizeSf": 850,
                "efficiencyFactor": 0.85,
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert any(call["tool_name"] == "web_search" for call in data["tool_calls"])
    assert any(call["tool_name"] == "compute_feasibility" for call in data["tool_calls"])
    assert "feasibility" in data["artifacts"]
    assert any(
        "preliminary Miami21 zoning standards" in warning
        for warning in data["artifacts"].get("warnings", [])
    )
    feasibility_stage = next(
        stage for stage in data["pipeline_stages"] if stage["key"] == "feasibility"
    )
    assert feasibility_stage["status"] == "completed"


@pytest.mark.asyncio
async def test_deal_analysis_live_run_falls_back_to_verified_local_ordinance_context(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    async def _fake_tool_result(request) -> HarnessToolCallResult:
        if request.tool_name == "geocode_address":
            payload = {
                "status": "success",
                "result": {
                    "address": str(request.args["address"]),
                    "municipality": "Fort Lauderdale",
                    "county": "Broward",
                    "state": "FL",
                    "lat": 26.1224,
                    "lng": -80.1373,
                },
            }
        elif request.tool_name == "lookup_property_info":
            payload = {
                "status": "success",
                "result": {
                    "folio": "504205120010",
                    "address": "1234 NW 15th St, Fort Lauderdale, FL 33311",
                    "municipality": "Fort Lauderdale",
                    "county": "Broward",
                    "zoning_code": "RS-8",
                    "ordinance_district_code": "RS-8",
                    "zoning_description": "Residential Single Family/Low Medium Density",
                    "lot_size_sqft": 6500,
                    "living_units": 1,
                    "zoning_layer_url": "https://example.test/ftl-zoning",
                },
            }
        elif request.tool_name in {"search_zoning_ordinance", "search_municode_live", "web_search"}:
            payload = {"status": "success", "results": []}
        else:
            payload = _live_tool_payload(request.tool_name, dict(request.args))
        return HarnessToolCallResult(
            ok=True,
            tool_call_id=ToolCallId(f"tool_call_{request.tool_name}"),
            tool_name=request.tool_name,
            run_id=RunId(str(request.run_id)),
            args=dict(request.args),
            status=ToolRouteStatus.COMPLETED,
            policy_decision=PolicyDecision(allowed=True, reason="test"),
            payload=payload,
            events=[],
            source_mode=request.source_mode,
        )

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "1234 NW 15th St, Fort Lauderdale, FL 33311",
            "analysis_type": "zoning_research",
            "source_mode": "live",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert (
        data["artifacts"]["ordinance_search"]["fallback_source"] == "verified_dimensional_standard"
    )
    assert (
        data["artifacts"]["ordinance_search"]["authority_confidence"]
        == "indexed_official_reference"
    )
    assert data["artifacts"]["ordinance_search"]["authority_is_live"] is False
    assert data["artifacts"]["gis_site_context"]["county"] == "Broward"
    assert data["artifacts"]["gis_site_context"]["municipality"] == "Fort Lauderdale"
    assert (
        data["artifacts"]["gis_site_context"]["warning"]
        == "Broward county zoning layers are contextual for municipal parcels; use municipal zoning code or GIS for entitlement standards."
    )
    assert any(
        "Broward county zoning layers are contextual for municipal parcels" in warning
        for warning in data["artifacts"].get("warnings", [])
    )
    assert any(
        item["source_type"] == "gis_layer"
        and item["source_name"] == "South Florida GIS site context"
        and item["applicability"] == "requires_municipal_verification"
        for item in data["evidence_items"]
    )
    underwriting_section = next(
        section
        for section in data["report"]["sections"]
        if section["section_id"] == "underwriting_summary"
    )
    assert (
        underwriting_section["zoning_support_summary"]["ordinance_source"]
        == "verified_dimensional_standard"
    )
    assert (
        underwriting_section["zoning_support_summary"]["authority_confidence"]
        == "indexed_official_reference"
    )
    assert underwriting_section["zoning_support_summary"]["authority_is_official"] is True
    assert underwriting_section["zoning_support_summary"]["gis_applicability"] == (
        "requires_municipal_verification"
    )
    assert data["artifacts"]["underwriting_stage"]["status"] == "not_required"
    zoning_stage = next(
        stage for stage in data["pipeline_stages"] if stage["key"] == "zoning_evidence"
    )
    assert zoning_stage["status"] == "warning"
    assert not any(
        "fell back to staged local zoning authority context" in warning
        for warning in data["artifacts"].get("warnings", [])
    )


@pytest.mark.asyncio
async def test_deal_analysis_live_run_rejects_broward_county_ordinance_for_municipal_parcel(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    async def _fake_tool_result(request) -> HarnessToolCallResult:
        if request.tool_name == "geocode_address":
            payload = {
                "status": "success",
                "result": {
                    "address": str(request.args["address"]),
                    "municipality": "Fort Lauderdale",
                    "county": "Broward",
                    "state": "FL",
                    "lat": 26.1224,
                    "lng": -80.1373,
                },
            }
        elif request.tool_name == "lookup_property_info":
            payload = {
                "status": "success",
                "result": {
                    "folio": "504205120010",
                    "address": "1234 NW 15th St, Fort Lauderdale, FL 33311",
                    "municipality": "Fort Lauderdale",
                    "county": "Broward",
                    "zoning_code": "RS-8",
                    "ordinance_district_code": "RS-8",
                    "zoning_description": "Residential Single Family/Low Medium Density",
                    "lot_size_sqft": 6500,
                    "living_units": 1,
                    "zoning_layer_url": "https://example.test/ftl-zoning",
                },
            }
        elif request.tool_name == "search_zoning_ordinance":
            payload = {
                "status": "success",
                "results": [
                    {
                        "section": "Sec. 39-10",
                        "section_id": "broward_rs_8",
                        "title": "Broward residential district standards",
                        "text": "RS-8 development standards for county residential districts.",
                        "zone_codes": ["RS-8"],
                        "citation": {
                            "url": "https://library.municode.com/fl/broward_county",
                            "jurisdiction": "Broward County",
                        },
                    }
                ],
            }
        elif request.tool_name in {"search_municode_live", "web_search"}:
            payload = {"status": "success", "results": []}
        else:
            payload = _live_tool_payload(request.tool_name, dict(request.args))
        return HarnessToolCallResult(
            ok=True,
            tool_call_id=ToolCallId(f"tool_call_{request.tool_name}"),
            tool_name=request.tool_name,
            run_id=RunId(str(request.run_id)),
            args=dict(request.args),
            status=ToolRouteStatus.COMPLETED,
            policy_decision=PolicyDecision(allowed=True, reason="test"),
            payload=payload,
            events=[],
            source_mode=request.source_mode,
        )

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "1234 NW 15th St, Fort Lauderdale, FL 33311",
            "analysis_type": "zoning_research",
            "source_mode": "live",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert (
        data["artifacts"]["ordinance_search"]["fallback_source"] == "verified_dimensional_standard"
    )
    assert (
        data["artifacts"]["ordinance_search"]["authority_confidence"]
        == "indexed_official_reference"
    )
    underwriting_section = next(
        section
        for section in data["report"]["sections"]
        if section["section_id"] == "underwriting_summary"
    )
    assert (
        underwriting_section["zoning_support_summary"]["ordinance_source"]
        == "verified_dimensional_standard"
    )
    ordinance_evidence = [
        item
        for item in data["evidence_items"]
        if item["source_type"] in {"ordinance_text", "municode_section"}
    ]
    assert ordinance_evidence
    assert all("broward_county" not in str(item["source_url"]) for item in ordinance_evidence)


@pytest.mark.asyncio
async def test_deal_analysis_live_run_rejects_mismatched_live_municode_authority_for_municipal_parcel(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    async def _fake_tool_result(request) -> HarnessToolCallResult:
        if request.tool_name == "geocode_address":
            payload = {
                "status": "success",
                "result": {
                    "address": str(request.args["address"]),
                    "municipality": "Fort Lauderdale",
                    "county": "Broward",
                    "state": "FL",
                    "lat": 26.1224,
                    "lng": -80.1373,
                },
            }
        elif request.tool_name == "lookup_property_info":
            payload = {
                "status": "success",
                "result": {
                    "folio": "504205120010",
                    "address": "1234 NW 15th St, Fort Lauderdale, FL 33311",
                    "municipality": "Fort Lauderdale",
                    "county": "Broward",
                    "zoning_code": "RS-8",
                    "ordinance_district_code": "RS-8",
                    "zoning_description": "Residential Single Family/Low Medium Density",
                    "lot_size_sqft": 6500,
                    "living_units": 1,
                    "zoning_layer_url": "https://example.test/ftl-zoning",
                },
            }
        elif request.tool_name == "search_zoning_ordinance":
            payload = {"status": "success", "results": []}
        elif request.tool_name == "search_municode_live":
            payload = {
                "status": "success",
                "results": [
                    {
                        "section": "Sec. 39-10",
                        "section_id": "broward_rs_8",
                        "title": "Broward residential district standards",
                        "text": "RS-8 development standards for county residential districts.",
                        "zone_codes": ["RS-8"],
                        "citation": {
                            "url": "https://library.municode.com/fl/broward_county",
                            "jurisdiction": "Broward County",
                        },
                        "rules": {
                            "source": "municode_live_table",
                            "source_url": "https://library.municode.com/fl/broward_county",
                            "source_section_id": "broward_rs_8",
                            "district_code": "RS-8",
                            "max_height_ft": 35.0,
                            "requires_official_verification": True,
                            "authority_source_type": "municode_live_table",
                            "authority_resolution": "section_table_extract",
                            "authority_confidence": "official_live_preliminary_extract",
                            "authority_is_live": True,
                            "authority_is_official": True,
                            "authority_jurisdiction": "Broward County, FL",
                        },
                    }
                ],
                "authority_source_type": "municode_live_search",
                "authority_resolution": "municode_discovered_config",
                "authority_confidence": "official_live_search",
                "authority_is_live": True,
                "authority_is_official": True,
                "authority_jurisdiction": "Broward County, FL",
            }
        elif request.tool_name == "web_search":
            payload = {"status": "success", "results": []}
        else:
            payload = _live_tool_payload(request.tool_name, dict(request.args))
        return HarnessToolCallResult(
            ok=True,
            tool_call_id=ToolCallId(f"tool_call_{request.tool_name}"),
            tool_name=request.tool_name,
            run_id=RunId(str(request.run_id)),
            args=dict(request.args),
            status=ToolRouteStatus.COMPLETED,
            policy_decision=PolicyDecision(allowed=True, reason="test"),
            payload=payload,
            events=[],
            source_mode=request.source_mode,
        )

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "1234 NW 15th St, Fort Lauderdale, FL 33311",
            "analysis_type": "zoning_research",
            "source_mode": "live",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert (
        data["artifacts"]["ordinance_search"]["fallback_source"] == "verified_dimensional_standard"
    )
    assert data["artifacts"]["ordinance_search"]["authority_is_live"] is False
    underwriting_section = next(
        section
        for section in data["report"]["sections"]
        if section["section_id"] == "underwriting_summary"
    )
    assert (
        underwriting_section["zoning_support_summary"]["ordinance_source"]
        == "verified_dimensional_standard"
    )
    assert underwriting_section["zoning_support_summary"]["authority_is_live"] is False
    ordinance_evidence = [
        item
        for item in data["evidence_items"]
        if item["source_type"] in {"ordinance_text", "municode_section"}
    ]
    assert ordinance_evidence
    assert all("broward_county" not in str(item["source_url"]) for item in ordinance_evidence)


@pytest.mark.asyncio
async def test_deal_analysis_live_run_falls_back_to_staged_local_ordinance_context(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    async def _fake_tool_result(request) -> HarnessToolCallResult:
        if request.tool_name == "lookup_property_info":
            payload = {
                "status": "success",
                "result": {
                    "folio": "0131360600010",
                    "address": "1603 NW 7 AVE",
                    "municipality": "Miami",
                    "county": "Miami-Dade",
                    "zoning_code": "CI-HD",
                    "ordinance_district_code": "CI-HD",
                    "zoning_description": "",
                    "lot_size_sqft": 43560,
                    "living_units": 0,
                    "lat": 25.790642,
                    "lng": -80.20681,
                    "zoning_layer_url": "",
                },
            }
        elif request.tool_name in {"search_zoning_ordinance", "search_municode_live", "web_search"}:
            payload = {"status": "success", "results": []}
        else:
            payload = _live_tool_payload(request.tool_name, dict(request.args))
        return HarnessToolCallResult(
            ok=True,
            tool_call_id=ToolCallId(f"tool_call_{request.tool_name}"),
            tool_name=request.tool_name,
            run_id=RunId(str(request.run_id)),
            args=dict(request.args),
            status=ToolRouteStatus.COMPLETED,
            policy_decision=PolicyDecision(allowed=True, reason="test"),
            payload=payload,
            events=[],
            source_mode=request.source_mode,
        )

    monkeypatch.setattr("plotlot.harness.fixture_runs._tool_result", _fake_tool_result)

    response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "1600 NW 7th Ave, Miami, FL 33136",
            "analysis_type": "zoning_research",
            "source_mode": "live",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["artifacts"]["ordinance_search"]["fallback_source"] == "staged_dimensional_standard"
    assert data["artifacts"]["ordinance_search"]["authority_confidence"] == "staged_preliminary"
    assert data["artifacts"]["ordinance_search"]["authority_is_live"] is False
    assert any(
        "fell back to staged local zoning authority context" in warning
        for warning in data["artifacts"].get("warnings", [])
    )
    underwriting_section = next(
        section
        for section in data["report"]["sections"]
        if section["section_id"] == "underwriting_summary"
    )
    assert (
        underwriting_section["zoning_support_summary"]["ordinance_source"]
        == "staged_dimensional_standard"
    )
    assert (
        underwriting_section["zoning_support_summary"]["authority_confidence"]
        == "staged_preliminary"
    )
    assert underwriting_section["zoning_support_summary"]["requires_official_verification"] is True
    zoning_stage = next(
        stage for stage in data["pipeline_stages"] if stage["key"] == "zoning_evidence"
    )
    assert zoning_stage["status"] == "warning"


@pytest.mark.asyncio
async def test_harness_run_events_api_replays_persisted_fixture_run(client: AsyncClient) -> None:
    create_response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "example Broward fixture address",
            "analysis_type": "zoning_research",
            "source_mode": "fixture",
        },
    )
    run_id = create_response.json()["run_id"]

    events_response = await client.get(f"/api/v1/harness/runs/{run_id}/events")
    replay_response = await client.post(f"/api/v1/harness/runs/{run_id}/replay")

    assert events_response.status_code == 200
    event_types = [event["type"] for event in events_response.json()["events"]]
    assert event_types[0] == "run.created"
    assert "tool.completed" in event_types
    assert event_types[-1] == "run.completed"
    assert replay_response.status_code == 200
    assert replay_response.json()["event_count"] == len(event_types)


@pytest.mark.asyncio
async def test_harness_run_evidence_api_reads_persisted_fixture_evidence(
    client: AsyncClient,
) -> None:
    create_response = await client.post(
        "/api/v1/deal-analysis/run",
        json={
            "address": "example Miami-Dade fixture address",
            "analysis_type": "acquisition_memo",
            "source_mode": "fixture",
        },
    )
    run_id = create_response.json()["run_id"]

    evidence_response = await client.get(f"/api/v1/harness/runs/{run_id}/evidence")
    evidence_id = evidence_response.json()["evidence"][0]["evidence_id"]
    show_response = await client.get(f"/api/v1/evidence/{evidence_id}")

    assert evidence_response.status_code == 200
    assert evidence_id in create_response.json()["evidence_ids"]
    assert show_response.status_code == 200
    assert show_response.json()["freshness_status"] == "fixture"
    assert len(evidence_response.json()["evidence"]) >= 3


@pytest.mark.asyncio
async def test_harness_job_api_queues_and_worker_executes_fixture_run(
    client: AsyncClient,
) -> None:
    queued_response = await client.post(
        "/api/v1/harness/jobs",
        json={
            "address": "example Miami-Dade fixture address",
            "analysis_type": "acquisition_memo",
            "source_mode": "fixture",
        },
    )
    worker_response = await client.post("/api/v1/harness/jobs/run-next")
    job_id = queued_response.json()["job_id"]

    assert queued_response.status_code == 200
    assert queued_response.json()["status"] == "queued"
    assert worker_response.status_code == 200
    assert worker_response.json()["status"] == "completed"
    events_response = await client.get(f"/api/v1/harness/jobs/{job_id}/events")
    assert [event["type"] for event in events_response.json()["events"]][-2:] == [
        "job.started",
        "job.completed",
    ]


@pytest.mark.asyncio
async def test_harness_job_api_persists_configured_attempt_budget(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/harness/jobs",
        json={
            "address": "example retry budget API fixture address",
            "analysis_type": "acquisition_memo",
            "source_mode": "fixture",
            "max_attempts": 1,
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "queued"
    assert response.json()["max_attempts"] == 1


@pytest.mark.asyncio
async def test_residual_land_value_api_persists_calculation_for_run(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/deal-analysis/residual-land-value",
        json={
            "run_id": "run_fixture_api_calc",
            "input": {
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
        },
    )
    calculation_id = response.json()["calculation_id"]
    list_response = await client.get("/api/v1/harness/runs/run_fixture_api_calc/calculations")
    show_response = await client.get(f"/api/v1/calculations/{calculation_id}")

    assert response.status_code == 200
    assert response.json()["outputs"]["max_supportable_land_price"] == 195_000
    assert list_response.status_code == 200
    assert list_response.json()["calculations"][0]["calculation_id"] == calculation_id
    assert show_response.status_code == 200
    assert show_response.json()["calculation_id"] == calculation_id


@pytest.mark.asyncio
async def test_deal_analysis_run_persists_linked_analysis_run_when_context_is_provided(
    client: AsyncClient,
) -> None:
    from plotlot.storage.models import Analysis, Project, Site, Workspace

    session = FakeLifecycleSession()
    session._workspaces["ws_fixture"] = Workspace(id="ws_fixture", name="Workspace")  # type: ignore[arg-type]
    session._projects["prj_fixture"] = Project(  # type: ignore[arg-type]
        id="prj_fixture",
        workspace_id="ws_fixture",
        name="Project",
    )
    session._sites["site_fixture"] = Site(  # type: ignore[arg-type]
        id="site_fixture",
        project_id="prj_fixture",
        address="171 NE 209th Ter, Miami, FL 33179",
    )
    session._analyses["analysis_fixture"] = Analysis(  # type: ignore[arg-type]
        id="analysis_fixture",
        workspace_id="ws_fixture",
        project_id="prj_fixture",
        site_id="site_fixture",
        name="Acquisition analysis",
        skill_name="acquisition_memo",
    )

    with (
        patch("plotlot.api.harness.get_session", new=AsyncMock(return_value=session)),
        patch("plotlot.api.analyses.get_session", new=AsyncMock(return_value=session)),
    ):
        response = await client.post(
            "/api/v1/deal-analysis/run",
            json={
                "address": "example Miami-Dade fixture address",
                "analysisType": "acquisition_memo",
                "sourceMode": "fixture",
                "workspaceId": "ws_fixture",
                "projectId": "prj_fixture",
                "siteId": "site_fixture",
                "analysisId": "analysis_fixture",
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["analysis_run_id"] == payload["run_id"]
        assert payload["workspace_id"] == "ws_fixture"
        assert payload["project_id"] == "prj_fixture"
        assert payload["site_id"] == "site_fixture"
        assert payload["analysis_id"] == "analysis_fixture"

        run_response = await client.get(f"/api/v1/analysis-runs/{payload['analysis_run_id']}")
        assert run_response.status_code == 200
        analysis_run = run_response.json()
        assert analysis_run["analysis_id"] == "analysis_fixture"
        assert analysis_run["output_json"]["harness_run_id"] == payload["run_id"]
        assert analysis_run["output_json"]["pipeline_stages"][0]["key"] == "site_identification"


@pytest.mark.asyncio
async def test_deal_analysis_run_rejects_partial_workspace_context(
    client: AsyncClient,
) -> None:
    session = FakeLifecycleSession()

    with patch("plotlot.api.harness.get_session", new=AsyncMock(return_value=session)):
        response = await client.post(
            "/api/v1/deal-analysis/run",
            json={
                "address": "example Miami-Dade fixture address",
                "analysisType": "acquisition_memo",
                "sourceMode": "fixture",
                "projectId": "prj_fixture",
            },
        )

    assert response.status_code == 400
    assert "workspace_id and project_id are both required" in response.json()["detail"]
