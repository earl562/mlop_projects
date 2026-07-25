from __future__ import annotations

import json
from contextlib import contextmanager

import pytest

from plotlot.api.chat_harness_bridge import execute_full_harness_chat_tool
from plotlot.harness.fixture_runs import (
    FixtureDealRunResult,
    FixtureDealRunRequest,
    run_fixture_deal_analysis_async,
)
from plotlot.harness.run_store import LocalHarnessRunStore
from plotlot.harness.tool_call_store import LocalToolCallLedger
from plotlot.harness.tool_router import HarnessToolCallRequest, HarnessToolCallResult, ToolRouteStatus
from plotlot.harness.contracts import (
    PlotLotEvent,
    PlotLotEventSource,
    PlotLotEventStatus,
    PlotLotEventType,
    RunId,
    SourceMode,
    ToolCallId,
    WorkspaceId,
)
from plotlot.harness.contracts.base import EventId
from plotlot.land_use.models import ToolContext
from plotlot.land_use.models import PolicyDecision


class _RecordingSpan:
    def __init__(self) -> None:
        self.attributes: dict[str, str | int | float | bool] = {}

    def set_attribute(self, key: str, value: str | int | float | bool) -> None:
        self.attributes[key] = value


class _FakeRouter:
    def __init__(self) -> None:
        self.last_request: HarnessToolCallRequest | None = None

    async def call_async(self, request: HarnessToolCallRequest) -> HarnessToolCallResult:
        self.last_request = request
        return HarnessToolCallResult(
            ok=True,
            tool_call_id=ToolCallId("tool_call_fixture"),
            tool_name=request.tool_name,
            run_id=RunId(request.context.run_id),
            args=request.args,
            status=ToolRouteStatus.COMPLETED,
            policy_decision=PolicyDecision(allowed=True, reason="fixture"),
            payload={"results": [{"title": "Fixture result"}]},
            events=[
                PlotLotEvent(
                    event_id=EventId("evt_fixture"),
                    run_id=RunId(request.context.run_id),
                    workspace_id=WorkspaceId(request.context.workspace_id),
                    sequence=1,
                    type=PlotLotEventType.TOOL_COMPLETED,
                    payload={"tool_name": request.tool_name},
                    status=PlotLotEventStatus.COMPLETED,
                    source=PlotLotEventSource.TOOL,
                    created_at="2026-06-28T00:00:00Z",
                )
            ],
            evidence_ids=["ev_fixture"],
            source_mode=request.source_mode,
        )


@pytest.mark.asyncio
async def test_execute_full_harness_chat_tool_emits_trace_attributes(monkeypatch) -> None:
    span = _RecordingSpan()
    router = _FakeRouter()

    @contextmanager
    def _span_cm(*_args, **_kwargs):
        yield span

    monkeypatch.setattr("plotlot.api.chat_harness_bridge.start_otel_span", _span_cm)
    monkeypatch.setattr("plotlot.api.chat_harness_bridge.default_tool_router", lambda: router)

    payload = json.loads(
        await execute_full_harness_chat_tool(
            "web_search",
            {"query": "Miami zoning update"},
            context=None,
            session_id="sess_bridge_trace",
        )
    )

    assert payload["status"] == "success"
    assert payload["tool_name"] == "web_search"
    assert payload["evidence_ids"] == ["ev_fixture"]
    assert payload["source_mode"] == "fixture"
    assert router.last_request is not None
    assert router.last_request.source_mode == SourceMode.FIXTURE
    assert span.attributes["plotlot.chat.tool_name"] == "web_search"
    assert span.attributes["plotlot.chat.session_id"] == "sess_bridge_trace"
    assert span.attributes["plotlot.chat.run_id"] == "sess_bridge_trace"
    assert span.attributes["plotlot.chat.arg_count"] == 1
    assert span.attributes["plotlot.chat.ok"] is True
    assert span.attributes["plotlot.chat.status"] == "completed"
    assert span.attributes["plotlot.chat.evidence_count"] == 1


@pytest.mark.asyncio
async def test_execute_full_harness_chat_tool_uses_live_source_mode_when_context_allows_it(
    monkeypatch,
) -> None:
    router = _FakeRouter()

    monkeypatch.setattr("plotlot.api.chat_harness_bridge.default_tool_router", lambda: router)

    payload = json.loads(
        await execute_full_harness_chat_tool(
            "web_search",
            {"query": "Miami zoning update"},
            context=ToolContext(
                workspace_id="ws_fixture",
                actor_user_id="analyst_fixture",
                run_id="run_bridge_live",
                live_network_allowed=True,
            ),
            session_id="sess_bridge_live",
        )
    )

    assert payload["status"] == "success"
    assert payload["source_mode"] == "live"
    assert router.last_request is not None
    assert router.last_request.source_mode == SourceMode.LIVE


@pytest.mark.asyncio
async def test_execute_full_harness_chat_tool_uses_live_source_mode_for_property_lookup_when_context_allows_it(
    monkeypatch,
) -> None:
    router = _FakeRouter()

    monkeypatch.setattr("plotlot.api.chat_harness_bridge.default_tool_router", lambda: router)

    payload = json.loads(
        await execute_full_harness_chat_tool(
            "lookup_property_info",
            {
                "address": "45 NW 209 ST, Miami Gardens, FL 33169",
                "county": "Miami-Dade",
                "state": "FL",
            },
            context=ToolContext(
                workspace_id="ws_fixture",
                actor_user_id="analyst_fixture",
                run_id="run_bridge_property_live",
                live_network_allowed=True,
            ),
            session_id="sess_bridge_property_live",
        )
    )

    assert payload["status"] == "success"
    assert payload["source_mode"] == "live"
    assert router.last_request is not None
    assert router.last_request.tool_name == "lookup_property_info"
    assert router.last_request.source_mode == SourceMode.LIVE


@pytest.mark.asyncio
async def test_execute_full_harness_chat_tool_persists_tool_call_and_appends_run_events(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PLOTLOT_HARNESS_TOOL_CALL_STORE_PATH", str(tmp_path / "tool-calls.json"))
    monkeypatch.setenv("PLOTLOT_HARNESS_STORE_PATH", str(tmp_path / "runs.json"))
    run_store = LocalHarnessRunStore(tmp_path / "runs.json")
    result = (
        await run_fixture_deal_analysis_async(
            FixtureDealRunRequest(
                address="example persisted chat bridge address",
                analysis_type="acquisition_memo",
            )
        )
    ).model_copy(update={"run_id": RunId("sess_bridge_persist")})
    run_store.save_run(result)

    payload = json.loads(
        await execute_full_harness_chat_tool(
            "search_municode",
            {"jurisdiction": "miami", "query": "parking"},
            context=None,
            session_id="sess_bridge_persist",
        )
    )

    stored_calls = LocalToolCallLedger(tmp_path / "tool-calls.json").list_tool_calls(
        run_id="sess_bridge_persist"
    )
    stored_run = run_store.get_run(RunId("sess_bridge_persist"))

    assert payload["status"] == "success"
    assert len(stored_calls) == 1
    assert stored_calls[0].tool_name == "search_municode"
    assert len(stored_run.events) == len(result.events) + 4
    assert stored_run.events[-1].type == PlotLotEventType.TOOL_COMPLETED


@pytest.mark.asyncio
async def test_execute_full_harness_chat_tool_uses_shared_fixture_comps_handler() -> None:
    payload = json.loads(
        await execute_full_harness_chat_tool(
            "find_comparables",
            {
                "address": "example Miami-Dade fixture address",
                "county": "Miami-Dade",
                "municipality": "Miami",
                "state": "FL",
                "lat": 25.7617,
                "lng": -80.1918,
                "lot_size_sqft": 7500,
                "zoning_code": "T4-R",
            },
            context=ToolContext(
                workspace_id="ws_fixture",
                actor_user_id="chat_agent",
                run_id="run_bridge_comps",
            ),
            session_id="sess_bridge_comps",
        )
    )

    assert payload["status"] == "success"
    assert payload["tool_name"] == "find_comparables"
    assert payload["source_mode"] == "fixture"
    analysis = payload["payload"]["analysis"]
    assert analysis["estimated_land_value"] > 0
    assert analysis["comparables"]
    assert analysis["comparables"][0]["citation"]["jurisdiction"] == "Miami-Dade"


@pytest.mark.asyncio
async def test_execute_full_harness_chat_tool_uses_live_source_mode_for_comps_when_context_allows_it(
    monkeypatch,
) -> None:
    router = _FakeRouter()

    monkeypatch.setattr("plotlot.api.chat_harness_bridge.default_tool_router", lambda: router)

    payload = json.loads(
        await execute_full_harness_chat_tool(
            "find_comparables",
            {
                "address": "171 NE 209th Ter, Miami, FL 33179",
                "county": "Miami-Dade",
                "municipality": "Miami Gardens",
                "state": "FL",
                "lat": 25.968392,
                "lng": -80.198728,
                "lot_size_sqft": 7500,
                "zoning_code": "R-1",
            },
            context=ToolContext(
                workspace_id="ws_live",
                actor_user_id="chat_agent",
                run_id="run_bridge_live_comps",
                live_network_allowed=True,
            ),
            session_id="sess_bridge_live_comps",
        )
    )

    assert payload["status"] == "success"
    assert payload["source_mode"] == "live"
    assert router.last_request is not None
    assert router.last_request.source_mode == SourceMode.LIVE


@pytest.mark.asyncio
async def test_execute_full_harness_chat_tool_uses_live_source_mode_for_gis_context_when_context_allows_it(
    monkeypatch,
) -> None:
    router = _FakeRouter()

    monkeypatch.setattr("plotlot.api.chat_harness_bridge.default_tool_router", lambda: router)

    payload = json.loads(
        await execute_full_harness_chat_tool(
            "resolve_site_boundary_context",
            {"county": "Broward", "municipality": "Fort Lauderdale"},
            context=ToolContext(
                workspace_id="ws_live",
                actor_user_id="chat_agent",
                run_id="run_bridge_live_gis",
                live_network_allowed=True,
            ),
            session_id="sess_bridge_live_gis",
        )
    )

    assert payload["status"] == "success"
    assert payload["source_mode"] == "live"
    assert router.last_request is not None
    assert router.last_request.tool_name == "resolve_site_boundary_context"
    assert router.last_request.source_mode == SourceMode.LIVE


@pytest.mark.asyncio
async def test_execute_full_harness_chat_tool_runs_shared_deal_analysis_with_live_context(
    monkeypatch,
) -> None:
    base_result = await run_fixture_deal_analysis_async(
        FixtureDealRunRequest(
            address="example Miami-Dade fixture address",
            analysis_type="acquisition_memo",
        )
    )
    fake_result = FixtureDealRunResult.model_validate(
        base_result.model_dump(mode="json")
        | {
            "analysis_type": "acquisition_memo",
            "source_mode": SourceMode.LIVE.value,
        }
    )

    async def _fake_run(_request: FixtureDealRunRequest) -> FixtureDealRunResult:
        assert _request.address == "171 NE 209th Ter, Miami, FL 33179"
        assert _request.analysis_type == "acquisition_memo"
        assert _request.source_mode == SourceMode.LIVE
        return fake_result

    monkeypatch.setattr("plotlot.api.chat_harness_bridge.run_deal_analysis_async", _fake_run)

    payload = json.loads(
        await execute_full_harness_chat_tool(
            "run_deal_analysis",
            {
                "address": "171 NE 209th Ter, Miami, FL 33179",
                "analysisType": "acquisition_memo",
            },
            context=ToolContext(
                workspace_id="ws_fixture",
                actor_user_id="chat_agent",
                run_id="run_bridge_analysis",
                live_network_allowed=True,
            ),
            session_id="sess_bridge_analysis",
        )
    )

    assert payload["status"] == "success"
    assert payload["tool_name"] == "run_deal_analysis"
    assert payload["source_mode"] == "live"
    assert payload["payload"]["analysis_type"] == "acquisition_memo"
    assert payload["active_analysis"]["analysis_origin"] == "harness_run"
    assert payload["active_analysis"]["address"] == "example Miami-Dade fixture address"
    assert payload["active_analysis"]["by_right"]["max_units"] is not None
    assert payload["active_analysis"]["valuation"]["public_listing_land_comp_count"] == 0
    assert payload["active_analysis"]["valuation"]["public_listing_signal_tier"] is None


@pytest.mark.asyncio
async def test_compact_harness_active_analysis_surfaces_harness_comp_trust_fields(
    monkeypatch,
) -> None:
    base_result = await run_fixture_deal_analysis_async(
        FixtureDealRunRequest(
            address="example Miami-Dade fixture address",
            analysis_type="acquisition_memo",
        )
    )
    base_payload = base_result.model_dump(mode="json")
    artifacts = dict(base_payload["artifacts"])
    artifacts["acquisition_guidance"] = {
        "recommended_action": "insufficient_support",
        "recommended_offer": 0.0,
        "requires_market_signal_validation": True,
        "recommendation_confidence": "low",
    }
    artifacts["comp_search_strategy"] = {
        "public_listing_signal_tier": "contextual_verified",
        "land_signal_tier": "contextual_public_listing",
        "public_listing_micro_market_confidence": "medium",
        "exit_support_market_scope": "subject_zip",
        "exit_micro_market_confidence": "high",
    }
    artifacts["comps"] = {
        "adv_per_unit": 699000.0,
        "adv_source": "comps",
        "estimated_land_value_low": 150000.0,
        "estimated_land_value_high": 165000.0,
        "public_listing_land_comparables": [
            {
                "address": "17605 NW 19th Avenue, Miami Gardens, FL 33056",
                "verification_status": "contextual_verified",
            }
        ],
    }
    fake_result = FixtureDealRunResult.model_validate(base_payload | {"artifacts": artifacts})

    async def _fake_run(_request: FixtureDealRunRequest) -> FixtureDealRunResult:
        return fake_result

    monkeypatch.setattr("plotlot.api.chat_harness_bridge.run_deal_analysis_async", _fake_run)

    payload = json.loads(
        await execute_full_harness_chat_tool(
            "run_deal_analysis",
            {
                "address": "171 NE 209th Ter, Miami, FL 33179",
                "analysisType": "acquisition_memo",
            },
            context=ToolContext(
                workspace_id="ws_fixture",
                actor_user_id="chat_agent",
                run_id="run_bridge_analysis_trust",
                live_network_allowed=True,
            ),
            session_id="sess_bridge_analysis_trust",
        )
    )

    valuation = payload["active_analysis"]["valuation"]
    assert valuation["recommended_action"] == "insufficient_support"
    assert valuation["recommended_offer"] == 0.0
    assert valuation["requires_market_signal_validation"] is True
    assert valuation["recommendation_confidence"] == "low"
    assert valuation["public_listing_signal_tier"] == "contextual_verified"
    assert valuation["land_signal_tier"] == "contextual_public_listing"
    assert valuation["land_micro_market_confidence"] == "medium"
    assert valuation["exit_support_market_scope"] == "subject_zip"
    assert valuation["exit_micro_market_confidence"] == "high"


@pytest.mark.asyncio
async def test_execute_full_harness_chat_tool_forces_fixture_mode_when_live_not_allowed(
    monkeypatch,
) -> None:
    base_result = await run_fixture_deal_analysis_async(
        FixtureDealRunRequest(
            address="example Miami-Dade fixture address",
            analysis_type="zoning_research",
        )
    )
    fake_result = FixtureDealRunResult.model_validate(base_result.model_dump(mode="json"))

    async def _fake_run(_request: FixtureDealRunRequest) -> FixtureDealRunResult:
        assert _request.source_mode == SourceMode.FIXTURE
        return fake_result

    monkeypatch.setattr("plotlot.api.chat_harness_bridge.run_deal_analysis_async", _fake_run)

    payload = json.loads(
        await execute_full_harness_chat_tool(
            "run_deal_analysis",
            {
                "address": "171 NE 209th Ter, Miami, FL 33179",
                "analysisType": "zoning_research",
                "sourceMode": "live",
            },
            context=ToolContext(
                workspace_id="ws_fixture",
                actor_user_id="chat_agent",
                run_id="run_bridge_analysis_fixture",
                live_network_allowed=False,
            ),
            session_id="sess_bridge_analysis_fixture",
        )
    )

    assert payload["status"] == "success"
    assert payload["source_mode"] == "fixture"
