from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from plotlot.api.chat_harness_tool_specs import FULL_HARNESS_CHAT_TOOL_NAMES, FULL_HARNESS_CHAT_TOOLS
from plotlot.domain.types import ToolContext
from plotlot.harness.contracts import ExecutionMode, JsonObject, SourceMode
from plotlot.harness.fixture_runs import FixtureDealRunRequest, run_deal_analysis_async
from plotlot.harness.run_persistence import (
    default_fixture_run_persistence_stores,
    persist_fixture_run_result,
)
from plotlot.harness.run_store import HarnessRunNotFoundError, default_harness_run_store
from plotlot.harness.tool_call_store import default_tool_call_ledger, tool_call_from_result
from plotlot.harness.tool_router import HarnessToolCallRequest, HarnessToolCallResult, default_tool_router
from plotlot.observability.tracing import start_otel_span

JsonObjectAdapter = TypeAdapter(JsonObject)

__all__ = [
    "FULL_HARNESS_CHAT_TOOL_NAMES",
    "FULL_HARNESS_CHAT_TOOLS",
    "execute_full_harness_chat_tool",
]


class ChatDealAnalysisArgs(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    address: str = Field(min_length=3)
    analysis_type: str = Field(
        default="acquisition_memo",
        min_length=1,
        validation_alias="analysisType",
    )
    source_mode: SourceMode | None = Field(
        default=None,
        validation_alias="sourceMode",
    )
    assumptions: JsonObject = Field(default_factory=dict)


async def execute_full_harness_chat_tool(
    tool_name: str,
    args: JsonObject,
    *,
    context: ToolContext | None,
    session_id: str,
) -> str:
    resolved_context = context or _default_context(session_id)
    if tool_name == "run_deal_analysis":
        return await _execute_chat_deal_analysis(
            JsonObjectAdapter.validate_python(args),
            context=resolved_context,
            session_id=session_id,
        )
    request = HarnessToolCallRequest(
        tool_name=tool_name,
        args=JsonObjectAdapter.validate_python(args),
        context=resolved_context,
        source_mode=_source_mode_for_chat_tool(tool_name, resolved_context),
        execution_mode=ExecutionMode.API,
    )
    with start_otel_span(
        "plotlot.api.chat_harness_tool",
        attributes={
            "plotlot.chat.tool_name": tool_name,
            "plotlot.chat.session_id": session_id,
            "plotlot.chat.run_id": resolved_context.run_id,
            "plotlot.chat.arg_count": len(request.args),
        },
    ) as span:
        span.set_attribute("plotlot.chat.tool_name", tool_name)
        span.set_attribute("plotlot.chat.session_id", session_id)
        span.set_attribute("plotlot.chat.run_id", resolved_context.run_id)
        span.set_attribute("plotlot.chat.arg_count", len(request.args))
        result = await default_tool_router().call_async(request)
        span.set_attribute("plotlot.chat.ok", result.ok)
        span.set_attribute("plotlot.chat.status", result.status.value)
        span.set_attribute("plotlot.chat.evidence_count", len(result.evidence_ids))
    _persist_chat_tool_result(result)
    return json.dumps(_chat_payload(result))


def _default_context(session_id: str) -> ToolContext:
    return ToolContext(
        workspace_id="default-workspace",
        actor_user_id="chat_agent",
        run_id=session_id or "chat_tool",
        live_network_allowed=False,
    )


def _source_mode_for_chat_tool(tool_name: str, context: ToolContext) -> SourceMode:
    if tool_name in {
        "geocode_address",
        "lookup_property_info",
        "search_zoning_ordinance",
        "search_municode_live",
        "search_south_florida_gis",
        "get_gis_source_metadata",
        "query_gis_feature_service",
        "resolve_site_boundary_context",
        "discover_open_data_layers",
        "find_comparables",
        "load_rental_market_evidence",
        "load_underwriting_market_profile",
        "web_search",
        "fetch_web_contents",
    } and context.live_network_allowed:
        return SourceMode.LIVE
    return SourceMode.FIXTURE


async def _execute_chat_deal_analysis(
    args: JsonObject,
    *,
    context: ToolContext,
    session_id: str,
) -> str:
    request_args = ChatDealAnalysisArgs.model_validate(args)
    source_mode = _analysis_source_mode(request_args.source_mode, context)
    run_request = FixtureDealRunRequest(
        address=request_args.address,
        analysis_type=request_args.analysis_type,
        source_mode=source_mode,
        execution_mode=ExecutionMode.API,
        assumptions=request_args.assumptions,
    )
    with start_otel_span(
        "plotlot.api.chat_harness_run",
        attributes={
            "plotlot.chat.tool_name": "run_deal_analysis",
            "plotlot.chat.session_id": session_id,
            "plotlot.chat.run_id": context.run_id,
            "plotlot.chat.analysis_type": request_args.analysis_type,
            "plotlot.chat.source_mode": source_mode.value,
        },
    ) as span:
        result = await run_deal_analysis_async(run_request)
        span.set_attribute("plotlot.chat.ok", result.status == "completed")
        span.set_attribute("plotlot.chat.status", result.status)
        span.set_attribute("plotlot.chat.evidence_count", len(result.evidence_ids))
    persist_fixture_run_result(
        result,
        default_fixture_run_persistence_stores(),
    )
    return json.dumps(
        JsonObjectAdapter.validate_python(
            {
                "status": "success" if result.status == "completed" else result.status,
                "ok": result.status == "completed",
                "tool_name": "run_deal_analysis",
                "run_id": str(result.run_id),
                "analysis_type": result.analysis_type,
                "source_mode": result.source_mode.value,
                "payload": result.model_dump(mode="json"),
                "active_analysis": compact_harness_active_analysis(result.model_dump(mode="json")),
                "events": [event.model_dump(mode="json") for event in result.events],
                "evidence_ids": result.evidence_ids,
                "warnings": result.artifacts.get("warnings", []),
            }
        )
    )


def _analysis_source_mode(requested_mode: SourceMode | None, context: ToolContext) -> SourceMode:
    if requested_mode is SourceMode.LIVE and context.live_network_allowed:
        return SourceMode.LIVE
    if requested_mode is SourceMode.LIVE:
        return SourceMode.FIXTURE
    if requested_mode is SourceMode.FIXTURE:
        return SourceMode.FIXTURE
    if context.live_network_allowed:
        return SourceMode.LIVE
    return SourceMode.FIXTURE


def compact_harness_active_analysis(payload: JsonObject) -> JsonObject | None:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict):
        return None
    property_record = artifacts.get("property_record")
    if not isinstance(property_record, dict):
        return None
    feasibility = artifacts.get("feasibility")
    comps = artifacts.get("comps")
    residual = artifacts.get("residual_land_value")
    acquisition_guidance = artifacts.get("acquisition_guidance")
    comp_search_strategy = artifacts.get("comp_search_strategy")
    underwriting_profile = artifacts.get("underwriting_market_profile")
    warnings = artifacts.get("warnings", [])
    compact_payload: JsonObject = {
        "status": "success",
        "analysis_origin": "harness_run",
        "address": str(property_record.get("address") or payload.get("address") or ""),
        "zoning_code": str(property_record.get("zoning_code") or ""),
        "zoning_description": str(property_record.get("zoning_description") or ""),
        "lot_size_sqft": property_record.get("lot_size_sqft"),
        "county": str(property_record.get("county") or ""),
        "municipality": str(property_record.get("municipality") or ""),
        "source_mode": payload.get("source_mode"),
        "verification_status": payload.get("verification_status"),
        "preliminary": payload.get("preliminary"),
        "report_id": payload.get("report_id"),
        "evidence_ids": payload.get("evidence_ids", []),
        "warnings": warnings if isinstance(warnings, list) else [],
    }
    if isinstance(feasibility, dict):
        compact_payload["by_right"] = {
            "max_units": feasibility.get("estimated_units"),
            "governing_constraint": ", ".join(feasibility.get("major_constraints", []))
            if isinstance(feasibility.get("major_constraints"), list)
            else "",
            "verification": payload.get("verification_status"),
        }
    if isinstance(comps, dict) or isinstance(residual, dict) or isinstance(acquisition_guidance, dict):
        public_listing_land_comparables = (
            comps.get("public_listing_land_comparables")
            if isinstance(comps, dict) and isinstance(comps.get("public_listing_land_comparables"), list)
            else []
        )
        compact_payload["valuation"] = {
            "adv_per_unit": comps.get("adv_per_unit") if isinstance(comps, dict) else None,
            "adv_source": comps.get("adv_source") if isinstance(comps, dict) else None,
            "land_value_range": [
                comps.get("estimated_land_value_low"),
                comps.get("estimated_land_value_high"),
            ]
            if isinstance(comps, dict)
            else None,
            "max_land_price_residual": residual.get("max_supportable_land_price")
            if isinstance(residual, dict)
            else None,
            "recommended_offer": acquisition_guidance.get("recommended_offer")
            if isinstance(acquisition_guidance, dict)
            else None,
            "recommended_action": acquisition_guidance.get("recommended_action")
            if isinstance(acquisition_guidance, dict)
            else None,
            "requires_market_signal_validation": acquisition_guidance.get("requires_market_signal_validation")
            if isinstance(acquisition_guidance, dict)
            else None,
            "recommendation_confidence": acquisition_guidance.get("recommendation_confidence")
            if isinstance(acquisition_guidance, dict)
            else None,
            "market": underwriting_profile.get("market")
            if isinstance(underwriting_profile, dict)
            else None,
            "public_listing_land_comp_count": len(public_listing_land_comparables),
            "public_listing_signal_tier": comp_search_strategy.get("public_listing_signal_tier")
            if isinstance(comp_search_strategy, dict)
            else (
                public_listing_land_comparables[0].get("verification_status")
                if public_listing_land_comparables and isinstance(public_listing_land_comparables[0], dict)
                else None
            ),
            "land_signal_tier": comp_search_strategy.get("land_signal_tier")
            if isinstance(comp_search_strategy, dict)
            else None,
            "land_micro_market_confidence": comp_search_strategy.get("public_listing_micro_market_confidence")
            if isinstance(comp_search_strategy, dict)
            else None,
            "exit_support_market_scope": comp_search_strategy.get("exit_support_market_scope")
            if isinstance(comp_search_strategy, dict)
            else None,
            "exit_micro_market_confidence": comp_search_strategy.get("exit_micro_market_confidence")
            if isinstance(comp_search_strategy, dict)
            else None,
        }
    return compact_payload


def _persist_chat_tool_result(result: HarnessToolCallResult) -> None:
    default_tool_call_ledger().save_tool_call(tool_call_from_result(result))
    try:
        default_harness_run_store().append_events(result.run_id, result.events)
    except HarnessRunNotFoundError:
        return


def _chat_payload(result: HarnessToolCallResult) -> JsonObject:
    payload = JsonObjectAdapter.validate_python(
        {
            "status": "success" if result.ok else result.status.value,
            "ok": result.ok,
            "tool_name": result.tool_name,
            "tool_call_id": str(result.tool_call_id),
            "harness_status": result.status.value,
            "run_id": str(result.run_id),
            "source_mode": result.source_mode.value,
            "policy_decision": result.policy_decision.model_dump(mode="json"),
            "payload": result.payload,
            "events": [event.model_dump(mode="json") for event in result.events],
            "evidence_ids": result.evidence_ids,
            "warnings": result.warnings,
        }
    )
    if result.error is not None:
        payload["error"] = result.error.model_dump(mode="json")
    return payload
