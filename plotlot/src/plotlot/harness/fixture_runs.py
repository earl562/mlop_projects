from __future__ import annotations

import anyio
import re
from math import floor
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING
from urllib.parse import urlparse
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field

from plotlot.domain.dimensional_standard import DistrictDimensionalStandard
from plotlot.domain.types import ToolContext
from plotlot.harness.calculation_runner import (
    build_calculation_result,
    execute_underwriting_calculation,
)
from plotlot.harness.comping_workflow import build_comping_workflow_artifact
from plotlot.harness.contracts import (
    ApplicabilityStatus,
    CalculationResult,
    Claim,
    ClaimFreshnessStatus,
    ClaimId,
    ClaimKind,
    ClaimOrigin,
    ClaimStatus,
    CountyName,
    EvidenceId,
    EvidenceItem,
    EvidenceSourceType,
    ExecutionMode,
    FreshnessStatus,
    JsonObject,
    PlotLotEvent,
    PlotLotEventSource,
    PlotLotEventStatus,
    PlotLotEventType,
    Report,
    ReportId,
    ReportStatus,
    ReportType,
    RunId,
    SourceMode,
    ToolCall,
)
from plotlot.harness.fixture_site_data import (
    FixtureSiteProfile,
    fixture_property_record,
    fixture_site_profile_for_address,
)
from plotlot.harness.pipeline_stages import (
    PipelineStageSummary,
    build_pipeline_stage_artifacts,
    build_pipeline_stages,
)
from plotlot.harness.verification import verify_report_traceability
from plotlot.harness.municode_source import (
    create_municode_evidence,
    get_municode_section,
)
from plotlot.harness.south_florida_gis import resolve_site_boundary_context
from plotlot.harness.parcel_geometry import derive_lot_dimensions_from_parcel_geometry
from plotlot.harness.exit_comp_support import best_exit_comp_snapshot
from plotlot.harness.evaluation_readiness import assess_live_evaluation_readiness
from plotlot.harness.comparable_listing_search import rank_listing_candidates
from plotlot.harness.listing_comp_support import (
    contextual_fit_score,
    lot_size_variance_ratio,
    parse_iso_date,
)
from plotlot.harness.listing_comp_verification import build_contextual_land_listing_verification
from plotlot.pipeline.calculator import parse_lot_dimensions
from plotlot.storage.dimensional_standards import (
    get_dimensional_standard,
    get_dimensional_standard_from_fixture,
)

if TYPE_CHECKING:
    from plotlot.harness.tool_router import HarnessToolCallResult


class FixtureDealRunRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    address: str = Field(min_length=3)
    analysis_type: str = Field(min_length=1)
    source_mode: SourceMode = SourceMode.FIXTURE
    execution_mode: ExecutionMode = ExecutionMode.API
    assumptions: JsonObject = Field(default_factory=dict)
    workspace_id: str | None = None
    project_id: str | None = None
    site_id: str | None = None
    analysis_id: str | None = None


class FixtureDealRunResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: RunId
    analysis_run_id: str | None = None
    workspace_id: str | None = None
    project_id: str | None = None
    site_id: str | None = None
    analysis_id: str | None = None
    analysis_type: str
    status: str
    events_url: str
    report_id: str
    evidence_ids: list[str]
    verification_status: str
    source_mode: SourceMode
    preliminary: bool
    events: list[PlotLotEvent]
    evidence_items: list[EvidenceItem] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    calculations: list[CalculationResult] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    report: Report | None = None
    artifacts: JsonObject = Field(default_factory=dict)
    pipeline_stages: list[PipelineStageSummary] = Field(default_factory=list)


@dataclass(frozen=True)
class LiveFeasibilityResolution:
    inputs: JsonObject
    warning: str | None = None


@dataclass(frozen=True)
class LiveProFormaResolution:
    inputs: JsonObject | None
    warning: str | None = None


@dataclass(frozen=True)
class LiveNoiResolution:
    inputs: JsonObject | None
    warning: str | None = None


@dataclass(frozen=True)
class LiveComparableStrategyResolution:
    payload: JsonObject
    attempts: list[JsonObject]


@dataclass(frozen=True)
class CountyReconciliationCandidate:
    listed_address: str
    listed_sale_price: float
    listed_sale_date: str
    listed_lot_size_sqft: float
    county_address: str
    county_sale_price: float
    county_sale_date: str
    county_lot_size_sqft: float


@dataclass(frozen=True)
class LiveUnderwritingStrategy:
    mode: str
    reason: str


LIVE_READ_TOOL_RISK_BUDGET_CENTS = 10_000


def run_deal_analysis(request: FixtureDealRunRequest) -> FixtureDealRunResult:
    return anyio.run(run_deal_analysis_async, request)


async def run_deal_analysis_async(request: FixtureDealRunRequest) -> FixtureDealRunResult:
    if request.source_mode is SourceMode.FIXTURE:
        return await run_fixture_deal_analysis_async(request)
    return await _run_live_deal_analysis_async(request)


def run_fixture_deal_analysis(request: FixtureDealRunRequest) -> FixtureDealRunResult:
    return anyio.run(run_fixture_deal_analysis_async, request)


async def run_fixture_deal_analysis_async(request: FixtureDealRunRequest) -> FixtureDealRunResult:
    run_id = fixture_run_id_for_address(request.address)
    normalized_analysis = request.analysis_type.replace("-", "_")
    profile = fixture_site_profile_for_address(request.address)
    report_id = ReportId(f"report_{run_id}")
    tool_context = ToolContext(
        workspace_id="workspace_fixture",
        actor_user_id=request.execution_mode.value,
        run_id=str(run_id),
        project_id=f"project_{profile.key}",
        site_id=f"site_{profile.key}",
    )

    events = [
        _event(
            run_id=run_id,
            sequence=1,
            event_type=PlotLotEventType.RUN_CREATED,
            source=_event_source_for_execution_mode(request.execution_mode),
            source_mode=request.source_mode,
            execution_mode=request.execution_mode,
            payload={"analysis_type": normalized_analysis, "address": request.address},
        ),
        _event(
            run_id=run_id,
            sequence=2,
            event_type=PlotLotEventType.SKILL_SELECTED,
            source=PlotLotEventSource.HARNESS,
            source_mode=request.source_mode,
            execution_mode=request.execution_mode,
            payload={"skill_name": normalized_analysis},
        ),
        _event(
            run_id=run_id,
            sequence=3,
            event_type=PlotLotEventType.RUN_STARTED,
            source=PlotLotEventSource.HARNESS,
            source_mode=request.source_mode,
            execution_mode=request.execution_mode,
            payload={"analysis_type": normalized_analysis},
        ),
    ]

    tool_calls: list[ToolCall] = []
    calculations: list[CalculationResult] = []
    evidence_items: list[EvidenceItem] = []
    artifacts: JsonObject = {
        "site": {
            "address": request.address,
            "municipality": profile.municipality,
            "county": profile.county,
            "state": profile.state,
            "zoning_code": profile.zoning_code,
            "lot_size_sqft": profile.lot_size_sqft,
        }
    }

    geocode_call = await _tool_result(
        request=ToolExecutionRequest(
            run_id=run_id,
            tool_name="geocode_address",
            args={"address": request.address},
            execution_mode=request.execution_mode,
            source_mode=request.source_mode,
            context=tool_context,
        )
    )
    _append_tool_result(events=events, tool_calls=tool_calls, result=geocode_call)
    geocode_payload = geocode_call.payload.get("result", {})
    if isinstance(geocode_payload, dict):
        artifacts["geocode"] = geocode_payload

    property_call = await _tool_result(
        request=ToolExecutionRequest(
            run_id=run_id,
            tool_name="lookup_property_info",
            args={
                "address": request.address,
                "county": profile.county,
                "state": profile.state,
                "lat": profile.lat,
                "lng": profile.lng,
            },
            execution_mode=request.execution_mode,
            source_mode=request.source_mode,
            context=tool_context,
        )
    )
    _append_tool_result(events=events, tool_calls=tool_calls, result=property_call)
    property_payload = _required_dict(property_call.payload, "result")
    artifacts["property_record"] = property_payload
    evidence_items.append(
        _property_evidence(
            run_id=run_id,
            profile=profile,
            property_payload=property_payload,
            requested_address=request.address,
        )
    )
    artifacts["site"] = {
        "address": str(property_payload.get("address") or request.address),
        "municipality": str(property_payload.get("municipality") or profile.municipality),
        "county": str(property_payload.get("county") or profile.county),
        "state": str(property_payload.get("state") or profile.state),
        "zoning_code": str(property_payload.get("zoning_code") or profile.zoning_code),
        "lot_size_sqft": float(property_payload.get("lot_size_sqft") or profile.lot_size_sqft),
    }

    gis_call = await _tool_result(
        request=ToolExecutionRequest(
            run_id=run_id,
            tool_name="search_south_florida_gis",
            args={"query": profile.gis_query, "county": profile.county},
            execution_mode=request.execution_mode,
            source_mode=request.source_mode,
            context=tool_context,
        )
    )
    _append_tool_result(events=events, tool_calls=tool_calls, result=gis_call)
    gis_results = _required_list(gis_call.payload, "results")
    selected_gis = gis_results[0] if gis_results else {}
    if isinstance(selected_gis, dict):
        artifacts["gis_source"] = selected_gis
        evidence_items.append(
            _gis_source_evidence(run_id=run_id, profile=profile, source_payload=selected_gis)
        )

    section_id = ""
    rule_payload: JsonObject = {}
    municode_call = await _tool_result(
        request=ToolExecutionRequest(
            run_id=run_id,
            tool_name="search_municode",
            args={"jurisdiction": profile.municode_jurisdiction, "query": "parking"},
            execution_mode=request.execution_mode,
            source_mode=request.source_mode,
            context=tool_context,
        )
    )
    _append_tool_result(events=events, tool_calls=tool_calls, result=municode_call)
    municode_results = _required_list(municode_call.payload, "results")
    if municode_results:
        selected_section = municode_results[0]
        if isinstance(selected_section, dict):
            section_id = str(selected_section.get("section_id", ""))
            artifacts["municode_search"] = selected_section
    if section_id:
        section = get_municode_section(section_id, source_mode=request.source_mode)
        evidence_items.append(create_municode_evidence(section, run_id=str(run_id)))
        section_call = await _tool_result(
            request=ToolExecutionRequest(
                run_id=run_id,
                tool_name="get_municode_section",
                args={"section_id": section_id},
                execution_mode=request.execution_mode,
                source_mode=request.source_mode,
                context=tool_context,
            )
        )
        _append_tool_result(events=events, tool_calls=tool_calls, result=section_call)
        rule_call = await _tool_result(
            request=ToolExecutionRequest(
                run_id=run_id,
                tool_name="extract_ordinance_rules",
                args={"section_id": section_id},
                execution_mode=request.execution_mode,
                source_mode=request.source_mode,
                context=tool_context,
            )
        )
        _append_tool_result(events=events, tool_calls=tool_calls, result=rule_call)
        rule_payload = rule_call.payload
        artifacts["ordinance_rules"] = rule_payload

    match normalized_analysis:
        case "zoning_research":
            claims = _zoning_claims(
                run_id=run_id,
                report_id=report_id,
                profile=profile,
                evidence_items=evidence_items,
            )
            report = _build_report(
                report_id=report_id,
                run_id=run_id,
                analysis_type=normalized_analysis,
                claims=claims,
                evidence_items=evidence_items,
                calculations=[],
                source_mode=request.source_mode,
                underwriting_mode=_required_dict(artifacts, "underwriting_mode"),
                artifacts=artifacts,
            )
        case "comparable_comping":
            comp_call = await _tool_result(
                request=ToolExecutionRequest(
                    run_id=run_id,
                    tool_name="find_comparables",
                    args={
                        "address": request.address,
                        "county": str(property_payload.get("county") or profile.county),
                        "municipality": str(
                            property_payload.get("municipality") or profile.municipality
                        ),
                        "state": str(property_payload.get("state") or profile.state),
                        "lat": float(property_payload.get("lat") or profile.lat),
                        "lng": float(property_payload.get("lng") or profile.lng),
                        "lot_size_sqft": float(
                            property_payload.get("lot_size_sqft") or profile.lot_size_sqft
                        ),
                        "zoning_code": str(
                            property_payload.get("zoning_code") or profile.zoning_code
                        ),
                    },
                    execution_mode=request.execution_mode,
                    source_mode=request.source_mode,
                    context=tool_context,
                )
            )
            _append_tool_result(events=events, tool_calls=tool_calls, result=comp_call)
            comps_payload = _required_dict(comp_call.payload, "analysis")
            artifacts["comps"] = comps_payload
            artifacts["comping_workflow"] = build_comping_workflow_artifact(
                property_payload=property_payload,
                comps_payload=comps_payload,
                tool_calls=tool_calls,
                underwriting_status="blocked_until_underwriting_skill",
            )
            evidence_items.extend(
                _comp_evidence(run_id=run_id, profile=profile, comps_payload=comps_payload)
            )
            claims = _comping_claims(
                run_id=run_id,
                report_id=report_id,
                profile=profile,
                evidence_items=evidence_items,
                comp_payload=comps_payload,
            )
            report = _build_report(
                report_id=report_id,
                run_id=run_id,
                analysis_type=normalized_analysis,
                claims=claims,
                evidence_items=evidence_items,
                calculations=[],
                source_mode=request.source_mode,
                underwriting_mode=_required_dict(artifacts, "underwriting_mode"),
                artifacts=artifacts,
            )
        case "acquisition_memo" | "development_underwriting" | "lender_package":
            comp_call = await _tool_result(
                request=ToolExecutionRequest(
                    run_id=run_id,
                    tool_name="find_comparables",
                    args={
                        "address": request.address,
                        "county": profile.county,
                        "municipality": profile.municipality,
                        "state": profile.state,
                        "lat": profile.lat,
                        "lng": profile.lng,
                        "lot_size_sqft": profile.lot_size_sqft,
                        "zoning_code": profile.zoning_code,
                    },
                    execution_mode=request.execution_mode,
                    source_mode=request.source_mode,
                    context=tool_context,
                )
            )
            _append_tool_result(events=events, tool_calls=tool_calls, result=comp_call)
            comps_payload = _required_dict(comp_call.payload, "analysis")
            artifacts["comps"] = comps_payload
            artifacts["comping_workflow"] = build_comping_workflow_artifact(
                property_payload=property_payload,
                comps_payload=comps_payload,
                tool_calls=tool_calls,
                underwriting_status="available_to_underwriting",
            )
            evidence_items.extend(
                _comp_evidence(run_id=run_id, profile=profile, comps_payload=comps_payload)
            )

            feasibility_inputs = _feasibility_inputs(
                profile=profile, assumptions=request.assumptions
            )
            feasibility_call = await _tool_result(
                request=ToolExecutionRequest(
                    run_id=run_id,
                    tool_name="compute_feasibility",
                    args=feasibility_inputs,
                    execution_mode=request.execution_mode,
                    source_mode=request.source_mode,
                    context=tool_context,
                )
            )
            _append_tool_result(events=events, tool_calls=tool_calls, result=feasibility_call)
            feasibility_calc = _calculation_result(
                run_id=run_id,
                command="feasibility",
                inputs=feasibility_inputs,
            )
            calculations.append(feasibility_calc)
            artifacts["feasibility"] = feasibility_call.payload

            noi_inputs = _noi_inputs(profile=profile, assumptions=request.assumptions)
            noi_call = await _tool_result(
                request=ToolExecutionRequest(
                    run_id=run_id,
                    tool_name="run_noi_valuation",
                    args=noi_inputs,
                    execution_mode=request.execution_mode,
                    source_mode=request.source_mode,
                    context=tool_context,
                )
            )
            _append_tool_result(events=events, tool_calls=tool_calls, result=noi_call)
            noi_calc = _calculation_result(
                run_id=run_id,
                command="noi-valuation",
                inputs=noi_inputs,
            )
            calculations.append(noi_calc)
            artifacts["noi_valuation"] = noi_call.payload

            residual_inputs = _residual_inputs(
                profile=profile,
                assumptions=request.assumptions,
                as_built_value=float(noi_call.payload["as_built_value"]),
            )
            residual_call = await _tool_result(
                request=ToolExecutionRequest(
                    run_id=run_id,
                    tool_name="run_residual_land_value",
                    args=residual_inputs,
                    execution_mode=request.execution_mode,
                    source_mode=request.source_mode,
                    context=tool_context,
                )
            )
            _append_tool_result(events=events, tool_calls=tool_calls, result=residual_call)
            residual_calc = _calculation_result(
                run_id=run_id,
                command="residual-land-value",
                inputs=residual_inputs,
            )
            calculations.append(residual_calc)
            artifacts["residual_land_value"] = residual_call.payload

            claims = _acquisition_claims(
                run_id=run_id,
                report_id=report_id,
                profile=profile,
                evidence_items=evidence_items,
                calculations=calculations,
                comp_payload=comps_payload,
                residual_payload=residual_call.payload,
            )
            report = _build_report(
                report_id=report_id,
                run_id=run_id,
                analysis_type=normalized_analysis,
                claims=claims,
                evidence_items=evidence_items,
                calculations=calculations,
                source_mode=request.source_mode,
                underwriting_mode=_required_dict(artifacts, "underwriting_mode"),
                artifacts=artifacts,
            )
        case _:
            claims = _zoning_claims(
                run_id=run_id,
                report_id=report_id,
                profile=profile,
                evidence_items=evidence_items,
            )
            report = _build_report(
                report_id=report_id,
                run_id=run_id,
                analysis_type=normalized_analysis,
                claims=claims,
                evidence_items=evidence_items,
                calculations=[],
                source_mode=request.source_mode,
                underwriting_mode=_required_dict(artifacts, "underwriting_mode"),
                artifacts=artifacts,
            )

    events.append(
        _event(
            run_id=run_id,
            sequence=len(events) + 1,
            event_type=PlotLotEventType.REPORT_GENERATED,
            source=PlotLotEventSource.REPORT,
            source_mode=request.source_mode,
            execution_mode=request.execution_mode,
            payload={"report_id": str(report.report_id), "claim_count": len(claims)},
        )
    )
    events.append(
        _event(
            run_id=run_id,
            sequence=len(events) + 1,
            event_type=PlotLotEventType.VERIFICATION_COMPLETED,
            source=PlotLotEventSource.VERIFIER,
            source_mode=request.source_mode,
            execution_mode=request.execution_mode,
            payload={
                "report_id": str(report.report_id),
                "status": "blocked",
                "reason": "fixture evidence remains preliminary",
            },
        )
    )
    events.append(
        _event(
            run_id=run_id,
            sequence=len(events) + 1,
            event_type=PlotLotEventType.RUN_COMPLETED,
            source=PlotLotEventSource.HARNESS,
            source_mode=request.source_mode,
            execution_mode=request.execution_mode,
            payload={"report_id": str(report.report_id), "evidence_count": len(evidence_items)},
        )
    )

    pipeline_stages = build_pipeline_stages(artifacts, normalized_analysis)
    artifacts.update(build_pipeline_stage_artifacts(pipeline_stages))
    evidence_ids = [str(item.evidence_id) for item in evidence_items]
    return FixtureDealRunResult(
        run_id=run_id,
        analysis_type=normalized_analysis,
        status="completed",
        events_url=f"/api/v1/harness/runs/{run_id}/events",
        report_id=str(report.report_id),
        evidence_ids=evidence_ids,
        verification_status="passed_with_warnings",
        source_mode=request.source_mode,
        preliminary=True,
        events=events,
        evidence_items=evidence_items,
        claims=claims,
        calculations=calculations,
        tool_calls=tool_calls,
        report=report,
        artifacts=artifacts,
        pipeline_stages=pipeline_stages,
    )


async def _run_live_deal_analysis_async(request: FixtureDealRunRequest) -> FixtureDealRunResult:
    run_id = fixture_run_id_for_address(f"{request.source_mode.value}:{request.address}")
    normalized_analysis = request.analysis_type.replace("-", "_")
    report_id = ReportId(f"report_{run_id}")
    tool_context = ToolContext(
        workspace_id="workspace_live",
        actor_user_id=request.execution_mode.value,
        run_id=str(run_id),
        project_id="project_live",
        site_id="site_live",
        risk_budget_cents=LIVE_READ_TOOL_RISK_BUDGET_CENTS,
        live_network_allowed=True,
    )
    events = [
        _event(
            run_id=run_id,
            sequence=1,
            event_type=PlotLotEventType.RUN_CREATED,
            source=_event_source_for_execution_mode(request.execution_mode),
            source_mode=request.source_mode,
            execution_mode=request.execution_mode,
            payload={"analysis_type": normalized_analysis, "address": request.address},
        ),
        _event(
            run_id=run_id,
            sequence=2,
            event_type=PlotLotEventType.SKILL_SELECTED,
            source=PlotLotEventSource.HARNESS,
            source_mode=request.source_mode,
            execution_mode=request.execution_mode,
            payload={"skill_name": normalized_analysis},
        ),
        _event(
            run_id=run_id,
            sequence=3,
            event_type=PlotLotEventType.RUN_STARTED,
            source=PlotLotEventSource.HARNESS,
            source_mode=request.source_mode,
            execution_mode=request.execution_mode,
            payload={"analysis_type": normalized_analysis},
        ),
    ]
    tool_calls: list[ToolCall] = []
    calculations: list[CalculationResult] = []
    evidence_items: list[EvidenceItem] = []
    artifacts: JsonObject = {"warnings": []}

    geocode_call = await _tool_result(
        request=ToolExecutionRequest(
            run_id=run_id,
            tool_name="geocode_address",
            args={"address": request.address},
            execution_mode=request.execution_mode,
            source_mode=request.source_mode,
            context=tool_context,
        )
    )
    _append_tool_result(events=events, tool_calls=tool_calls, result=geocode_call)
    geocode_payload = _required_dict(geocode_call.payload, "result")
    artifacts["geocode"] = geocode_payload
    if not geocode_payload:
        return _failed_live_result(
            request=request,
            run_id=run_id,
            report_id=report_id,
            events=events,
            tool_calls=tool_calls,
            message="Geocoding did not return a usable result.",
            artifacts=artifacts,
        )

    county = str(geocode_payload.get("county") or "").strip()
    municipality = str(geocode_payload.get("municipality") or "").strip()
    state = str(geocode_payload.get("state") or "").strip()
    lat = geocode_payload.get("lat")
    lng = geocode_payload.get("lng")
    if not county or lat is None or lng is None:
        return _failed_live_result(
            request=request,
            run_id=run_id,
            report_id=report_id,
            events=events,
            tool_calls=tool_calls,
            message="Geocoding result is missing county or coordinates.",
            artifacts=artifacts,
        )

    property_call = await _tool_result(
        request=ToolExecutionRequest(
            run_id=run_id,
            tool_name="lookup_property_info",
            args={
                "address": request.address,
                "county": county,
                "state": state,
                "lat": lat,
                "lng": lng,
            },
            execution_mode=request.execution_mode,
            source_mode=request.source_mode,
            context=tool_context,
        )
    )
    _append_tool_result(events=events, tool_calls=tool_calls, result=property_call)
    property_payload = _required_dict(property_call.payload, "result")
    artifacts["property_record"] = property_payload
    artifacts["site"] = {
        "address": str(property_payload.get("address") or request.address),
        "municipality": str(property_payload.get("municipality") or municipality),
        "county": str(property_payload.get("county") or county),
        "state": state or "FL",
        "zoning_code": str(property_payload.get("zoning_code") or ""),
        "lot_size_sqft": float(property_payload.get("lot_size_sqft") or 0.0),
    }
    if not property_payload:
        return _failed_live_result(
            request=request,
            run_id=run_id,
            report_id=report_id,
            events=events,
            tool_calls=tool_calls,
            message="Property lookup did not return a usable parcel record.",
            artifacts=artifacts,
        )

    gis_site_context = _live_gis_site_context(
        property_payload=property_payload,
        source_mode=request.source_mode,
    )
    if gis_site_context:
        property_payload["gis_site_context"] = gis_site_context
        artifacts["gis_site_context"] = gis_site_context
        evidence_items.append(
            _live_gis_site_context_evidence(
                run_id=run_id,
                property_payload=property_payload,
                gis_site_context=gis_site_context,
                source_mode=request.source_mode,
            )
        )
        warning = str(gis_site_context.get("warning") or "").strip()
        if warning:
            _append_warning(artifacts, warning)

    evidence_items.append(
        _live_property_evidence(
            run_id=run_id,
            property_payload=property_payload,
            source_mode=request.source_mode,
        )
    )
    zoning_code = str(property_payload.get("zoning_code") or "").strip()
    if zoning_code:
        evidence_items.append(
            _live_zoning_record_evidence(
                run_id=run_id,
                property_payload=property_payload,
                source_mode=request.source_mode,
            )
        )

    ordinance_payload = await _resolve_live_ordinance_payload(
        run_id=run_id,
        request=request,
        context=tool_context,
        events=events,
        tool_calls=tool_calls,
        municipality=str(property_payload.get("municipality") or municipality),
        state=state,
        zoning_code=str(property_payload.get("ordinance_district_code") or zoning_code),
    )
    if ordinance_payload is not None:
        artifacts["ordinance_search"] = ordinance_payload
        ordinance_rules_payload = _live_ordinance_rules_payload(ordinance_payload)
        if ordinance_rules_payload is not None:
            artifacts["ordinance_rules"] = ordinance_rules_payload
        if str(ordinance_payload.get("fallback_source") or "") == "miami21_web_reference":
            _append_warning(
                artifacts,
                _preliminary_live_dimensional_standard_warning(
                    municipality=str(property_payload.get("municipality") or municipality),
                    district_code=str(
                        property_payload.get("ordinance_district_code") or zoning_code
                    ),
                ),
            )
        if bool(ordinance_payload.get("requires_official_verification")):
            _append_warning(
                artifacts,
                (
                    "Ordinance search fell back to staged local zoning authority context; "
                    "verify the current municipal code section before relying on entitlement conclusions."
                ),
            )
        ordinance_evidence = _live_ordinance_evidence(
            run_id=run_id,
            ordinance_payload=ordinance_payload,
            property_payload=property_payload,
            source_mode=request.source_mode,
        )
        if ordinance_evidence is not None:
            evidence_items.append(ordinance_evidence)
    else:
        _append_warning(
            artifacts, "No ordinance search result was available; zoning remains preliminary."
        )

    manual_dimensional_payload = _manual_dimensional_assumptions_payload(request.assumptions)
    if manual_dimensional_payload is not None:
        artifacts["manual_dimensional_standards"] = manual_dimensional_payload
        evidence_items.append(
            _live_manual_dimensional_evidence(
                run_id=run_id,
                property_payload=property_payload,
                manual_dimensional_payload=manual_dimensional_payload,
                source_mode=request.source_mode,
            )
        )

    claims: list[Claim] = []
    if normalized_analysis == "comparable_comping":
        property_municipality = str(property_payload.get("municipality") or municipality).strip()
        comp_resolution = await _run_live_comparable_strategy(
            run_id=run_id,
            request=request,
            context=tool_context,
            events=events,
            tool_calls=tool_calls,
            property_payload=property_payload,
            municipality=property_municipality,
            county=county,
            state=state or "FL",
            lat=float(lat),
            lng=float(lng),
            zoning_code=zoning_code,
        )
        comps_payload = _apply_manual_comp_overrides(
            property_payload=property_payload,
            assumptions=request.assumptions,
            comps_payload=comp_resolution.payload,
        )
        comps_payload = _normalize_web_listing_artifacts(comps_payload)
        comps_payload = await _merge_browser_listing_capture(
            run_id=run_id,
            request=request,
            context=tool_context,
            events=events,
            tool_calls=tool_calls,
            property_payload=property_payload,
            comps_payload=comps_payload,
        )
        contextual_land_verification = await _verify_contextual_web_land_candidates(
            run_id=run_id,
            request=request,
            context=tool_context,
            events=events,
            tool_calls=tool_calls,
            comps_payload=comps_payload,
            property_payload=property_payload,
        )
        if contextual_land_verification:
            artifacts["contextual_land_listing_verification"] = contextual_land_verification
            comps_payload["contextual_land_listing_verification"] = contextual_land_verification
            contextual_land_reconciliation = (
                await _reconcile_contextual_land_candidates_with_county_records(
                    run_id=run_id,
                    request=request,
                    context=tool_context,
                    events=events,
                    tool_calls=tool_calls,
                    property_payload=property_payload,
                    contextual_land_verification=contextual_land_verification,
                )
            )
            if contextual_land_reconciliation:
                artifacts["contextual_land_listing_reconciliation"] = contextual_land_reconciliation
                comps_payload["contextual_land_listing_reconciliation"] = (
                    contextual_land_reconciliation
                )
        comps_payload = _derive_public_listing_land_comp_artifacts(comps_payload)
        artifacts["comps"] = comps_payload
        artifacts["comp_search_strategy"] = _build_comp_search_strategy_summary(
            comps_payload=comps_payload,
            attempts=comp_resolution.attempts,
            property_payload=property_payload,
        )
        artifacts["comping_workflow"] = build_comping_workflow_artifact(
            property_payload=property_payload,
            comps_payload=comps_payload,
            tool_calls=tool_calls,
        )
        comp_evidence = _comp_evidence_from_subject(
            run_id=run_id,
            property_payload=property_payload,
            comps_payload=comps_payload,
            source_mode=request.source_mode,
        )
        evidence_items.extend(comp_evidence)
        if not _has_live_comp_signal(comps_payload=comps_payload, comp_evidence=comp_evidence):
            _append_warning(
                artifacts,
                "Comparable sales search did not return qualifying comps; underwriting remains blocked.",
            )
        artifacts["underwriting_mode"] = _underwriting_mode_payload(
            mode="comping_only",
            status="blocked",
            reason="Comparable comping skill stops before deal underwriting.",
            source_artifacts=["property_record", "comps", "comping_workflow"],
            pricing_source="manual_comps"
            if bool(comps_payload.get("manual_comp_override"))
            else "auto_comps",
        )
        claims = _live_zoning_claims(
            run_id=run_id,
            report_id=report_id,
            property_payload=property_payload,
            evidence_items=evidence_items,
            artifacts=artifacts,
            warnings=[str(item) for item in artifacts.get("warnings", []) if isinstance(item, str)],
        )
        claims.extend(
            _live_comping_claims(
                run_id=run_id,
                report_id=report_id,
                property_payload=property_payload,
                evidence_items=evidence_items,
                comp_payload=comps_payload,
                source_mode=request.source_mode,
            )
        )
    elif normalized_analysis in {"acquisition_memo", "development_underwriting", "lender_package"}:
        underwriting_profile_call = await _tool_result(
            request=ToolExecutionRequest(
                run_id=run_id,
                tool_name="load_underwriting_market_profile",
                args={
                    "state": state or "FL",
                    "county": county,
                    "municipality": str(property_payload.get("municipality") or municipality),
                    "assumptions": request.assumptions,
                },
                execution_mode=request.execution_mode,
                source_mode=request.source_mode,
                context=tool_context,
            )
        )
        _append_tool_result(events=events, tool_calls=tool_calls, result=underwriting_profile_call)
        underwriting_profile = _required_dict(underwriting_profile_call.payload, "profile")
        artifacts["underwriting_market_profile"] = underwriting_profile
        rental_market_evidence = _required_dict(
            underwriting_profile_call.payload,
            "rental_market_evidence",
        )
        if rental_market_evidence:
            artifacts["rental_market_evidence"] = rental_market_evidence

        property_municipality = str(property_payload.get("municipality") or municipality).strip()
        comp_resolution = await _run_live_comparable_strategy(
            run_id=run_id,
            request=request,
            context=tool_context,
            events=events,
            tool_calls=tool_calls,
            property_payload=property_payload,
            municipality=property_municipality,
            county=county,
            state=state or "FL",
            lat=float(lat),
            lng=float(lng),
            zoning_code=zoning_code,
        )
        comps_payload = _apply_manual_comp_overrides(
            property_payload=property_payload,
            assumptions=request.assumptions,
            comps_payload=comp_resolution.payload,
        )
        comps_payload = _normalize_web_listing_artifacts(comps_payload)
        comps_payload = await _merge_browser_listing_capture(
            run_id=run_id,
            request=request,
            context=tool_context,
            events=events,
            tool_calls=tool_calls,
            property_payload=property_payload,
            comps_payload=comps_payload,
        )
        contextual_land_verification = await _verify_contextual_web_land_candidates(
            run_id=run_id,
            request=request,
            context=tool_context,
            events=events,
            tool_calls=tool_calls,
            comps_payload=comps_payload,
            property_payload=property_payload,
        )
        if contextual_land_verification:
            artifacts["contextual_land_listing_verification"] = contextual_land_verification
            comps_payload["contextual_land_listing_verification"] = contextual_land_verification
            contextual_land_reconciliation = (
                await _reconcile_contextual_land_candidates_with_county_records(
                    run_id=run_id,
                    request=request,
                    context=tool_context,
                    events=events,
                    tool_calls=tool_calls,
                    property_payload=property_payload,
                    contextual_land_verification=contextual_land_verification,
                )
            )
            if contextual_land_reconciliation:
                artifacts["contextual_land_listing_reconciliation"] = contextual_land_reconciliation
                comps_payload["contextual_land_listing_reconciliation"] = (
                    contextual_land_reconciliation
                )
        comps_payload = _derive_public_listing_land_comp_artifacts(comps_payload)
        artifacts["comps"] = comps_payload
        artifacts["comp_search_strategy"] = _build_comp_search_strategy_summary(
            comps_payload=comps_payload,
            attempts=comp_resolution.attempts,
            property_payload=property_payload,
        )
        artifacts["comping_workflow"] = build_comping_workflow_artifact(
            property_payload=property_payload,
            comps_payload=comps_payload,
            tool_calls=tool_calls,
        )
        comping_gate_blocks_underwriting = _comping_workflow_blocks_underwriting(artifacts)
        comping_underwriting_status = _comping_workflow_underwriting_status(artifacts)
        if comping_gate_blocks_underwriting:
            blocker = _comping_underwriting_blocker(comping_underwriting_status)
            artifacts["underwriting_calculation_gate"] = {
                "status": "blocked",
                "reason": blocker,
                "source_artifact": "comping_workflow",
                "comping_underwriting_status": comping_underwriting_status,
            }
            _append_warning(artifacts, blocker)
        else:
            artifacts["underwriting_calculation_gate"] = {
                "status": "available",
                "reason": "Comping workflow has enough verified market support to run deterministic underwriting.",
                "source_artifact": "comping_workflow",
                "comping_underwriting_status": comping_underwriting_status,
            }
        if bool(comps_payload.get("manual_comp_override")):
            artifacts["manual_comparables"] = {
                "land_comp_count": len(_required_list(comps_payload, "comparables")),
                "exit_comp_count": len(_required_list(comps_payload, "unit_comparables")),
                "adv_source": comps_payload.get("adv_source", ""),
                "land_comp_quality": _land_comp_quality_summary(comps_payload),
                "unit_comp_quality": _unit_comp_quality_summary(comps_payload),
            }
        pricing_source = (
            "manual_comps" if bool(comps_payload.get("manual_comp_override")) else "auto_comps"
        )
        comp_evidence = _comp_evidence_from_subject(
            run_id=run_id,
            property_payload=property_payload,
            comps_payload=comps_payload,
            source_mode=request.source_mode,
        )
        evidence_items.extend(comp_evidence)
        if not _has_live_comp_signal(comps_payload=comps_payload, comp_evidence=comp_evidence):
            _append_warning(
                artifacts,
                "Comparable sales search did not return qualifying comps; market pricing remains preliminary.",
            )

        feasibility_resolution = await _live_feasibility_inputs(
            property_payload=property_payload,
            assumptions=request.assumptions,
            ordinance_rules=_required_dict(artifacts, "ordinance_rules"),
        )
        if feasibility_resolution is not None:
            if feasibility_resolution.warning:
                _append_warning(artifacts, feasibility_resolution.warning)
            feasibility_inputs = feasibility_resolution.inputs
            feasibility_call = await _tool_result(
                request=ToolExecutionRequest(
                    run_id=run_id,
                    tool_name="compute_feasibility",
                    args=feasibility_inputs,
                    execution_mode=request.execution_mode,
                    source_mode=request.source_mode,
                    context=tool_context,
                )
            )
            _append_tool_result(events=events, tool_calls=tool_calls, result=feasibility_call)
            calculations.append(
                _calculation_result(run_id=run_id, command="feasibility", inputs=feasibility_inputs)
            )
            artifacts["feasibility"] = feasibility_call.payload
        else:
            _append_warning(
                artifacts,
                "Feasibility calculation skipped: provide maxFar and maxUnits assumptions for a live zoning capacity study.",
            )

        pro_forma_resolution = (
            None
            if comping_gate_blocks_underwriting
            else _live_pro_forma_inputs(
                property_payload=property_payload,
                assumptions=request.assumptions,
                comps_payload=comps_payload,
                feasibility_payload=_required_dict(artifacts, "feasibility"),
                state=state or "FL",
                underwriting_profile=underwriting_profile,
            )
        )
        if pro_forma_resolution is not None and pro_forma_resolution.warning:
            _append_warning(artifacts, pro_forma_resolution.warning)
        if pro_forma_resolution is not None and pro_forma_resolution.inputs is not None:
            pro_forma_inputs = pro_forma_resolution.inputs
            pro_forma_call = await _tool_result(
                request=ToolExecutionRequest(
                    run_id=run_id,
                    tool_name="run_pro_forma",
                    args=pro_forma_inputs,
                    execution_mode=request.execution_mode,
                    source_mode=request.source_mode,
                    context=tool_context,
                )
            )
            _append_tool_result(events=events, tool_calls=tool_calls, result=pro_forma_call)
            calculations.append(
                _calculation_result(run_id=run_id, command="pro-forma", inputs=pro_forma_inputs)
            )
            artifacts["pro_forma"] = pro_forma_call.payload
            cost_assumptions = _live_cost_assumption_payload(
                property_payload=property_payload,
                underwriting_profile=underwriting_profile,
                pro_forma_payload=pro_forma_call.payload,
            )
            artifacts["cost_assumptions"] = cost_assumptions
            evidence_items.append(
                _live_cost_assumption_evidence(
                    run_id=run_id,
                    property_payload=property_payload,
                    cost_assumptions=cost_assumptions,
                    source_mode=request.source_mode,
                )
            )
            if bool(cost_assumptions.get("requires_official_verification")):
                _append_warning(
                    artifacts,
                    "Pro forma used national default cost assumptions because no county-specific model was available; verify hard costs, soft costs, impact fees, and exit pricing before relying on the max offer.",
                )
            artifacts["underwriting_mode"] = _underwriting_mode_payload(
                mode="sold_unit_exit",
                status="partial",
                reason="Run reached sold-unit pro forma pricing but not income-based underwriting.",
                source_artifacts=["pro_forma", "cost_assumptions"],
                pricing_source=pricing_source,
            )

        if "cost_assumptions" not in artifacts:
            cost_assumptions = _live_cost_assumption_payload(
                property_payload=property_payload,
                underwriting_profile=underwriting_profile,
                pro_forma_payload={},
            )
            if any(
                cost_assumptions.get(key) is not None
                for key in (
                    "construction_cost_psf",
                    "monthly_rent_per_unit",
                    "operating_expense_pct",
                    "cap_rate",
                )
            ):
                artifacts["cost_assumptions"] = cost_assumptions
                evidence_items.append(
                    _live_cost_assumption_evidence(
                        run_id=run_id,
                        property_payload=property_payload,
                        cost_assumptions=cost_assumptions,
                        source_mode=request.source_mode,
                    )
                )

        underwriting_strategy = (
            LiveUnderwritingStrategy(
                mode="blocked_by_comping_gate",
                reason="Comping workflow blocked offer-driving underwriting until market comps are verified.",
            )
            if comping_gate_blocks_underwriting
            else _select_live_underwriting_strategy(
                property_payload=property_payload,
                assumptions=request.assumptions,
                comps_payload=comps_payload,
                feasibility_payload=_required_dict(artifacts, "feasibility"),
            )
        )
        cost_assumptions = _required_dict(artifacts, "cost_assumptions")
        if underwriting_strategy.mode == "income_cap_rate" and bool(
            cost_assumptions.get("requires_income_assumption_verification")
        ):
            _append_warning(
                artifacts,
                "Income underwriting used market rent or cap-rate defaults from the shared cost model; confirm rent, vacancy, opex, and cap rate before relying on the income approach.",
            )
        if underwriting_strategy.mode == "blocked_by_comping_gate":
            artifacts["underwriting_mode"] = _underwriting_mode_payload(
                mode="blocked_by_comping_gate",
                status="blocked",
                reason=underwriting_strategy.reason,
                source_artifacts=["comping_workflow", "comp_search_strategy"],
                pricing_source=pricing_source,
            )
        elif underwriting_strategy.mode == "sold_unit_exit":
            if "pro_forma" in artifacts:
                artifacts["underwriting_mode"] = _underwriting_mode_payload(
                    mode="sold_unit_exit",
                    status="completed",
                    reason=underwriting_strategy.reason,
                    source_artifacts=["pro_forma", "cost_assumptions"],
                    pricing_source=pricing_source,
                )
            else:
                _append_warning(
                    artifacts,
                    "Sold-unit exit underwriting was selected, but pro forma pricing could not be completed because no qualified exit pricing signal was available.",
                )
                artifacts["underwriting_mode"] = _underwriting_mode_payload(
                    mode="sold_unit_exit",
                    status="warning",
                    reason="Run preferred sold-unit exit underwriting, but deterministic pro forma pricing inputs were incomplete.",
                    source_artifacts=["cost_assumptions"],
                    pricing_source=pricing_source,
                )
        else:
            noi_resolution = _live_noi_inputs(
                property_payload=property_payload,
                underwriting_profile=underwriting_profile,
                feasibility_payload=_required_dict(artifacts, "feasibility"),
            )
            if noi_resolution.warning:
                _append_warning(artifacts, noi_resolution.warning)
            if noi_resolution.inputs is not None:
                noi_inputs = noi_resolution.inputs
                noi_call = await _tool_result(
                    request=ToolExecutionRequest(
                        run_id=run_id,
                        tool_name="run_noi_valuation",
                        args=noi_inputs,
                        execution_mode=request.execution_mode,
                        source_mode=request.source_mode,
                        context=tool_context,
                    )
                )
                _append_tool_result(events=events, tool_calls=tool_calls, result=noi_call)
                calculations.append(
                    _calculation_result(
                        run_id=run_id,
                        command="noi-valuation",
                        inputs=noi_inputs,
                    )
                )
                artifacts["noi_valuation"] = noi_call.payload

                residual_inputs = _live_residual_inputs(
                    assumptions=request.assumptions,
                    noi_payload=noi_call.payload,
                )
                if residual_inputs is not None:
                    residual_call = await _tool_result(
                        request=ToolExecutionRequest(
                            run_id=run_id,
                            tool_name="run_residual_land_value",
                            args=residual_inputs,
                            execution_mode=request.execution_mode,
                            source_mode=request.source_mode,
                            context=tool_context,
                        )
                    )
                    _append_tool_result(events=events, tool_calls=tool_calls, result=residual_call)
                    calculations.append(
                        _calculation_result(
                            run_id=run_id,
                            command="residual-land-value",
                            inputs=residual_inputs,
                        )
                    )
                    artifacts["residual_land_value"] = residual_call.payload
                    artifacts["underwriting_mode"] = _underwriting_mode_payload(
                        mode="income_cap_rate",
                        status="completed",
                        reason="Run completed income-based NOI and residual land value underwriting.",
                        source_artifacts=[
                            "noi_valuation",
                            "residual_land_value",
                            "cost_assumptions",
                        ],
                        pricing_source=pricing_source,
                    )
                else:
                    _append_warning(
                        artifacts,
                        "Residual land value calculation skipped: provide cost and profit assumptions for live underwriting.",
                    )
                    artifacts["underwriting_mode"] = _underwriting_mode_payload(
                        mode="income_cap_rate",
                        status="partial",
                        reason="Run completed NOI valuation but not residual land value underwriting.",
                        source_artifacts=["noi_valuation", "cost_assumptions"],
                        pricing_source=pricing_source,
                    )
            else:
                if "pro_forma" in artifacts:
                    _append_warning(
                        artifacts,
                        "Income-based NOI valuation was not available; the preliminary max offer uses sold-unit pro forma math instead of rent/cap-rate income.",
                    )
                    artifacts["underwriting_mode"] = _underwriting_mode_payload(
                        mode="sold_unit_exit",
                        status="partial",
                        reason="Run relied on sold-unit exit pricing because deterministic income inputs were unavailable.",
                        source_artifacts=["pro_forma", "cost_assumptions"],
                        pricing_source=pricing_source,
                    )
                else:
                    _append_warning(
                        artifacts,
                        "NOI valuation skipped: provide rent, operating expense, and cap rate assumptions for live underwriting.",
                    )
                    artifacts["underwriting_mode"] = _underwriting_mode_payload(
                        mode="missing_income_inputs",
                        status="warning",
                        reason="Run could not start income-based underwriting because rent, expense, or cap-rate inputs were missing.",
                        source_artifacts=[],
                        pricing_source=pricing_source,
                    )

        claims = _live_acquisition_claims(
            run_id=run_id,
            report_id=report_id,
            property_payload=property_payload,
            artifacts=artifacts,
            evidence_items=evidence_items,
            calculations=calculations,
            comps_payload=comps_payload,
            comp_evidence=comp_evidence,
            pro_forma_payload=_required_dict(artifacts, "pro_forma"),
            residual_payload=_required_dict(artifacts, "residual_land_value"),
            underwriting_mode=_required_dict(artifacts, "underwriting_mode"),
            warnings=[str(item) for item in artifacts.get("warnings", []) if isinstance(item, str)],
        )
        artifacts["acquisition_guidance"] = _build_live_acquisition_guidance(
            property_payload=property_payload,
            comps_payload=comps_payload,
            pro_forma_payload=_required_dict(artifacts, "pro_forma"),
            residual_payload=_required_dict(artifacts, "residual_land_value"),
            underwriting_mode=_required_dict(artifacts, "underwriting_mode"),
        )
    else:
        claims = _live_zoning_claims(
            run_id=run_id,
            report_id=report_id,
            property_payload=property_payload,
            evidence_items=evidence_items,
            artifacts=artifacts,
            warnings=[str(item) for item in artifacts.get("warnings", []) if isinstance(item, str)],
        )

    artifacts["evaluation_readiness"] = assess_live_evaluation_readiness(
        analysis_type=normalized_analysis,
        artifacts=artifacts,
    ).model_dump(mode="json")
    report = _build_report(
        report_id=report_id,
        run_id=run_id,
        analysis_type=normalized_analysis,
        claims=claims,
        evidence_items=evidence_items,
        calculations=calculations,
        source_mode=request.source_mode,
        underwriting_mode=_required_dict(artifacts, "underwriting_mode"),
        artifacts=artifacts,
    )
    verification = verify_report_traceability(report, claims, evidence_items)
    verification_status = _verification_status_label(verification)

    events.append(
        _event(
            run_id=run_id,
            sequence=len(events) + 1,
            event_type=PlotLotEventType.REPORT_GENERATED,
            source=PlotLotEventSource.REPORT,
            source_mode=request.source_mode,
            execution_mode=request.execution_mode,
            payload={"report_id": str(report.report_id), "claim_count": len(claims)},
        )
    )
    events.append(
        _event(
            run_id=run_id,
            sequence=len(events) + 1,
            event_type=PlotLotEventType.VERIFICATION_COMPLETED,
            source=PlotLotEventSource.VERIFIER,
            source_mode=request.source_mode,
            execution_mode=request.execution_mode,
            payload={
                "report_id": str(report.report_id),
                "status": verification.status.value,
                "checks": verification.checks,
            },
        )
    )
    events.append(
        _event(
            run_id=run_id,
            sequence=len(events) + 1,
            event_type=PlotLotEventType.RUN_COMPLETED,
            source=PlotLotEventSource.HARNESS,
            source_mode=request.source_mode,
            execution_mode=request.execution_mode,
            payload={"report_id": str(report.report_id), "evidence_count": len(evidence_items)},
        )
    )
    pipeline_stages = build_pipeline_stages(artifacts, normalized_analysis)
    artifacts.update(build_pipeline_stage_artifacts(pipeline_stages))
    return FixtureDealRunResult(
        run_id=run_id,
        analysis_type=normalized_analysis,
        status="completed",
        events_url=f"/api/v1/harness/runs/{run_id}/events",
        report_id=str(report.report_id),
        evidence_ids=[str(item.evidence_id) for item in evidence_items],
        verification_status=verification_status,
        source_mode=request.source_mode,
        preliminary=verification_status != "passed",
        events=events,
        evidence_items=evidence_items,
        claims=claims,
        calculations=calculations,
        tool_calls=tool_calls,
        report=report,
        artifacts=artifacts,
        pipeline_stages=pipeline_stages,
    )


def fixture_run_id_for_address(address: str) -> RunId:
    return RunId(f"run_fixture_{uuid5(NAMESPACE_URL, address).hex[:12]}")


def fixture_run_events(
    run_id: RunId,
    analysis_type: str,
    execution_mode: ExecutionMode,
) -> list[PlotLotEvent]:
    request = FixtureDealRunRequest(
        address=str(run_id),
        analysis_type=analysis_type,
        execution_mode=execution_mode,
    )
    return run_fixture_deal_analysis(request).events


class ToolExecutionRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: RunId
    tool_name: str = Field(min_length=1)
    args: JsonObject = Field(default_factory=dict)
    execution_mode: ExecutionMode
    source_mode: SourceMode
    context: ToolContext


async def _tool_result(request: ToolExecutionRequest) -> HarnessToolCallResult:
    from plotlot.harness.tool_router import HarnessToolCallRequest, default_tool_router

    return await default_tool_router().call_async(
        HarnessToolCallRequest(
            tool_name=request.tool_name,
            args=request.args,
            context=request.context,
            source_mode=request.source_mode,
            execution_mode=request.execution_mode,
        )
    )


def _append_tool_result(
    *,
    events: list[PlotLotEvent],
    tool_calls: list[ToolCall],
    result: HarnessToolCallResult,
) -> None:
    next_sequence = len(events) + 1
    for index, event in enumerate(result.events):
        events.append(
            event.model_copy(
                update={
                    "sequence": next_sequence + index,
                    "run_id": result.run_id,
                }
            )
        )
    tool_calls.append(_tool_call_from_result(result))


async def _run_live_comparable_strategy(
    *,
    run_id: RunId,
    request: FixtureDealRunRequest,
    context: ToolContext,
    events: list[PlotLotEvent],
    tool_calls: list[ToolCall],
    property_payload: JsonObject,
    municipality: str,
    county: str,
    state: str,
    lat: float,
    lng: float,
    zoning_code: str,
) -> LiveComparableStrategyResolution:
    search_plan: list[tuple[int, float]] = [(12, 3.0)]
    vacant_single_family_payload = _is_vacant_single_family_payload(property_payload)
    if vacant_single_family_payload:
        search_plan = [(6, 3.0), (12, 3.0), (24, 3.0), (24, 6.0)]

    attempts: list[JsonObject] = []
    attempt_payloads: list[JsonObject] = []
    selected_payload: JsonObject | None = None
    first_payload: JsonObject | None = None
    qualified_fallback_payload: JsonObject | None = None
    selected_attempt_index: int | None = None
    first_attempt_index: int | None = None
    qualified_fallback_attempt_index: int | None = None
    for months, radius_miles in search_plan:
        comp_call = await _tool_result(
            request=ToolExecutionRequest(
                run_id=run_id,
                tool_name="find_comparables",
                args={
                    "address": request.address,
                    "county": county,
                    "municipality": municipality,
                    "state": state,
                    "lat": lat,
                    "lng": lng,
                    "land_use_code": str(property_payload.get("land_use_code") or ""),
                    "land_use_description": str(property_payload.get("land_use_description") or ""),
                    "lot_size_sqft": float(property_payload.get("lot_size_sqft") or 0.0),
                    "living_units": int(property_payload.get("living_units") or 0),
                    "zoning_code": zoning_code,
                    "months": months,
                    "radius_miles": radius_miles,
                },
                execution_mode=request.execution_mode,
                source_mode=request.source_mode,
                context=context,
            )
        )
        _append_tool_result(events=events, tool_calls=tool_calls, result=comp_call)
        payload = _required_dict(comp_call.payload, "analysis")
        payload["subject_lot_size_sqft"] = float(property_payload.get("lot_size_sqft") or 0.0)
        attempt_payloads.append(payload)
        land_comp_quality = _land_comp_quality_summary(payload)
        unit_comp_quality = _unit_comp_quality_summary(payload)
        attempt = {
            "months": months,
            "radius_miles": radius_miles,
            "land_comp_count": len(_required_list(payload, "comparables")),
            "unit_comp_count": len(_required_list(payload, "unit_comparables")),
            "scored_land_comp_count": land_comp_quality["scored_land_comp_count"],
            "strong_land_comp_count": land_comp_quality["strong_land_comp_count"],
            "independent_land_comp_count": land_comp_quality["independent_land_comp_count"],
            "strong_independent_land_comp_count": land_comp_quality[
                "strong_independent_land_comp_count"
            ],
            "best_land_comp_fit_score": land_comp_quality["best_fit_score"],
            "best_land_comp_lot_size_variance_ratio": land_comp_quality[
                "best_fit_lot_size_variance_ratio"
            ],
            "best_land_comp_qualification_score": land_comp_quality["best_fit_qualification_score"],
            "direct_land_comp_signal": land_comp_quality["direct_land_comp_signal"],
            "scored_unit_comp_count": unit_comp_quality["scored_unit_comp_count"],
            "strong_unit_comp_count": unit_comp_quality["strong_unit_comp_count"],
            "best_exit_fit_score": unit_comp_quality["best_exit_fit_score"],
            "best_exit_price_variance_ratio": unit_comp_quality["best_exit_price_variance_ratio"],
            "best_exit_qualification_score": unit_comp_quality["best_exit_qualification_score"],
            "qualified_exit_comp_signal": unit_comp_quality["qualified_exit_comp_signal"],
            "estimated_land_value": payload.get("estimated_land_value", 0.0),
            "adv_per_unit": payload.get("adv_per_unit", 0.0),
            "confidence": payload.get("confidence", 0.0),
            "selected": False,
            "selection_reason": "not_selected",
        }
        attempts.append(attempt)
        if first_payload is None:
            first_payload = payload
            first_attempt_index = len(attempts) - 1
        if _has_direct_land_comp_signal(payload):
            attempt["selected"] = True
            attempt["selection_reason"] = "direct_land_comp_signal"
            selected_payload = payload
            selected_attempt_index = len(attempts) - 1
            break
        if qualified_fallback_payload is None and _has_qualified_live_unit_comp_signal(payload):
            qualified_fallback_payload = payload
            qualified_fallback_attempt_index = len(attempts) - 1
            attempt["selection_reason"] = "qualified_exit_comp_fallback_candidate"

    if selected_payload is None:
        if qualified_fallback_payload is not None:
            selected_payload = qualified_fallback_payload
            selected_attempt_index = qualified_fallback_attempt_index
        else:
            selected_payload = first_payload if first_payload is not None else {}
            selected_attempt_index = first_attempt_index
    if (
        vacant_single_family_payload
        and selected_payload is not None
        and not _has_direct_land_comp_signal(selected_payload)
    ):
        merged_payload = _merge_live_land_comp_payloads(
            primary_payload=selected_payload,
            attempt_payloads=attempt_payloads,
            subject_lot_size_sqft=float(property_payload.get("lot_size_sqft") or 0.0),
        )
        if _has_supported_relaxed_land_comp_signal(merged_payload):
            selected_payload = merged_payload
            if selected_attempt_index is not None and selected_attempt_index < len(attempts):
                attempts[selected_attempt_index]["selection_reason"] = (
                    "supported_relaxed_land_signal"
                )

    if selected_attempt_index is None and attempts:
        selected_attempt_index = len(attempts) - 1

    if selected_attempt_index is not None:
        for index, attempt in enumerate(attempts):
            attempt["selected"] = index == selected_attempt_index
            if index == selected_attempt_index and attempt["selection_reason"] == "not_selected":
                attempt["selection_reason"] = "unqualified_first_attempt"
            elif (
                index == selected_attempt_index
                and attempt["selection_reason"] == "qualified_exit_comp_fallback_candidate"
            ):
                attempt["selection_reason"] = "qualified_exit_comp_fallback"

    return LiveComparableStrategyResolution(payload=selected_payload, attempts=attempts)


async def _verify_contextual_web_land_candidates(
    *,
    run_id: RunId,
    request: FixtureDealRunRequest,
    context: ToolContext,
    events: list[PlotLotEvent],
    tool_calls: list[ToolCall],
    comps_payload: JsonObject,
    property_payload: JsonObject,
) -> JsonObject | None:
    if _has_direct_land_comp_signal(comps_payload):
        return None
    web_listing_candidates = comps_payload.get("web_listing_candidates")
    if not isinstance(web_listing_candidates, list):
        return None
    likely_land_urls = [
        str(candidate.get("url") or "").strip()
        for candidate in web_listing_candidates
        if isinstance(candidate, dict)
        and str(candidate.get("classification") or "unknown") == "likely_vacant_land"
        and str(candidate.get("url") or "").strip()
    ]
    if not likely_land_urls:
        return None
    content_call = await _tool_result(
        request=ToolExecutionRequest(
            run_id=run_id,
            tool_name="fetch_web_contents",
            args={"urls": likely_land_urls[:3]},
            execution_mode=request.execution_mode,
            source_mode=request.source_mode,
            context=context,
        )
    )
    _append_tool_result(events=events, tool_calls=tool_calls, result=content_call)
    fetched_results = _required_list(content_call.payload, "results")
    verification = build_contextual_land_listing_verification(
        candidates=[
            candidate for candidate in web_listing_candidates if isinstance(candidate, dict)
        ],
        fetched_results=[result for result in fetched_results if isinstance(result, dict)],
        subject_lot_area_sf=float(property_payload.get("lot_size_sqft") or 0.0),
        subject_municipality=str(property_payload.get("municipality") or ""),
        subject_address=request.address,
        reference_date_iso=datetime.now(timezone.utc).date().isoformat(),
    )
    if (
        int(verification.get("verified_candidate_count") or 0) <= 0
        and int(verification.get("reconciliation_candidate_count") or 0) <= 0
    ):
        return None
    return verification


async def _reconcile_contextual_land_candidates_with_county_records(
    *,
    run_id: RunId,
    request: FixtureDealRunRequest,
    context: ToolContext,
    events: list[PlotLotEvent],
    tool_calls: list[ToolCall],
    property_payload: JsonObject,
    contextual_land_verification: JsonObject,
) -> JsonObject | None:
    verified_candidates = contextual_land_verification.get("verified_candidates")
    reconciliation_candidates = contextual_land_verification.get("reconciliation_candidates")
    if not isinstance(verified_candidates, list) or not isinstance(reconciliation_candidates, list):
        return None
    county_candidates = [*verified_candidates, *reconciliation_candidates]

    reconciled_candidates: list[JsonObject] = []
    rejected_candidates: list[JsonObject] = []
    subject_lot_area_sf = float(property_payload.get("lot_size_sqft") or 0.0)
    for raw_candidate in _county_reconciliation_candidates(county_candidates):
        if not isinstance(raw_candidate, dict):
            continue
        candidate_address = str(
            raw_candidate.get("address_hint") or raw_candidate.get("title") or ""
        ).strip()
        if not candidate_address:
            continue
        geocode_call = await _tool_result(
            request=ToolExecutionRequest(
                run_id=run_id,
                tool_name="geocode_address",
                args={"address": candidate_address},
                execution_mode=request.execution_mode,
                source_mode=request.source_mode,
                context=context,
            )
        )
        _append_tool_result(events=events, tool_calls=tool_calls, result=geocode_call)
        geocode_payload = _required_dict(geocode_call.payload, "result")
        lat = geocode_payload.get("lat")
        lng = geocode_payload.get("lng")
        county = str(geocode_payload.get("county") or property_payload.get("county") or "").strip()
        if not isinstance(lat, int | float) or not isinstance(lng, int | float) or not county:
            rejected_candidates.append(
                _county_reconciliation_rejection(
                    raw_candidate=raw_candidate,
                    reason="candidate_geocode_missing_county_or_coordinates",
                )
            )
            continue
        property_call = await _tool_result(
            request=ToolExecutionRequest(
                run_id=run_id,
                tool_name="lookup_property_info",
                args={
                    "address": candidate_address,
                    "county": county,
                    "state": str(geocode_payload.get("state") or "FL"),
                    "lat": float(lat),
                    "lng": float(lng),
                },
                execution_mode=request.execution_mode,
                source_mode=request.source_mode,
                context=context,
            )
        )
        _append_tool_result(events=events, tool_calls=tool_calls, result=property_call)
        county_property = _required_dict(property_call.payload, "result")
        county_sale_price = county_property.get("last_sale_price")
        county_sale_date = str(county_property.get("last_sale_date") or "").strip()
        county_lot_size_sqft = county_property.get("lot_size_sqft")
        listed_sale_price = raw_candidate.get("sale_price")
        listed_sale_date = str(raw_candidate.get("sale_date") or "").strip()
        listed_lot_size_sqft = raw_candidate.get("lot_size_sqft")
        county_address = str(county_property.get("address") or "").strip()
        if not (
            isinstance(county_sale_price, int | float)
            and isinstance(county_lot_size_sqft, int | float)
        ):
            rejected_candidates.append(
                _county_reconciliation_rejection(
                    raw_candidate=raw_candidate,
                    reason="county_record_missing_sale_or_lot_facts",
                )
            )
            continue
        listing_sale_facts_complete = (
            isinstance(listed_sale_price, int | float)
            and float(listed_sale_price) > 0
            and isinstance(listed_lot_size_sqft, int | float)
            and float(listed_lot_size_sqft) > 0
            and bool(listed_sale_date)
        )
        if listing_sale_facts_complete:
            assert isinstance(listed_sale_price, int | float)
            assert isinstance(listed_lot_size_sqft, int | float)
            county_record_matches = _listing_candidate_matches_county_record(
                CountyReconciliationCandidate(
                    listed_address=candidate_address,
                    listed_sale_price=float(listed_sale_price),
                    listed_sale_date=listed_sale_date,
                    listed_lot_size_sqft=float(listed_lot_size_sqft),
                    county_address=county_address,
                    county_sale_price=float(county_sale_price),
                    county_sale_date=county_sale_date,
                    county_lot_size_sqft=float(county_lot_size_sqft),
                )
            )
            reconciliation_basis = "listing_facts_matched_county_record"
            county_sale_date_aligned = True
        else:
            county_record_matches = _listing_addresses_align(candidate_address, county_address)
            reconciliation_basis = "county_record_enriched"
            county_sale_date_aligned = False
        if not county_record_matches:
            rejected_candidates.append(
                _county_reconciliation_rejection(
                    raw_candidate=raw_candidate,
                    reason="candidate_listing_facts_do_not_match_county_record",
                )
            )
            continue
        county_price_per_acre = round(
            float(county_sale_price) / (float(county_lot_size_sqft) / 43_560.0),
            2,
        )
        reconciled_candidates.append(
            {
                **raw_candidate,
                "county_sale_price": float(county_sale_price),
                "county_sale_date": county_sale_date,
                "county_lot_size_sqft": float(county_lot_size_sqft),
                "county_price_per_acre": county_price_per_acre,
                "county_folio": county_property.get("folio"),
                "county_address": county_property.get("address"),
                "county_reconciled": True,
                "county_sale_date_aligned": county_sale_date_aligned,
                "listing_sale_facts_complete": listing_sale_facts_complete,
                "reconciliation_basis": reconciliation_basis,
            }
        )

    if subject_lot_area_sf <= 0:
        return _empty_county_reconciliation_result(
            verified_candidates=county_candidates,
            rejected_candidates=rejected_candidates,
            status="failed_subject_lot_area_missing",
        )
    if not reconciled_candidates:
        return _empty_county_reconciliation_result(
            verified_candidates=county_candidates,
            rejected_candidates=rejected_candidates,
            status="no_county_record_match",
        )
    pricing_candidates = _county_reconciled_pricing_candidates(reconciled_candidates)
    county_price_per_acre_values = sorted(
        float(candidate["county_price_per_acre"])
        for candidate in pricing_candidates
        if isinstance(candidate.get("county_price_per_acre"), int | float)
    )
    if not county_price_per_acre_values:
        return _empty_county_reconciliation_result(
            verified_candidates=county_candidates,
            rejected_candidates=rejected_candidates,
            status="failed_county_pricing_unavailable",
        )
    low_ppa = county_price_per_acre_values[0]
    high_ppa = county_price_per_acre_values[-1]
    median_ppa = county_price_per_acre_values[len(county_price_per_acre_values) // 2]
    subject_acres = subject_lot_area_sf / 43_560.0
    return {
        "status": "county_reconciled",
        "reconciled_candidate_count": len(reconciled_candidates),
        "reconciled_candidates": reconciled_candidates,
        "rejected_candidate_count": len(rejected_candidates),
        "rejected_candidates": rejected_candidates,
        "pricing_candidate_count": len(pricing_candidates),
        "pricing_market_scope": _county_reconciled_pricing_scope(pricing_candidates),
        "county_price_per_acre_low": round(low_ppa, 2),
        "county_price_per_acre_median": round(median_ppa, 2),
        "county_price_per_acre_high": round(high_ppa, 2),
        "county_estimated_land_value_low": round(low_ppa * subject_acres, 2),
        "county_estimated_land_value": round(median_ppa * subject_acres, 2),
        "county_estimated_land_value_high": round(high_ppa * subject_acres, 2),
    }


def _empty_county_reconciliation_result(
    *,
    verified_candidates: list[object],
    rejected_candidates: list[JsonObject],
    status: str,
) -> JsonObject:
    return {
        "status": status,
        "attempted_candidate_count": len(verified_candidates),
        "reconciled_candidate_count": 0,
        "reconciled_candidates": [],
        "rejected_candidate_count": len(rejected_candidates),
        "rejected_candidates": rejected_candidates,
        "pricing_candidate_count": 0,
        "pricing_market_scope": "none",
    }


def _county_reconciliation_rejection(*, raw_candidate: JsonObject, reason: str) -> JsonObject:
    return {
        "address": str(
            raw_candidate.get("address_hint") or raw_candidate.get("title") or ""
        ).strip(),
        "url": str(raw_candidate.get("url") or "").strip(),
        "reason": reason,
    }


def _listing_candidate_matches_county_record(candidate: CountyReconciliationCandidate) -> bool:
    if (
        candidate.listed_sale_price <= 0
        or candidate.listed_lot_size_sqft <= 0
        or candidate.county_sale_price <= 0
        or candidate.county_lot_size_sqft <= 0
    ):
        return False
    if (
        candidate.listed_address
        and candidate.county_address
        and not _listing_addresses_align(candidate.listed_address, candidate.county_address)
    ):
        return False
    if not _sale_dates_align(candidate.listed_sale_date, candidate.county_sale_date):
        return False
    sale_price_ratio = (
        abs(candidate.county_sale_price - candidate.listed_sale_price) / candidate.listed_sale_price
    )
    lot_size_ratio = (
        abs(candidate.county_lot_size_sqft - candidate.listed_lot_size_sqft)
        / candidate.listed_lot_size_sqft
    )
    return sale_price_ratio <= 0.1 and lot_size_ratio <= 0.2


def _sale_dates_align(listed_sale_date: str, county_sale_date: str) -> bool:
    listed_date = parse_iso_date(listed_sale_date)
    county_date = parse_iso_date(county_sale_date)
    if not isinstance(listed_date, date) or not isinstance(county_date, date):
        return False
    return abs((county_date - listed_date).days) <= 45


def _county_reconciliation_candidates(
    verified_candidates: list[JsonObject],
) -> list[JsonObject]:
    ranked_candidates = [
        candidate for candidate in verified_candidates if isinstance(candidate, dict)
    ]
    deduped_candidates: dict[str, JsonObject] = {}
    for candidate in ranked_candidates:
        dedupe_key = _county_reconciliation_dedupe_key(candidate)
        existing = deduped_candidates.get(dedupe_key)
        if existing is None or _county_reconciliation_sort_key(
            candidate
        ) < _county_reconciliation_sort_key(existing):
            deduped_candidates[dedupe_key] = candidate
    ranked = sorted(deduped_candidates.values(), key=_county_reconciliation_sort_key)
    return ranked[:3]


def _contextual_priced_candidate_count(verified_candidates: list[JsonObject]) -> int:
    return sum(
        1
        for candidate in verified_candidates
        if isinstance(candidate, dict)
        and not bool(candidate.get("county_reconciliation_required"))
        and isinstance(candidate.get("sale_price"), int | float)
        and float(candidate.get("sale_price") or 0.0) > 0
        and isinstance(candidate.get("lot_size_sqft"), int | float)
        and float(candidate.get("lot_size_sqft") or 0.0) > 0
        and bool(str(candidate.get("sale_date") or "").strip())
    )


def _county_reconciliation_dedupe_key(candidate: JsonObject) -> str:
    address_hint = (
        str(candidate.get("address_hint") or candidate.get("title") or "").strip().casefold()
    )
    return address_hint


def _county_reconciled_pricing_candidates(
    reconciled_candidates: list[JsonObject],
) -> list[JsonObject]:
    subject_zip_candidates = [
        candidate
        for candidate in reconciled_candidates
        if isinstance(candidate, dict) and candidate.get("zip_match") is True
    ]
    if subject_zip_candidates:
        return subject_zip_candidates
    subject_municipality_candidates = [
        candidate
        for candidate in reconciled_candidates
        if isinstance(candidate, dict) and candidate.get("municipality_match") is True
    ]
    if subject_municipality_candidates:
        return subject_municipality_candidates
    return reconciled_candidates


def _county_reconciled_pricing_scope(reconciled_candidates: list[JsonObject]) -> str:
    if not reconciled_candidates:
        return "unknown"
    if all(
        candidate.get("zip_match") is True
        for candidate in reconciled_candidates
        if isinstance(candidate, dict)
    ):
        return "subject_zip"
    if all(
        candidate.get("municipality_match") is True
        for candidate in reconciled_candidates
        if isinstance(candidate, dict)
    ):
        return "subject_municipality"
    return "mixed"


def _county_reconciliation_sort_key(candidate: JsonObject) -> tuple[object, ...]:
    return (
        candidate.get("zip_match") is not True,
        candidate.get("municipality_match") is not True,
        -float(candidate.get("fit_score") or 0.0),
        float(candidate.get("lot_size_variance_ratio") or 1.0),
        -float(candidate.get("parsing_confidence") or 0.0),
        -float(candidate.get("confidence") or 0.0),
        str(candidate.get("address_hint") or candidate.get("title") or ""),
    )


def _listing_addresses_align(listed_address: str, county_address: str) -> bool:
    listed_tokens = _normalized_address_tokens(listed_address)
    county_tokens = _normalized_address_tokens(county_address)
    if not listed_tokens or not county_tokens:
        return True
    listed_number = listed_tokens[0]
    county_number = county_tokens[0]
    if listed_number.isdigit() and county_number.isdigit() and listed_number != county_number:
        return False
    listed_semantic_tokens = _address_semantic_tokens(listed_tokens[1:])
    county_semantic_tokens = _address_semantic_tokens(county_tokens[1:])
    if not listed_semantic_tokens or not county_semantic_tokens:
        return True
    return len(listed_semantic_tokens & county_semantic_tokens) >= 2


def _normalized_address_tokens(value: str) -> list[str]:
    synonym_map = {
        "AVENUE": "AVE",
        "STREET": "ST",
        "TERRACE": "TER",
        "ROAD": "RD",
        "DRIVE": "DR",
        "BOULEVARD": "BLVD",
        "COURT": "CT",
        "LANE": "LN",
        "PLACE": "PL",
    }
    normalized = []
    for token in re.split(r"[^A-Za-z0-9]+", value.upper()):
        if not token:
            continue
        if token in {"FL", "MIAMI", "GARDENS", "FORT", "LAUDERDALE"}:
            continue
        normalized.append(_normalize_address_token(synonym_map.get(token, token)))
    return normalized


def _normalize_address_token(token: str) -> str:
    ordinal_match = re.fullmatch(r"([0-9]+)(ST|ND|RD|TH)", token)
    if ordinal_match is not None:
        return ordinal_match.group(1)
    return token


def _address_semantic_tokens(tokens: list[str]) -> set[str]:
    semantic_tokens: set[str] = set()
    for token in tokens:
        normalized = token.strip()
        if not normalized:
            continue
        if normalized.isdigit() and len(normalized) == 5:
            continue
        semantic_tokens.add(normalized)
    return semantic_tokens


def _apply_manual_comp_overrides(
    *,
    property_payload: JsonObject,
    assumptions: JsonObject,
    comps_payload: JsonObject,
) -> JsonObject:
    manual_land_comps = _manual_comp_entries(
        raw_value=assumptions.get("manualLandComps"),
        role="land",
    )
    manual_exit_comps = _manual_comp_entries(
        raw_value=assumptions.get("manualExitComps"),
        role="exit",
    )
    if not manual_land_comps and not manual_exit_comps:
        return comps_payload

    merged_payload = dict(comps_payload)
    notes = _string_list(merged_payload.get("notes"))

    if manual_land_comps:
        land_values = [
            comp["sale_price"] / comp["lot_size_sqft"]
            for comp in manual_land_comps
            if float(comp.get("lot_size_sqft") or 0.0) > 0
            and float(comp.get("sale_price") or 0.0) > 0
        ]
        subject_lot_area = float(property_payload.get("lot_size_sqft") or 0.0)
        merged_payload["comparables"] = manual_land_comps
        if land_values and subject_lot_area > 0:
            land_values_sorted = sorted(land_values)
            median_value = _median(land_values_sorted)
            low_value = _percentile_value(land_values_sorted, 0.25)
            high_value = _percentile_value(land_values_sorted, 0.75)
            merged_payload["estimated_land_value"] = round(median_value * subject_lot_area, 2)
            merged_payload["estimated_land_value_low"] = round(low_value * subject_lot_area, 2)
            merged_payload["estimated_land_value_high"] = round(high_value * subject_lot_area, 2)
        notes.append("Using user-supplied land comps for land value guidance.")

    if manual_exit_comps:
        unit_values = [
            comp["price_per_unit"]
            for comp in manual_exit_comps
            if isinstance(comp.get("price_per_unit"), int | float)
            and float(comp["price_per_unit"]) > 0
        ]
        merged_payload["unit_comparables"] = manual_exit_comps
        if unit_values:
            unit_values_sorted = sorted(float(value) for value in unit_values)
            merged_payload["adv_per_unit"] = round(_median(unit_values_sorted), 2)
            merged_payload["adv_per_unit_low"] = round(
                _percentile_value(unit_values_sorted, 0.25), 2
            )
            merged_payload["adv_per_unit_high"] = round(
                _percentile_value(unit_values_sorted, 0.75), 2
            )
            merged_payload["adv_source"] = "manual_comps"
        notes.append("Using user-supplied exit comps for finished-product pricing guidance.")

    merged_payload["confidence"] = max(
        float(merged_payload.get("confidence") or 0.0),
        0.85 if manual_land_comps and manual_exit_comps else 0.75,
    )
    merged_payload["notes"] = notes
    merged_payload["manual_comp_override"] = True
    return merged_payload


def _event(
    *,
    run_id: RunId,
    sequence: int,
    event_type: PlotLotEventType,
    source: PlotLotEventSource,
    source_mode: SourceMode,
    execution_mode: ExecutionMode,
    payload: JsonObject,
) -> PlotLotEvent:
    return PlotLotEvent(
        run_id=run_id,
        sequence=sequence,
        type=event_type,
        source=source,
        status=PlotLotEventStatus.COMPLETED,
        source_mode=source_mode,
        execution_mode=execution_mode,
        payload=payload,
        created_at=datetime.now(timezone.utc),
    )


def _property_evidence(
    *,
    run_id: RunId,
    profile: FixtureSiteProfile,
    property_payload: JsonObject | None = None,
    requested_address: str = "",
) -> EvidenceItem:
    property_record = fixture_property_record(profile)
    evidence_address = str(
        (property_payload or {}).get("address") or requested_address or property_record.address
    )
    evidence_municipality = str(
        (property_payload or {}).get("municipality")
        or property_record.municipality
        or profile.municipality
    )
    evidence_county = str(
        (property_payload or {}).get("county") or property_record.county or profile.county
    )
    evidence_zoning_code = str(
        (property_payload or {}).get("zoning_code")
        or property_record.zoning_code
        or profile.zoning_code
    )
    evidence_lot_size_sqft = float(
        (property_payload or {}).get("lot_size_sqft")
        or property_record.lot_size_sqft
        or profile.lot_size_sqft
    )
    evidence_folio = str((property_payload or {}).get("folio") or profile.folio)
    return EvidenceItem(
        evidence_id=EvidenceId(f"ev_{run_id}_parcel_record"),
        run_id=run_id,
        source_type=EvidenceSourceType.PARCEL_RECORD,
        source_name=f"{profile.county} parcel fixture",
        source_url=f"fixture://{profile.key}/parcel",
        source_identifier=evidence_folio,
        provider="fixture",
        jurisdiction=profile.county,
        county=CountyName(evidence_county),
        municipality=evidence_municipality,
        freshness_status=FreshnessStatus.FIXTURE,
        applicability=_municipal_applicability(profile),
        normalized_text=(
            f"{evidence_address} is mapped to zoning {evidence_zoning_code} with "
            f"{evidence_lot_size_sqft:.0f} square feet."
        ),
        structured_payload={
            "folio": evidence_folio,
            "address": evidence_address,
            "zoning_code": evidence_zoning_code,
            "lot_size_sqft": evidence_lot_size_sqft,
        },
        confidence=0.82,
        source_mode=SourceMode.FIXTURE,
        metadata={"fixture_profile": profile.key},
    )


def _gis_source_evidence(
    *,
    run_id: RunId,
    profile: FixtureSiteProfile,
    source_payload: JsonObject,
) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=EvidenceId(f"ev_{run_id}_gis_source"),
        run_id=run_id,
        source_type=EvidenceSourceType.GIS_LAYER,
        source_name=str(source_payload.get("dataset_name", "South Florida GIS fixture")),
        source_url=str(source_payload.get("source_url", "fixture://south-florida-gis")),
        source_identifier=str(source_payload.get("source_id", "gis_fixture")),
        provider=str(source_payload.get("provider", "fixture")),
        jurisdiction=profile.county,
        county=CountyName(profile.county),
        municipality=profile.municipality,
        freshness_status=FreshnessStatus.FIXTURE,
        applicability=_municipal_applicability(profile),
        normalized_text="Fixture GIS source selected for county zoning context.",
        structured_payload=source_payload,
        confidence=0.7,
        source_mode=SourceMode.FIXTURE,
        metadata={"fixture_profile": profile.key},
    )


def _comp_evidence(
    *,
    run_id: RunId,
    profile: FixtureSiteProfile,
    comps_payload: JsonObject,
) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    land_comp_quality = _land_comp_quality_summary(comps_payload)
    for comp_type in ("comparables", "unit_comparables"):
        raw_items = comps_payload.get(comp_type)
        if not isinstance(raw_items, list):
            continue
        for index, raw_item in enumerate(raw_items):
            if not isinstance(raw_item, dict):
                continue
            source_type = (
                EvidenceSourceType.RENTAL_COMP
                if comp_type == "unit_comparables"
                else EvidenceSourceType.MARKET_COMP
            )
            structured_payload: JsonObject = {"comp_type": comp_type, **raw_item}
            metadata: JsonObject = {
                "fixture_profile": profile.key,
                "land_comp_quality": land_comp_quality,
            }
            normalized_text = (
                f"{raw_item.get('address', 'Comparable sale')} sold for "
                f"{raw_item.get('sale_price', 0)} on {raw_item.get('sale_date', '')}."
            )
            metadata["comp_quality_status"] = (
                _unit_comp_quality_status(raw_item)
                if comp_type == "unit_comparables"
                else _land_comp_quality_status(raw_item)
            )
            metadata["manual_override_used"] = bool(comps_payload.get("manual_comp_override"))
            score = _comp_qualification_score(raw_item)
            if score is not None:
                structured_payload["qualification_score"] = score
                metadata["qualification_score"] = score
                normalized_text = f"{normalized_text} Qualification score {score:.3f}."
            items.append(
                EvidenceItem(
                    evidence_id=EvidenceId(f"ev_{run_id}_{comp_type}_{index + 1}"),
                    run_id=run_id,
                    source_type=source_type,
                    source_name=f"{profile.county} comparable sale",
                    source_url="fixture://market-comps",
                    source_identifier=str(raw_item.get("address", f"{comp_type}_{index + 1}")),
                    provider="fixture",
                    jurisdiction=profile.county,
                    county=CountyName(profile.county),
                    municipality=profile.municipality,
                    freshness_status=FreshnessStatus.FIXTURE,
                    applicability=_municipal_applicability(profile),
                    normalized_text=normalized_text,
                    structured_payload=structured_payload,
                    confidence=0.72,
                    source_mode=SourceMode.FIXTURE,
                    metadata=metadata,
                )
            )
    return items


def _feasibility_inputs(*, profile: FixtureSiteProfile, assumptions: JsonObject) -> JsonObject:
    inputs: JsonObject = {
        "lot_area_sf": profile.lot_size_sqft,
        "max_far": _float_assumption(assumptions, "maxFar", profile.max_far),
        "max_units": int(_float_assumption(assumptions, "maxUnits", profile.max_units)),
        "efficiency_factor": _float_assumption(
            assumptions,
            "efficiencyFactor",
            profile.efficiency_factor,
        ),
        "avg_unit_size_sf": _float_assumption(
            assumptions, "avgUnitSizeSf", profile.avg_unit_size_sf
        ),
        "parking_spaces_per_unit": profile.parking_spaces_per_unit,
    }
    for assumption_key, payload_key in (
        ("lotFrontageFt", "lot_frontage_ft"),
        ("lotDepthFt", "lot_depth_ft"),
        ("frontSetbackFt", "setback_front_ft"),
        ("sideSetbackFt", "setback_side_ft"),
        ("rearSetbackFt", "setback_rear_ft"),
        ("maxLotCoveragePct", "max_lot_coverage_pct"),
    ):
        value = _optional_float_assumption(assumptions, assumption_key)
        if value is not None:
            inputs[payload_key] = value
    return inputs


def _noi_inputs(*, profile: FixtureSiteProfile, assumptions: JsonObject) -> JsonObject:
    unit_count = int(_float_assumption(assumptions, "unitCount", profile.living_units))
    monthly_rent = _float_assumption(
        assumptions, "monthlyRentPerUnit", profile.monthly_rent_per_unit
    )
    vacancy = _float_assumption(assumptions, "vacancyPct", profile.vacancy_pct)
    operating_expense = _float_assumption(
        assumptions,
        "operatingExpensePct",
        profile.operating_expense_pct,
    )
    cap_rate = _float_assumption(assumptions, "capRate", profile.cap_rate)
    return {
        "unit_count": unit_count,
        "monthly_rent_per_unit": monthly_rent,
        "vacancy_pct": vacancy,
        "operating_expense_pct": operating_expense,
        "cap_rate": cap_rate,
    }


def _residual_inputs(
    *,
    profile: FixtureSiteProfile,
    assumptions: JsonObject,
    as_built_value: float,
) -> JsonObject:
    target_profit_pct = _float_assumption(assumptions, "targetProfitPct", 0.18)
    return {
        "as_built_value": as_built_value,
        "desired_profit": round(as_built_value * target_profit_pct, 2),
        "hard_costs": _float_assumption(assumptions, "hardCosts", profile.hard_costs),
        "soft_costs": _float_assumption(assumptions, "softCosts", profile.soft_costs),
        "contingency": _float_assumption(assumptions, "contingency", profile.contingency),
        "developer_fee": _float_assumption(assumptions, "developerFee", profile.developer_fee),
        "closing_costs": _float_assumption(assumptions, "closingCosts", profile.closing_costs),
        "financing_costs": _float_assumption(
            assumptions,
            "financingCosts",
            profile.financing_costs,
        ),
        "holding_costs": _float_assumption(assumptions, "holdingCosts", profile.holding_costs),
        "selling_costs": _float_assumption(assumptions, "sellingCosts", profile.selling_costs),
        "asking_price": _float_assumption(
            assumptions,
            "askingPrice",
            float(profile.market_value),
        ),
    }


def _calculation_result(*, run_id: RunId, command: str, inputs: JsonObject) -> CalculationResult:
    output = execute_underwriting_calculation(command, inputs)
    return build_calculation_result(run_id=run_id, inputs=inputs, output=output)


def _zoning_claims(
    *,
    run_id: RunId,
    report_id: ReportId,
    profile: FixtureSiteProfile,
    evidence_items: list[EvidenceItem],
) -> list[Claim]:
    evidence_ids = [item.evidence_id for item in evidence_items]
    return [
        Claim(
            claim_id=ClaimId(f"claim_{run_id}_zoning_code"),
            run_id=run_id,
            report_id=report_id,
            claim_text=(
                f"{profile.address} is currently treated as {profile.zoning_code} "
                f"({profile.zoning_description}) in this fixture harness run."
            ),
            claim_type="zoning_code",
            field_key="zoning.current_district",
            kind=ClaimKind.HYPOTHESIS,
            origin=ClaimOrigin.LOCAL_AUTHORITY,
            status=ClaimStatus.PRELIMINARY,
            confidence=0.68,
            evidence_ids=evidence_ids,
            source_url="https://library.municode.com/fl",
            next_verification_step=(
                "Confirm the controlling municipal zoning district and adopted code section."
            ),
            claim_freshness=ClaimFreshnessStatus.REQUIRES_OFFICIAL_VERIFICATION,
            source_mode=SourceMode.FIXTURE,
        )
    ]


def _acquisition_claims(
    *,
    run_id: RunId,
    report_id: ReportId,
    profile: FixtureSiteProfile,
    evidence_items: list[EvidenceItem],
    calculations: list[CalculationResult],
    comp_payload: JsonObject,
    residual_payload: JsonObject,
) -> list[Claim]:
    evidence_ids = [item.evidence_id for item in evidence_items]
    comp_claim_evidence_ids = _claim_evidence_ids_for_source_types(
        evidence_items,
        (EvidenceSourceType.MARKET_COMP, EvidenceSourceType.RENTAL_COMP),
    )
    if not comp_claim_evidence_ids:
        comp_claim_evidence_ids = evidence_ids
    calc_ids = [item.calculation_id for item in calculations]
    adv = comp_payload.get("adv_per_unit")
    land_value = comp_payload.get("estimated_land_value")
    max_offer = residual_payload.get("max_supportable_land_price")
    land_comp_quality = _land_comp_quality_summary(comp_payload)
    unit_comp_quality = _unit_comp_quality_summary(comp_payload)
    return [
        Claim(
            claim_id=ClaimId(f"claim_{run_id}_zoning_program"),
            run_id=run_id,
            report_id=report_id,
            claim_text=(
                f"{profile.address} is modeled as a {profile.zoning_code} site with "
                f"an estimated fixture program of up to {profile.max_units} units."
            ),
            claim_type="zoning_program",
            field_key="site.program",
            kind=ClaimKind.HYPOTHESIS,
            origin=ClaimOrigin.LOCAL_AUTHORITY,
            status=ClaimStatus.PRELIMINARY,
            confidence=0.66,
            evidence_ids=evidence_ids[:3],
            source_url="https://library.municode.com/fl",
            next_verification_step="Verify zoning district, density controls, and dimensional standards.",
            claim_freshness=ClaimFreshnessStatus.REQUIRES_OFFICIAL_VERIFICATION,
            source_mode=SourceMode.FIXTURE,
        ),
        Claim(
            claim_id=ClaimId(f"claim_{run_id}_comp_value"),
            run_id=run_id,
            report_id=report_id,
            claim_text=(
                f"Fixture comps indicate an estimated land value of {land_value} and "
                f"an ADV per unit of {adv}."
            ),
            claim_type="comp_value_signal",
            field_key="market.comp_signal",
            kind=ClaimKind.CALCULATION,
            origin=ClaimOrigin.GIS_PROVIDER,
            status=ClaimStatus.PRELIMINARY,
            confidence=0.7,
            evidence_ids=comp_claim_evidence_ids,
            source_url="fixture://market-comps",
            next_verification_step="Replace fixture comps with county-verified comparable sale evidence.",
            claim_freshness=ClaimFreshnessStatus.FIXTURE,
            metadata={
                "pricing_source": "fixture_comps",
                "land_comp_quality": land_comp_quality,
                "unit_comp_quality": unit_comp_quality,
            },
            source_mode=SourceMode.FIXTURE,
        ),
        Claim(
            claim_id=ClaimId(f"claim_{run_id}_max_offer"),
            run_id=run_id,
            report_id=report_id,
            claim_text=f"Deterministic residual math yields a fixture max supportable land price of {max_offer}.",
            claim_type="max_supportable_land_price",
            field_key="underwriting.max_offer",
            kind=ClaimKind.CALCULATION,
            origin=ClaimOrigin.DETERMINISTIC_CALCULATION,
            status=ClaimStatus.PRELIMINARY,
            confidence=0.86,
            evidence_ids=evidence_ids,
            calculation_ids=calc_ids,
            next_verification_step="Re-run underwriting with live source evidence before issuing a final offer.",
            claim_freshness=ClaimFreshnessStatus.FIXTURE,
            source_mode=SourceMode.FIXTURE,
        ),
    ]


def _comping_claims(
    *,
    run_id: RunId,
    report_id: ReportId,
    profile: FixtureSiteProfile,
    evidence_items: list[EvidenceItem],
    comp_payload: JsonObject,
) -> list[Claim]:
    evidence_ids = [item.evidence_id for item in evidence_items]
    comp_claim_evidence_ids = _claim_evidence_ids_for_source_types(
        evidence_items,
        (EvidenceSourceType.MARKET_COMP, EvidenceSourceType.RENTAL_COMP),
    )
    if not comp_claim_evidence_ids:
        comp_claim_evidence_ids = evidence_ids
    land_comp_quality = _land_comp_quality_summary(comp_payload)
    unit_comp_quality = _unit_comp_quality_summary(comp_payload)
    land_value = comp_payload.get("estimated_land_value")
    adv = comp_payload.get("adv_per_unit")
    return [
        Claim(
            claim_id=ClaimId(f"claim_{run_id}_comp_candidate_quality"),
            run_id=run_id,
            report_id=report_id,
            claim_text=(
                f"Comparable search for {profile.address} produced fixture market signals "
                f"with land comp quality {land_comp_quality} and unit comp quality {unit_comp_quality}."
            ),
            claim_type="comp_candidate_quality",
            field_key="market.comp_quality",
            kind=ClaimKind.HYPOTHESIS,
            origin=ClaimOrigin.GIS_PROVIDER,
            status=ClaimStatus.PRELIMINARY,
            confidence=0.68,
            evidence_ids=comp_claim_evidence_ids,
            source_url="fixture://market-comps",
            next_verification_step=(
                "Reconcile public sold-listing candidates with county records, parcel facts, "
                "sale recency, lot size, and micro-market fit before underwriting."
            ),
            claim_freshness=ClaimFreshnessStatus.FIXTURE,
            metadata={
                "land_comp_quality": land_comp_quality,
                "unit_comp_quality": unit_comp_quality,
                "estimated_land_value": land_value,
                "adv_per_unit": adv,
            },
            source_mode=SourceMode.FIXTURE,
        )
    ]


def _live_comping_claims(
    *,
    run_id: RunId,
    report_id: ReportId,
    property_payload: JsonObject,
    evidence_items: list[EvidenceItem],
    comp_payload: JsonObject,
    source_mode: SourceMode,
) -> list[Claim]:
    comp_evidence_ids = _claim_evidence_ids_for_source_types(
        evidence_items,
        (EvidenceSourceType.MARKET_COMP, EvidenceSourceType.RENTAL_COMP),
    )
    if not comp_evidence_ids:
        comp_evidence_ids = [item.evidence_id for item in evidence_items]
    land_comp_quality = _land_comp_quality_summary(comp_payload)
    unit_comp_quality = _unit_comp_quality_summary(comp_payload)
    public_listing_search = _required_dict(comp_payload, "web_listing_search")
    return [
        Claim(
            claim_id=ClaimId(f"claim_{run_id}_live_comp_candidate_quality"),
            run_id=run_id,
            report_id=report_id,
            claim_text=(
                f"Comparable search for {property_payload.get('address', 'the site')} used "
                "tool-derived parcel and zoning context, then followed a sold-land-first "
                "public listing and county-record strategy."
            ),
            claim_type="comp_candidate_quality",
            field_key="market.comp_quality",
            kind=ClaimKind.HYPOTHESIS,
            origin=ClaimOrigin.GIS_PROVIDER,
            status=ClaimStatus.PRELIMINARY,
            confidence=0.7,
            evidence_ids=comp_evidence_ids,
            source_url=str(
                public_listing_search.get("query") or "https://plotlot.local/market-comps"
            ),
            next_verification_step=(
                "Reconcile accepted public listing candidates against county records and "
                "confirm same micro-market fit before using comps for an offer."
            ),
            claim_freshness=ClaimFreshnessStatus.REQUIRES_OFFICIAL_VERIFICATION,
            metadata={
                "land_comp_quality": land_comp_quality,
                "unit_comp_quality": unit_comp_quality,
                "search_strategy": str(public_listing_search.get("strategy") or ""),
                "query_plan": public_listing_search.get("query_plan") or [],
            },
            source_mode=source_mode,
        )
    ]


def _build_report(
    *,
    report_id: ReportId,
    run_id: RunId,
    analysis_type: str,
    claims: list[Claim],
    evidence_items: list[EvidenceItem],
    calculations: list[CalculationResult],
    source_mode: SourceMode,
    underwriting_mode: JsonObject | None = None,
    artifacts: JsonObject | None = None,
) -> Report:
    match analysis_type:
        case "zoning_research":
            report_type = ReportType.ZONING_RESEARCH_MEMO
        case "lender_package":
            report_type = ReportType.LENDER_PACKAGE
        case "construction_budget":
            report_type = ReportType.CONSTRUCTION_BUDGET
        case _:
            report_type = ReportType.ACQUISITION_MEMO
    public_listing_section = _public_listing_report_section(artifacts or {})
    sections: list[JsonObject] = [
        {
            "section_id": "site_summary",
            "title": "Site Summary",
            "claim_ids": [str(claim.claim_id) for claim in claims[:1]],
        },
        {
            "section_id": "underwriting_summary",
            "title": "Underwriting Summary",
            "claim_ids": [str(claim.claim_id) for claim in claims[1:]],
            "calculation_ids": [item.calculation_id for item in calculations],
            "underwriting_mode": underwriting_mode or {},
            "feasibility": _required_dict(artifacts or {}, "feasibility"),
            "comp_search_strategy": _required_dict(artifacts or {}, "comp_search_strategy"),
            "acquisition_guidance": _required_dict(artifacts or {}, "acquisition_guidance"),
            "comp_support_summary": _comp_support_summary(artifacts or {}),
            "comping_decision_trace": _required_dict(
                _required_dict(artifacts or {}, "comping_workflow"),
                "comping_decision_trace",
            ),
            "contextual_land_listing_reconciliation": _required_dict(
                artifacts or {},
                "contextual_land_listing_reconciliation",
            ),
            "zoning_support_summary": _zoning_support_summary(artifacts or {}),
        },
    ]
    if public_listing_section is not None:
        sections.append(public_listing_section)
    sections.append(
        {
            "section_id": "evidence_appendix",
            "title": "Evidence Appendix",
            "evidence_ids": [str(item.evidence_id) for item in evidence_items],
        }
    )
    return Report(
        report_id=report_id,
        run_id=run_id,
        report_type=report_type,
        title=f"Preliminary {analysis_type.replace('_', ' ').title()}",
        status=ReportStatus.PRELIMINARY,
        sections=sections,
        claims=[claim.claim_id for claim in claims],
        evidence_ids=[item.evidence_id for item in evidence_items],
        calculation_ids=[item.calculation_id for item in calculations],
        source_mode=source_mode,
    )


def _public_listing_report_section(artifacts: JsonObject) -> JsonObject | None:
    comps = _required_dict(artifacts, "comps")
    public_listing_land_comparables = _required_list(comps, "public_listing_land_comparables")
    if not public_listing_land_comparables:
        return None
    summary = _required_dict(artifacts, "comp_search_strategy")
    return {
        "section_id": "public_listing_comps",
        "title": "Public Listing Land Comps",
        "public_listing_signal_tier": summary.get("public_listing_signal_tier", ""),
        "public_listing_domains": summary.get("public_listing_domains", []),
        "comparables": public_listing_land_comparables,
        "count": len(public_listing_land_comparables),
        "preliminary": summary.get("public_listing_signal_tier") != "county_reconciled",
    }


def _comp_support_summary(artifacts: JsonObject) -> JsonObject:
    guidance = _required_dict(artifacts, "acquisition_guidance")
    strategy = _required_dict(artifacts, "comp_search_strategy")
    comping_workflow = _required_dict(artifacts, "comping_workflow")
    comping_trust_gates = _required_dict(comping_workflow, "trust_gates")
    comping_underwriting_status = str(
        comping_trust_gates.get("underwriting_status") or "unknown"
    ).strip()
    recommendation_confidence = str(guidance.get("recommendation_confidence") or "").strip()
    recommended_action = str(guidance.get("recommended_action") or "").strip()
    requires_validation = bool(guidance.get("requires_market_signal_validation"))
    public_listing_signal_tier = str(strategy.get("public_listing_signal_tier") or "none").strip()
    land_signal_tier = str(strategy.get("land_signal_tier") or "none").strip()
    land_support_source, land_support_fit_score, land_support_quality_score = (
        _land_support_snapshot(
            strategy=strategy,
            land_signal_tier=land_signal_tier,
        )
    )
    exit_support_fit_score = float(strategy.get("best_exit_comp_fit_score") or 0.0)
    exit_support_quality_score = float(strategy.get("best_exit_comp_qualification_score") or 0.0)
    status = "passed"
    reason = "direct land comps or county-reconciled support available"
    if recommended_action == "insufficient_support":
        status = "warning"
        reason = "live market support is too weak for a confident offer recommendation"
    elif requires_validation:
        status = "warning"
        reason = "market signal depends on contextual public listing evidence that still needs validation"
    elif recommendation_confidence == "medium":
        status = "warning"
        reason = "offer guidance depends on county-reconciled public listing support rather than direct land comps"
    return {
        "status": status,
        "reason": reason,
        "comping_underwriting_status": comping_underwriting_status,
        "comping_underwriting_blocker": _comping_underwriting_blocker(comping_underwriting_status),
        "recommendation_confidence": recommendation_confidence or "unknown",
        "recommended_action": recommended_action or "unknown",
        "requires_market_signal_validation": requires_validation,
        "land_signal_tier": land_signal_tier,
        "public_listing_signal_tier": public_listing_signal_tier,
        "land_support_source": land_support_source,
        "land_support_fit_score": land_support_fit_score,
        "land_support_quality_score": land_support_quality_score,
        "land_support_market_scope": str(strategy.get("public_listing_market_scope") or "unknown"),
        "land_support_sale_date": str(strategy.get("best_public_listing_sale_date") or ""),
        "land_support_recency_tier": str(strategy.get("public_listing_recency_tier") or "unknown"),
        "land_support_parse_confidence": float(
            strategy.get("best_public_listing_parse_confidence") or 0.0
        ),
        "land_micro_market_confidence": str(
            strategy.get("public_listing_micro_market_confidence") or "unknown"
        ),
        "exit_support_fit_score": exit_support_fit_score,
        "exit_support_quality_score": exit_support_quality_score,
        "exit_support_distance_miles": float(strategy.get("best_exit_comp_distance_miles") or 0.0),
        "exit_support_market_scope": str(strategy.get("exit_support_market_scope") or "unknown"),
        "exit_support_sale_date": str(strategy.get("best_exit_comp_sale_date") or ""),
        "exit_support_recency_tier": str(strategy.get("exit_comp_recency_tier") or "unknown"),
        "exit_micro_market_confidence": str(
            strategy.get("exit_micro_market_confidence") or "unknown"
        ),
        "combined_support_tier": _combined_support_tier(
            recommended_action=recommended_action,
            land_signal_tier=land_signal_tier,
            land_support_fit_score=land_support_fit_score,
            exit_support_fit_score=exit_support_fit_score,
        ),
    }


def _comping_underwriting_blocker(status: str) -> str:
    match status:
        case "available_to_underwriting":
            return ""
        case "blocked_pending_county_reconciliation":
            return "public listing comps require county-record reconciliation before confident underwriting"
        case "blocked_missing_land_comp_support":
            return "no acceptable land comp support is available for underwriting"
        case "blocked_until_underwriting_skill":
            return "comping skill intentionally stops before underwriting"
        case "":
            return "comping workflow did not report an underwriting status"
        case _:
            return f"comping workflow status requires review: {status}"


def _comping_workflow_underwriting_status(artifacts: JsonObject) -> str:
    comping_workflow = _required_dict(artifacts, "comping_workflow")
    trust_gates = _required_dict(comping_workflow, "trust_gates")
    return str(trust_gates.get("underwriting_status") or "unknown").strip()


def _comping_workflow_blocks_underwriting(artifacts: JsonObject) -> bool:
    status = _comping_workflow_underwriting_status(artifacts)
    return status not in {"available_to_underwriting", "blocked_until_underwriting_skill"}


def _zoning_support_summary(artifacts: JsonObject) -> JsonObject:
    ordinance_search = _required_dict(artifacts, "ordinance_search")
    ordinance_rules = _required_dict(artifacts, "ordinance_rules")
    gis_source = _required_dict(artifacts, "gis_source")
    gis_site_context = _required_dict(artifacts, "gis_site_context")
    gis_context = gis_site_context or gis_source
    has_rules = bool(ordinance_rules)
    requires_official_verification = bool(
        ordinance_search.get("requires_official_verification")
        or ordinance_rules.get("requires_official_verification")
    )
    fallback_source = str(
        ordinance_search.get("fallback_source") or ordinance_rules.get("source") or "none"
    ).strip()
    authority_source_type = str(
        ordinance_search.get("authority_source_type")
        or ordinance_rules.get("authority_source_type")
        or fallback_source
        or "none"
    ).strip()
    authority_resolution = str(
        ordinance_search.get("authority_resolution")
        or ordinance_rules.get("authority_resolution")
        or "unknown"
    ).strip()
    authority_confidence = str(
        ordinance_search.get("authority_confidence")
        or ordinance_rules.get("authority_confidence")
        or "unknown"
    ).strip()
    authority_jurisdiction = str(
        ordinance_search.get("authority_jurisdiction")
        or ordinance_rules.get("authority_jurisdiction")
        or ""
    ).strip()
    authority_is_live = bool(
        ordinance_search.get("authority_is_live") or ordinance_rules.get("authority_is_live")
    )
    authority_is_official = bool(
        ordinance_search.get("authority_is_official")
        or ordinance_rules.get("authority_is_official")
    )
    gis_warning = str(gis_context.get("warning") or "").strip()
    gis_applicability = str(gis_context.get("zoning_record_applicability") or "").strip() or (
        "requires_municipal_verification" if gis_warning else "direct"
    )
    status = "passed"
    reason = "direct ordinance and GIS zoning context available"
    if not has_rules:
        status = "warning"
        reason = "no ordinance rules were resolved for the subject zoning district"
    elif requires_official_verification:
        status = "warning"
        reason = "zoning support still depends on preliminary ordinance or staged municipal authority context"
    elif not authority_is_official:
        status = "warning"
        reason = "zoning authority source is not marked official"
    elif not authority_is_live:
        status = "warning"
        reason = "zoning authority source is not live/current enough for final entitlement claims"
    elif authority_confidence in {"staged_preliminary", "unknown"}:
        status = "warning"
        reason = "zoning authority confidence is preliminary or unknown"
    elif gis_applicability == "requires_municipal_verification":
        status = "warning"
        reason = "GIS zoning context requires municipal verification"
    elif gis_warning:
        status = "warning"
        reason = "GIS source selection still requires municipal zoning confirmation"
    return {
        "status": status,
        "reason": reason,
        "ordinance_rules_resolved": has_rules,
        "ordinance_source": fallback_source or "none",
        "requires_official_verification": requires_official_verification,
        "authority_source_type": authority_source_type or "none",
        "authority_resolution": authority_resolution or "unknown",
        "authority_confidence": authority_confidence or "unknown",
        "authority_jurisdiction": authority_jurisdiction,
        "authority_is_live": authority_is_live,
        "authority_is_official": authority_is_official,
        "gis_applicability": gis_applicability,
    }


def _land_support_snapshot(
    *,
    strategy: JsonObject,
    land_signal_tier: str,
) -> tuple[str, float, float]:
    if land_signal_tier == "direct_land_comps":
        return (
            "direct_land_comps",
            float(strategy.get("best_direct_land_comp_fit_score") or 0.0),
            float(strategy.get("best_direct_land_comp_qualification_score") or 0.0),
        )
    if land_signal_tier in {"county_reconciled_public_listing", "contextual_public_listing"}:
        return (
            land_signal_tier,
            float(strategy.get("best_public_listing_fit_score") or 0.0),
            0.0,
        )
    return ("none", 0.0, 0.0)


def _best_public_listing_sale_date(public_listing_land_comparables: list[JsonObject]) -> str:
    sale_dates = [
        parsed.isoformat()
        for item in public_listing_land_comparables
        if isinstance(item, dict)
        and isinstance(parsed := parse_iso_date(str(item.get("sale_date") or "")), date)
    ]
    if not sale_dates:
        return ""
    return max(sale_dates)


def _public_listing_market_scope(public_listing_land_comparables: list[JsonObject]) -> str:
    if not public_listing_land_comparables:
        return "none"
    zip_match_count = sum(
        1
        for item in public_listing_land_comparables
        if isinstance(item, dict) and item.get("zip_match") is True
    )
    zip_known_count = sum(
        1
        for item in public_listing_land_comparables
        if isinstance(item, dict) and item.get("zip_match") is not None
    )
    matched_count = sum(
        1
        for item in public_listing_land_comparables
        if isinstance(item, dict) and item.get("municipality_match") is True
    )
    known_count = sum(
        1
        for item in public_listing_land_comparables
        if isinstance(item, dict) and str(item.get("municipality") or "").strip()
    )
    if zip_match_count == len(public_listing_land_comparables):
        return "subject_zip"
    if (
        matched_count == len(public_listing_land_comparables)
        and zip_known_count > 0
        and zip_match_count == 0
    ):
        return "cross_zip_same_municipality"
    if matched_count == len(public_listing_land_comparables):
        return "subject_municipality"
    if known_count > 0:
        return "partial_unknown"
    return "unknown"


def _public_listing_micro_market_confidence(
    public_listing_land_comparables: list[JsonObject],
) -> str:
    if not public_listing_land_comparables:
        return "none"
    zip_match_count = sum(
        1
        for item in public_listing_land_comparables
        if isinstance(item, dict) and item.get("zip_match") is True
    )
    municipality_match_count = sum(
        1
        for item in public_listing_land_comparables
        if isinstance(item, dict) and item.get("municipality_match") is True
    )
    best_parse_confidence = max(
        (
            float(item.get("parsing_confidence") or 0.0)
            for item in public_listing_land_comparables
            if isinstance(item, dict)
        ),
        default=0.0,
    )
    if (
        zip_match_count == len(public_listing_land_comparables)
        and municipality_match_count == len(public_listing_land_comparables)
        and best_parse_confidence >= 0.9
    ):
        return "high"
    if municipality_match_count == len(public_listing_land_comparables):
        if zip_match_count > 0 or best_parse_confidence >= 0.9:
            return "medium"
        return "low"
    return "low"


def _public_listing_recency_tier(best_public_listing_sale_date: str) -> str:
    parsed_sale_date = parse_iso_date(best_public_listing_sale_date)
    if not isinstance(parsed_sale_date, date):
        return "unknown"
    days_since_sale = (datetime.now(timezone.utc).date() - parsed_sale_date).days
    if days_since_sale <= 183:
        return "recent_6m"
    if days_since_sale <= 366:
        return "recent_12m"
    if days_since_sale <= 731:
        return "extended_24m"
    return "stale"


def _combined_support_tier(
    *,
    recommended_action: str,
    land_signal_tier: str,
    land_support_fit_score: float,
    exit_support_fit_score: float,
) -> str:
    if recommended_action == "insufficient_support":
        if exit_support_fit_score >= 0.8:
            return "exit_only"
        return "weak"
    if (
        land_signal_tier == "direct_land_comps"
        and exit_support_fit_score >= 0.8
        and land_support_fit_score >= 0.8
    ):
        return "balanced"
    if land_signal_tier == "county_reconciled_public_listing" and exit_support_fit_score >= 0.8:
        return "county_land_plus_exit"
    if land_signal_tier == "direct_land_comps":
        return "land_weighted"
    return "weak"


def _exit_micro_market_confidence(exit_support_snapshot: JsonObject) -> str:
    market_scope = str(exit_support_snapshot.get("exit_support_market_scope") or "unknown").strip()
    recency_tier = str(exit_support_snapshot.get("exit_support_recency_tier") or "unknown").strip()
    distance_miles = float(exit_support_snapshot.get("exit_support_distance_miles") or 0.0)
    if (
        market_scope == "subject_zip"
        and distance_miles <= 1.0
        and recency_tier in {"recent_6m", "recent_12m"}
    ):
        return "high"
    if (
        market_scope in {"subject_municipality", "subject_zip"}
        and distance_miles <= 1.5
        and recency_tier in {"recent_6m", "recent_12m", "extended_24m"}
    ):
        return "medium"
    return "low"


def _required_dict(payload: JsonObject, key: str) -> JsonObject:
    value = payload.get(key)
    if isinstance(value, dict):
        return value
    return {}


def _required_list(payload: JsonObject, key: str) -> list[JsonObject]:
    value = payload.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _claim_evidence_ids_for_source_types(
    evidence_items: list[EvidenceItem],
    source_types: tuple[EvidenceSourceType, ...],
) -> list[EvidenceId]:
    selected_ids: list[EvidenceId] = []
    for item in evidence_items:
        if item.source_type in source_types and item.evidence_id not in selected_ids:
            selected_ids.append(item.evidence_id)
    return selected_ids


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _source_domain(url: str) -> str:
    return urlparse(url).netloc.strip().lower()


def _comp_qualification_score(raw_item: JsonObject) -> float | None:
    adjustments = raw_item.get("adjustments")
    if not isinstance(adjustments, dict):
        return None
    score = adjustments.get("qualification_score")
    if not isinstance(score, int | float):
        return None
    return round(float(score), 3)


def _comp_address_sort_penalty(raw_item: JsonObject) -> int:
    address = str(raw_item.get("address") or "").strip()
    return 1 if address.replace("-", "").isdigit() and address else 0


def _land_comp_quality_status(raw_item: JsonObject) -> str:
    score = _comp_qualification_score(raw_item)
    if score is not None:
        return "strong" if score >= 0.7 else "weak"
    if bool(raw_item.get("user_supplied")):
        return "user_supplied_unscored"
    return "unscored"


def _unit_comp_quality_status(raw_item: JsonObject) -> str:
    score = _comp_qualification_score(raw_item)
    if score is not None:
        return "strong" if score >= 0.7 else "weak"
    if bool(raw_item.get("user_supplied")):
        return "user_supplied_unscored"
    return "unscored"


def _land_comp_cluster_key(raw_item: JsonObject) -> tuple[str, int, int] | None:
    sale_date = str(raw_item.get("sale_date") or "").strip()
    sale_price = raw_item.get("sale_price")
    lot_size_sqft = raw_item.get("lot_size_sqft")
    if (
        not sale_date
        or not isinstance(sale_price, int | float)
        or not isinstance(lot_size_sqft, int | float)
    ):
        return None
    return (
        sale_date,
        int(round(float(sale_price) / 5_000.0) * 5_000),
        int(round(float(lot_size_sqft) / 250.0) * 250),
    )


def _comparable_identity_key(raw_item: JsonObject) -> str | None:
    provider = str(raw_item.get("provider") or "").strip().lower()
    source_url = str(raw_item.get("source_url") or "").strip().lower()
    if source_url:
        return f"{provider}|url|{source_url}"
    source_identifier = str(raw_item.get("source_identifier") or "").strip().upper()
    if source_identifier:
        return f"{provider}|id|{source_identifier}"
    address = str(raw_item.get("address") or "").strip().upper()
    if address:
        return f"{provider}|address|{address}"
    cluster_key = _land_comp_cluster_key(raw_item)
    if cluster_key is None:
        return None
    return f"{provider}|cluster|{cluster_key[0]}|{cluster_key[1]}|{cluster_key[2]}"


def _independent_land_comp_counts(comparables: list[JsonObject]) -> tuple[int, int]:
    all_clusters: set[tuple[str, int, int]] = set()
    strong_clusters: set[tuple[str, int, int]] = set()
    independent_count = 0
    strong_independent_count = 0
    for comparable in comparables:
        cluster_key = _land_comp_cluster_key(comparable)
        score = _comp_qualification_score(comparable)
        is_strong = isinstance(score, float) and score >= 0.7
        if cluster_key is None:
            independent_count += 1
            if is_strong:
                strong_independent_count += 1
            continue
        if cluster_key not in all_clusters:
            all_clusters.add(cluster_key)
            independent_count += 1
        if is_strong and cluster_key not in strong_clusters:
            strong_clusters.add(cluster_key)
            strong_independent_count += 1
    return independent_count, strong_independent_count


def _land_comp_quality_summary(comps_payload: JsonObject) -> JsonObject:
    comparables = _required_list(comps_payload, "comparables")
    scores = [
        score
        for comparable in comparables
        for score in [_comp_qualification_score(comparable)]
        if score is not None
    ]
    best_fit_score, best_fit_variance_ratio, best_fit_qualification_score = (
        _best_land_comp_fit_metrics(comps_payload=comps_payload)
    )
    independent_count, strong_independent_count = _independent_land_comp_counts(
        [comparable for comparable in comparables if isinstance(comparable, dict)]
    )
    return {
        "land_comp_count": len(comparables),
        "scored_land_comp_count": len(scores),
        "strong_land_comp_count": len([score for score in scores if score >= 0.7]),
        "independent_land_comp_count": independent_count,
        "strong_independent_land_comp_count": strong_independent_count,
        "land_comp_scores": scores,
        "best_fit_score": best_fit_score,
        "best_fit_lot_size_variance_ratio": best_fit_variance_ratio,
        "best_fit_qualification_score": best_fit_qualification_score,
        "direct_land_comp_signal": _has_direct_land_comp_signal(comps_payload),
        "manual_override_used": bool(comps_payload.get("manual_comp_override")),
    }


def _best_land_comp_fit_metrics(comps_payload: JsonObject) -> tuple[float, float, float]:
    comparables = comps_payload.get("comparables")
    subject_lot_size_sqft = float(comps_payload.get("subject_lot_size_sqft") or 0.0)
    if subject_lot_size_sqft <= 0 and isinstance(comparables, list):
        for comparable in comparables:
            if not isinstance(comparable, dict):
                continue
            comparable_lot_size = comparable.get("subject_lot_size_sqft")
            if isinstance(comparable_lot_size, int | float) and float(comparable_lot_size) > 0:
                subject_lot_size_sqft = float(comparable_lot_size)
                break
    if subject_lot_size_sqft <= 0 or not isinstance(comparables, list):
        return 0.0, 0.0, 0.0

    ranked_metrics: list[tuple[float, float, float]] = []
    for comparable in comparables:
        if not isinstance(comparable, dict):
            continue
        lot_size_sqft = comparable.get("lot_size_sqft")
        if not isinstance(lot_size_sqft, int | float) or float(lot_size_sqft) <= 0:
            continue
        variance_ratio = lot_size_variance_ratio(
            subject_lot_area_sf=subject_lot_size_sqft,
            comparable_lot_size_sqft=float(lot_size_sqft),
        )
        if variance_ratio is None:
            continue
        fit_score = contextual_fit_score(
            subject_lot_area_sf=subject_lot_size_sqft,
            comparable_lot_size_sqft=float(lot_size_sqft),
        )
        qualification_score = float(_comp_qualification_score(comparable) or 0.0)
        ranked_metrics.append((fit_score, round(variance_ratio, 3), qualification_score))
    if not ranked_metrics:
        return 0.0, 0.0, 0.0
    ranked_metrics.sort(key=lambda metric: (-metric[0], metric[1], -metric[2]))
    return ranked_metrics[0]


def _unit_comp_quality_summary(comps_payload: JsonObject) -> JsonObject:
    unit_comparables = _required_list(comps_payload, "unit_comparables")
    scores = [
        score
        for comparable in unit_comparables
        for score in [_comp_qualification_score(comparable)]
        if score is not None
    ]
    best_exit_fit_score, best_exit_price_variance_ratio, best_exit_qualification_score = (
        _best_unit_comp_fit_metrics(comps_payload)
    )
    strong_scores = [score for score in scores if score >= 0.7]
    very_strong_scores = [score for score in scores if score >= 0.85]
    return {
        "unit_comp_count": len(unit_comparables),
        "scored_unit_comp_count": len(scores),
        "strong_unit_comp_count": len(strong_scores),
        "very_strong_unit_comp_count": len(very_strong_scores),
        "unit_comp_scores": scores,
        "best_exit_fit_score": best_exit_fit_score,
        "best_exit_price_variance_ratio": best_exit_price_variance_ratio,
        "best_exit_qualification_score": best_exit_qualification_score,
        "qualified_exit_comp_signal": _has_qualified_live_unit_comp_signal(comps_payload),
        "manual_override_used": bool(comps_payload.get("manual_comp_override")),
    }


def _best_unit_comp_fit_metrics(comps_payload: JsonObject) -> tuple[float, float, float]:
    unit_comparables = comps_payload.get("unit_comparables")
    adv_per_unit = comps_payload.get("adv_per_unit")
    if (
        not isinstance(unit_comparables, list)
        or not isinstance(adv_per_unit, int | float)
        or float(adv_per_unit) <= 0
    ):
        return 0.0, 0.0, 0.0
    target_adv_per_unit = float(adv_per_unit)
    ranked_metrics: list[tuple[float, float, float]] = []
    for comparable in unit_comparables:
        if not isinstance(comparable, dict):
            continue
        price_per_unit = comparable.get("price_per_unit")
        if not isinstance(price_per_unit, int | float) or float(price_per_unit) <= 0:
            continue
        variance_ratio = abs(float(price_per_unit) - target_adv_per_unit) / target_adv_per_unit
        fit_score = round(max(0.0, 1.0 - variance_ratio), 3)
        qualification_score = float(_comp_qualification_score(comparable) or 0.0)
        ranked_metrics.append((fit_score, round(variance_ratio, 3), qualification_score))
    if not ranked_metrics:
        return 0.0, 0.0, 0.0
    ranked_metrics.sort(key=lambda metric: (-metric[0], metric[1], -metric[2]))
    return ranked_metrics[0]


def _payload_number(payload: JsonObject, key: str) -> int | float | None:
    value = payload.get(key)
    if isinstance(value, int | float):
        return value
    nested = payload.get("result")
    if isinstance(nested, dict):
        nested_value = nested.get(key)
        if isinstance(nested_value, int | float):
            return nested_value
    return None


def _build_comp_search_strategy_summary(
    *,
    comps_payload: JsonObject,
    attempts: list[JsonObject],
    property_payload: JsonObject,
) -> JsonObject:
    land_comp_quality = _land_comp_quality_summary(comps_payload)
    unit_comp_quality = _unit_comp_quality_summary(comps_payload)
    selected_attempt = next(
        (attempt for attempt in attempts if bool(attempt.get("selected"))), None
    )
    contextual_land_verification = _required_dict(
        comps_payload,
        "contextual_land_listing_verification",
    )
    contextual_land_reconciliation = _required_dict(
        comps_payload,
        "contextual_land_listing_reconciliation",
    )
    contextual_verified_candidate_count = _contextual_priced_candidate_count(
        _required_list(contextual_land_verification, "verified_candidates")
    )
    county_reconciled_candidate_count = int(
        contextual_land_reconciliation.get("reconciled_candidate_count") or 0
    )
    if bool(comps_payload.get("manual_comp_override")):
        land_signal_tier = "manual_override"
    elif _has_direct_land_comp_signal(comps_payload):
        land_signal_tier = "direct_land_comps"
    elif _has_supported_relaxed_land_comp_signal(comps_payload):
        land_signal_tier = "supported_relaxed_land_comps"
    elif county_reconciled_candidate_count > 0:
        land_signal_tier = "county_reconciled_public_listing"
    elif contextual_verified_candidate_count > 0:
        land_signal_tier = "contextual_public_listing"
    else:
        land_signal_tier = "none"
    public_listing_land_comparables = _required_list(
        comps_payload, "public_listing_land_comparables"
    )
    unit_comparables = _required_list(comps_payload, "unit_comparables")
    public_listing_signal_tier = "none"
    best_public_listing_fit_score = 0.0
    best_public_listing_lot_size_variance_ratio = 0.0
    if public_listing_land_comparables:
        first_public_listing = public_listing_land_comparables[0]
        public_listing_signal_tier = str(
            first_public_listing.get("verification_status") or "contextual_verified"
        )
        best_public_listing_fit_score = float(first_public_listing.get("fit_score") or 0.0)
        best_public_listing_lot_size_variance_ratio = float(
            first_public_listing.get("lot_size_variance_ratio") or 0.0
        )
    best_public_listing_sale_date = _best_public_listing_sale_date(public_listing_land_comparables)
    best_public_listing_parse_confidence = (
        float(public_listing_land_comparables[0].get("parsing_confidence") or 0.0)
        if public_listing_land_comparables
        else 0.0
    )
    public_listing_domains = sorted(
        {
            str(item.get("source_domain") or "").strip()
            for item in public_listing_land_comparables
            if str(item.get("source_domain") or "").strip()
        }
    )
    public_listing_micro_market_confidence = _public_listing_micro_market_confidence(
        public_listing_land_comparables
    )
    web_listing_search = _required_dict(comps_payload, "web_listing_search")
    exit_support_snapshot = best_exit_comp_snapshot(
        unit_comparables=unit_comparables,
        adv_per_unit=float(comps_payload.get("adv_per_unit") or 0.0),
        subject_address=str(property_payload.get("address") or ""),
    )
    exit_micro_market_confidence = _exit_micro_market_confidence(exit_support_snapshot)
    exit_signal_tier = "none"
    if _has_qualified_live_unit_comp_signal(comps_payload):
        exit_signal_tier = (
            "relaxed_improved_sales"
            if bool(comps_payload.get("used_relaxed_unit_comps"))
            else "strict_improved_sales"
        )
    return {
        "attempts": attempts,
        "selected_months": selected_attempt.get("months")
        if isinstance(selected_attempt, dict)
        else None,
        "selected_reason": (
            selected_attempt.get("selection_reason")
            if isinstance(selected_attempt, dict)
            else "unqualified_first_attempt"
        ),
        "land_signal_tier": land_signal_tier,
        "exit_signal_tier": exit_signal_tier,
        "sales_source_type": str(comps_payload.get("sales_source_type") or ""),
        "exit_comp_source_type": str(comps_payload.get("exit_comp_source_type") or ""),
        "best_direct_land_comp_fit_score": land_comp_quality["best_fit_score"],
        "best_direct_land_comp_lot_size_variance_ratio": land_comp_quality[
            "best_fit_lot_size_variance_ratio"
        ],
        "best_direct_land_comp_qualification_score": land_comp_quality[
            "best_fit_qualification_score"
        ],
        "best_exit_comp_fit_score": unit_comp_quality["best_exit_fit_score"],
        "best_exit_comp_price_variance_ratio": unit_comp_quality["best_exit_price_variance_ratio"],
        "best_exit_comp_qualification_score": unit_comp_quality["best_exit_qualification_score"],
        "best_exit_comp_distance_miles": float(
            exit_support_snapshot.get("exit_support_distance_miles") or 0.0
        ),
        "best_exit_comp_sale_date": str(exit_support_snapshot.get("exit_support_sale_date") or ""),
        "exit_support_market_scope": str(
            exit_support_snapshot.get("exit_support_market_scope") or "unknown"
        ),
        "exit_micro_market_confidence": exit_micro_market_confidence,
        "exit_comp_recency_tier": str(
            exit_support_snapshot.get("exit_support_recency_tier") or "unknown"
        ),
        "public_listing_signal_tier": public_listing_signal_tier,
        "public_listing_land_comp_count": len(public_listing_land_comparables),
        "best_public_listing_fit_score": best_public_listing_fit_score,
        "best_public_listing_lot_size_variance_ratio": best_public_listing_lot_size_variance_ratio,
        "best_public_listing_sale_date": best_public_listing_sale_date,
        "best_public_listing_parse_confidence": best_public_listing_parse_confidence,
        "public_listing_market_scope": _public_listing_market_scope(
            public_listing_land_comparables
        ),
        "public_listing_micro_market_confidence": public_listing_micro_market_confidence,
        "public_listing_recency_tier": _public_listing_recency_tier(best_public_listing_sale_date),
        "public_listing_domains": public_listing_domains,
        "public_listing_strategy": str(web_listing_search.get("strategy") or ""),
        "public_listing_selected_search_category": str(
            web_listing_search.get("selected_search_category") or ""
        ),
        "public_listing_selected_search_window_months": web_listing_search.get(
            "selected_search_window_months"
        ),
        "public_listing_query_attempts": _required_list(web_listing_search, "attempts"),
        "used_relaxed_land_comps": bool(comps_payload.get("used_relaxed_land_comps")),
        "used_relaxed_unit_comps": bool(comps_payload.get("used_relaxed_unit_comps")),
        "contextual_verified_candidate_count": contextual_verified_candidate_count,
        "county_reconciled_candidate_count": county_reconciled_candidate_count,
        "qualified_exit_comp_signal": _has_qualified_live_unit_comp_signal(comps_payload),
    }


def _float_assumption(assumptions: JsonObject, key: str, default: float) -> float:
    value = assumptions.get(key)
    if isinstance(value, int | float):
        return float(value)
    return default


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    middle = len(values) // 2
    if len(values) % 2 == 1:
        return values[middle]
    return (values[middle - 1] + values[middle]) / 2.0


def _percentile_value(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * quantile
    lower_index = floor(position)
    upper_index = floor(position + 1)
    if lower_index == upper_index or upper_index >= len(values):
        return values[lower_index]
    lower_value = values[lower_index]
    upper_value = values[upper_index]
    weight = position - lower_index
    return lower_value + ((upper_value - lower_value) * weight)


def _optional_float_assumption(assumptions: JsonObject, key: str) -> float | None:
    value = assumptions.get(key)
    if isinstance(value, int | float):
        return float(value)
    dimensional = assumptions.get("dimensionalStandards")
    if isinstance(dimensional, dict):
        nested_value = dimensional.get(key)
        if isinstance(nested_value, int | float):
            return float(nested_value)
    return None


def _manual_comp_entries(*, raw_value: object, role: str) -> list[JsonObject]:
    if not isinstance(raw_value, list):
        return []
    entries: list[JsonObject] = []
    for raw_item in raw_value:
        if not isinstance(raw_item, dict):
            continue
        sale_price = raw_item.get("salePrice")
        if not isinstance(sale_price, int | float) or float(sale_price) <= 0:
            continue
        lot_size_sqft = raw_item.get("lotSizeSqft")
        units = raw_item.get("units")
        distance_miles = raw_item.get("distanceMiles")
        normalized: JsonObject = {
            "address": str(raw_item.get("address") or "Manual comparable").strip(),
            "sale_price": round(float(sale_price), 2),
            "sale_date": str(raw_item.get("saleDate") or "").strip(),
            "lot_size_sqft": round(float(lot_size_sqft), 2)
            if isinstance(lot_size_sqft, int | float)
            else 0.0,
            "zoning_code": str(raw_item.get("zoningCode") or "").strip(),
            "distance_miles": round(float(distance_miles), 3)
            if isinstance(distance_miles, int | float)
            else 0.0,
            "provider": "user_provided_comp",
            "source_url": str(raw_item.get("sourceUrl") or "").strip()
            or "https://plotlot.local/user-input/comps",
            "user_supplied": True,
            "comp_role": role,
        }
        if role == "land" and normalized["lot_size_sqft"] > 0:
            normalized["price_per_acre"] = round(
                (float(normalized["sale_price"]) / float(normalized["lot_size_sqft"])) * 43_560.0,
                2,
            )
        if role == "exit":
            unit_count = (
                float(units) if isinstance(units, int | float) and float(units) > 0 else 1.0
            )
            normalized["price_per_unit"] = round(float(normalized["sale_price"]) / unit_count, 2)
        entries.append(normalized)
    return entries


def _municipal_applicability(profile: FixtureSiteProfile):
    if profile.municipality == "BMSD":
        return ApplicabilityStatus.REQUIRES_MUNICIPAL_VERIFICATION
    return ApplicabilityStatus.REQUIRES_MUNICIPAL_VERIFICATION


def _event_source_for_execution_mode(execution_mode: ExecutionMode) -> PlotLotEventSource:
    match execution_mode:
        case ExecutionMode.CLI:
            return PlotLotEventSource.CLI
        case ExecutionMode.TUI:
            return PlotLotEventSource.TUI
        case ExecutionMode.WORKER:
            return PlotLotEventSource.WORKER
        case ExecutionMode.API | ExecutionMode.LOCAL:
            return PlotLotEventSource.SYSTEM


async def _resolve_live_ordinance_payload(
    *,
    run_id: RunId,
    request: FixtureDealRunRequest,
    context: ToolContext,
    events: list[PlotLotEvent],
    tool_calls: list[ToolCall],
    municipality: str,
    state: str,
    zoning_code: str,
) -> JsonObject | None:
    if not municipality:
        return None
    query = f"{zoning_code} setbacks density height parking permitted uses".strip()
    fallback_payload = await _fallback_live_ordinance_payload(
        municipality=municipality,
        zoning_code=zoning_code,
    )
    zoning_call = await _tool_result(
        request=ToolExecutionRequest(
            run_id=run_id,
            tool_name="search_zoning_ordinance",
            args={
                "municipality": municipality,
                "query": query,
                "zone_code_boost": zoning_code or None,
                "known_zoning_code": zoning_code or None,
                "limit": 5,
            },
            execution_mode=request.execution_mode,
            source_mode=request.source_mode,
            context=context,
        )
    )
    _append_tool_result(events=events, tool_calls=tool_calls, result=zoning_call)
    if _ordinance_payload_matches_requested_context(
        payload=zoning_call.payload,
        municipality=municipality,
        zoning_code=zoning_code,
    ):
        if _live_ordinance_rules_payload(zoning_call.payload) is not None:
            return zoning_call.payload
        indexed_payload = zoning_call.payload
    else:
        indexed_payload = None
    if _uses_miami21_special_authority(municipality):
        web_call = await _tool_result(
            request=ToolExecutionRequest(
                run_id=run_id,
                tool_name="web_search",
                args={
                    "query": (
                        f'site:miami.gov OR site:miami21.org "{zoning_code}" '
                        '"Miami 21" density intensity setbacks parking'
                    ),
                },
                execution_mode=request.execution_mode,
                source_mode=request.source_mode,
                context=context,
            )
        )
        _append_tool_result(events=events, tool_calls=tool_calls, result=web_call)
        if _required_list(web_call.payload, "results"):
            if (
                fallback_payload is not None
                and _live_ordinance_rules_payload(web_call.payload) is None
            ):
                return {
                    **web_call.payload,
                    "fallback_source": "miami21_web_reference",
                    "requires_official_verification": True,
                    "authority_source_type": "miami21_web_reference",
                    "authority_resolution": "web_reference_fallback",
                    "authority_confidence": "official_web_reference",
                    "authority_is_live": True,
                    "authority_is_official": True,
                    "authority_jurisdiction": municipality,
                }
            return web_call.payload
    if state:
        municode_call = await _tool_result(
            request=ToolExecutionRequest(
                run_id=run_id,
                tool_name="search_municode_live",
                args={
                    "municipality": municipality,
                    "state": state,
                    "query": query,
                    "known_zoning_code": zoning_code or None,
                    "limit": 5,
                },
                execution_mode=request.execution_mode,
                source_mode=request.source_mode,
                context=context,
            )
        )
        _append_tool_result(events=events, tool_calls=tool_calls, result=municode_call)
        if _ordinance_payload_matches_requested_context(
            payload=municode_call.payload,
            municipality=municipality,
            zoning_code=zoning_code,
        ):
            if (
                fallback_payload is not None
                and _live_ordinance_rules_payload(municode_call.payload) is None
            ):
                if indexed_payload is not None:
                    return indexed_payload
                return fallback_payload
            return municode_call.payload
    if indexed_payload is not None:
        if fallback_payload is not None:
            return fallback_payload
        return indexed_payload
    return fallback_payload


async def _fallback_live_ordinance_payload(
    *,
    municipality: str,
    zoning_code: str,
) -> JsonObject | None:
    if not municipality.strip() or not zoning_code.strip():
        return None
    standard = await get_dimensional_standard(municipality, zoning_code)
    if standard is None:
        return None
    is_verified = standard.is_verified_fact_source()
    fallback_source = (
        "verified_dimensional_standard" if is_verified else "staged_dimensional_standard"
    )
    title = f"{municipality} zoning standards for {standard.district_code}"
    summary_parts = [
        f"FAR {standard.far}" if standard.far is not None else None,
        (
            f"density {standard.max_density_units_per_acre} du/ac"
            if standard.max_density_units_per_acre is not None
            else None
        ),
        f"front setback {standard.setback_front_ft} ft"
        if standard.setback_front_ft is not None
        else None,
        f"side setback {standard.setback_side_ft} ft"
        if standard.setback_side_ft is not None
        else None,
        f"rear setback {standard.setback_rear_ft} ft"
        if standard.setback_rear_ft is not None
        else None,
        f"height {standard.max_height_ft} ft" if standard.max_height_ft is not None else None,
    ]
    summary = ", ".join(part for part in summary_parts if part is not None)
    text = (
        f"{title}. {summary}. Source: {standard.source_section_id}."
        if summary
        else f"{title}. Source: {standard.source_section_id}."
    )
    rules: JsonObject = {
        "zoning_district": standard.district_code,
        "source": fallback_source,
        "requires_official_verification": not is_verified,
        "source_section_id": standard.source_section_id,
        "source_url": standard.source_url,
        "authority_source_type": fallback_source,
        "authority_resolution": "local_dimensional_standard_fallback",
        "authority_confidence": (
            "indexed_official_reference" if is_verified else "staged_preliminary"
        ),
        "authority_is_live": False,
        "authority_is_official": is_verified,
        "authority_jurisdiction": municipality,
    }
    field_values = {
        "min_lot_area_sqft": standard.min_lot_area_sqft,
        "min_lot_width_ft": standard.min_lot_width_ft,
        "setback_front_ft": standard.setback_front_ft,
        "setback_side_ft": standard.setback_side_ft,
        "setback_rear_ft": standard.setback_rear_ft,
        "max_height_ft": standard.max_height_ft,
        "max_lot_coverage_pct": standard.max_lot_coverage_pct,
        "far": standard.far,
        "max_density_units_per_acre": standard.max_density_units_per_acre,
    }
    for key, value in field_values.items():
        if value is not None:
            rules[key] = float(value)
    return {
        "status": "success",
        "fallback_source": fallback_source,
        "requires_official_verification": not is_verified,
        "authority_source_type": fallback_source,
        "authority_resolution": "local_dimensional_standard_fallback",
        "authority_confidence": (
            "indexed_official_reference" if is_verified else "staged_preliminary"
        ),
        "authority_is_live": False,
        "authority_is_official": is_verified,
        "authority_jurisdiction": municipality,
        "rules": rules,
        "results": [
            {
                "section": standard.source_section_id or title,
                "section_id": standard.source_section_id or title,
                "title": title,
                "text": text,
                "zone_codes": [standard.district_code],
                "citation": {
                    "url": standard.source_url,
                    "jurisdiction": municipality,
                },
            }
        ],
    }


def _live_property_evidence(
    *,
    run_id: RunId,
    property_payload: JsonObject,
    source_mode: SourceMode,
) -> EvidenceItem:
    county = _county_name(str(property_payload.get("county") or "Unknown"))
    municipality = str(property_payload.get("municipality") or "") or None
    zoning_layer_url = str(property_payload.get("zoning_layer_url") or "").strip()
    return EvidenceItem(
        evidence_id=EvidenceId(f"ev_{run_id}_live_parcel_record"),
        run_id=run_id,
        source_type=EvidenceSourceType.PARCEL_RECORD,
        source_name=f"{county} property record",
        source_url=zoning_layer_url or "https://plotlot.local/property-record",
        source_identifier=str(property_payload.get("folio") or "") or None,
        provider="county_property_appraiser",
        jurisdiction=county,
        county=CountyName(county),
        municipality=municipality,
        freshness_status=FreshnessStatus.FRESH,
        applicability=ApplicabilityStatus.DIRECT,
        normalized_text=(
            f"{property_payload.get('address', 'Subject parcel')} is mapped to zoning "
            f"{property_payload.get('zoning_code', 'unknown')} with "
            f"{property_payload.get('lot_size_sqft', 0)} square feet."
        ),
        structured_payload=property_payload,
        confidence=0.82,
        source_mode=source_mode,
        metadata={"live": True},
    )


def _live_gis_site_context(
    *,
    property_payload: JsonObject,
    source_mode: SourceMode,
) -> JsonObject:
    existing_context = property_payload.get("gis_site_context")
    if isinstance(existing_context, dict) and existing_context:
        return existing_context
    county = _county_name(str(property_payload.get("county") or "Unknown"))
    if county not in {"Miami-Dade", "Broward"}:
        return {}
    municipality = str(property_payload.get("municipality") or "").strip() or None
    return resolve_site_boundary_context(
        county=CountyName(county),
        municipality=municipality,
        source_mode=source_mode,
    )


def _live_gis_site_context_evidence(
    *,
    run_id: RunId,
    property_payload: JsonObject,
    gis_site_context: JsonObject,
    source_mode: SourceMode,
) -> EvidenceItem:
    county = _county_name(str(property_payload.get("county") or "Unknown"))
    municipality = str(property_payload.get("municipality") or "") or None
    warning = str(gis_site_context.get("warning") or "").strip()
    applicability = _gis_context_applicability(gis_site_context)
    normalized_text = (
        warning
        or f"South Florida GIS source selection resolved direct zoning context for {municipality or county}."
    )
    return EvidenceItem(
        evidence_id=EvidenceId(f"ev_{run_id}_live_gis_site_context"),
        run_id=run_id,
        source_type=EvidenceSourceType.GIS_LAYER,
        source_name="South Florida GIS site context",
        source_url="https://plotlot.local/south-florida-gis-site-context",
        source_identifier=str(property_payload.get("folio") or "") or None,
        provider="south_florida_gis",
        jurisdiction=municipality or county,
        county=CountyName(county),
        municipality=municipality,
        freshness_status=FreshnessStatus.REQUIRES_OFFICIAL_VERIFICATION,
        applicability=applicability,
        normalized_text=normalized_text,
        structured_payload=gis_site_context,
        confidence=0.83 if not warning else 0.8,
        source_mode=source_mode,
        metadata={"live": True},
    )


def _gis_context_applicability(gis_site_context: JsonObject) -> ApplicabilityStatus:
    raw_value = str(gis_site_context.get("zoning_record_applicability") or "").strip()
    match raw_value:
        case "direct":
            return ApplicabilityStatus.DIRECT
        case "contextual":
            return ApplicabilityStatus.CONTEXTUAL
        case "not_applicable":
            return ApplicabilityStatus.NOT_APPLICABLE
        case "requires_municipal_verification":
            return ApplicabilityStatus.REQUIRES_MUNICIPAL_VERIFICATION
        case _:
            return ApplicabilityStatus.UNKNOWN


def _live_zoning_record_provider(
    property_payload: JsonObject,
    gis_site_context: JsonObject,
) -> str:
    county = _county_name(str(property_payload.get("county") or "Unknown"))
    authority = str(gis_site_context.get("controlling_zoning_authority") or "").strip()
    if county == "Miami-Dade" and authority == "municipal":
        return "miami_dade_arcgis"
    if county == "Broward" and authority == "county":
        return "broward_geohub"
    return "county_zoning_lookup"


def _live_zoning_record_jurisdiction(
    *,
    county: str,
    municipality: str | None,
    gis_site_context: JsonObject,
) -> str:
    controlling = str(gis_site_context.get("controlling_zoning_jurisdiction") or "").strip()
    if controlling:
        return controlling
    if municipality is not None and municipality.strip():
        return municipality
    return county


def _live_zoning_record_evidence(
    *,
    run_id: RunId,
    property_payload: JsonObject,
    source_mode: SourceMode,
) -> EvidenceItem:
    county = _county_name(str(property_payload.get("county") or "Unknown"))
    municipality = str(property_payload.get("municipality") or "") or None
    gis_site_context = _live_gis_site_context(
        property_payload=property_payload,
        source_mode=source_mode,
    )
    applicability = _gis_context_applicability(gis_site_context)
    provider = _live_zoning_record_provider(property_payload, gis_site_context)
    jurisdiction = _live_zoning_record_jurisdiction(
        county=county,
        municipality=municipality,
        gis_site_context=gis_site_context,
    )
    zoning_code = str(property_payload.get("zoning_code") or "").strip()
    zoning_description = str(property_payload.get("zoning_description") or "").strip()
    zoning_layer_url = str(property_payload.get("zoning_layer_url") or "").strip()
    return EvidenceItem(
        evidence_id=EvidenceId(f"ev_{run_id}_live_zoning_record"),
        run_id=run_id,
        source_type=EvidenceSourceType.ZONING_BOUNDARY,
        source_name=f"{jurisdiction} zoning lookup",
        source_url=zoning_layer_url or "https://plotlot.local/zoning-record",
        source_identifier=zoning_code or None,
        provider=provider,
        jurisdiction=jurisdiction,
        county=CountyName(county),
        municipality=municipality,
        freshness_status=FreshnessStatus.REQUIRES_OFFICIAL_VERIFICATION,
        applicability=applicability,
        normalized_text=f"Live property lookup returned zoning {zoning_code} ({zoning_description}).",
        structured_payload={
            "zoning_code": zoning_code,
            "zoning_description": zoning_description,
            "ordinance_district_code": property_payload.get("ordinance_district_code"),
            "controlling_zoning_authority": gis_site_context.get("controlling_zoning_authority"),
            "controlling_zoning_jurisdiction": gis_site_context.get(
                "controlling_zoning_jurisdiction"
            ),
            "zoning_record_applicability": applicability.value,
        },
        confidence=0.84 if applicability is ApplicabilityStatus.DIRECT else 0.76,
        source_mode=source_mode,
        metadata={"live": True},
    )


def _live_ordinance_evidence(
    *,
    run_id: RunId,
    ordinance_payload: JsonObject,
    property_payload: JsonObject,
    source_mode: SourceMode,
) -> EvidenceItem | None:
    results = _required_list(ordinance_payload, "results")
    if not results:
        return None
    first = results[0]
    citation_value = first.get("citation")
    citation = citation_value if isinstance(citation_value, dict) else {}
    source_url = str(citation.get("url") or "https://library.municode.com/").strip()
    county = _county_name(str(property_payload.get("county") or "Unknown"))
    municipality = str(property_payload.get("municipality") or "") or None
    title = str(
        first.get("title") or first.get("heading") or first.get("section") or "Ordinance section"
    )
    section_id = str(first.get("section") or first.get("section_id") or title)
    text = str(first.get("text") or first.get("snippet") or "").strip()
    return EvidenceItem(
        evidence_id=EvidenceId(f"ev_{run_id}_live_ordinance"),
        run_id=run_id,
        source_type=EvidenceSourceType.ORDINANCE_TEXT,
        source_name=title,
        source_url=source_url,
        source_identifier=section_id,
        provider="ordinance_search",
        jurisdiction=municipality or county,
        county=CountyName(county),
        municipality=municipality,
        freshness_status=FreshnessStatus.REQUIRES_OFFICIAL_VERIFICATION,
        applicability=ApplicabilityStatus.REQUIRES_MUNICIPAL_VERIFICATION,
        raw_excerpt=text[:500] if text else None,
        normalized_text=text[:500] if text else title,
        structured_payload=first,
        confidence=0.68,
        source_mode=source_mode,
        metadata={"live": True},
    )


def _comp_evidence_from_subject(
    *,
    run_id: RunId,
    property_payload: JsonObject,
    comps_payload: JsonObject,
    source_mode: SourceMode,
) -> list[EvidenceItem]:
    county = _county_name(str(property_payload.get("county") or "Unknown"))
    municipality = str(property_payload.get("municipality") or "") or None
    items: list[EvidenceItem] = []
    land_comp_quality = _land_comp_quality_summary(comps_payload)
    for comp_type in ("comparables", "unit_comparables"):
        raw_items = comps_payload.get(comp_type)
        if not isinstance(raw_items, list):
            continue
        for index, raw_item in enumerate(raw_items):
            if not isinstance(raw_item, dict):
                continue
            source_type = (
                EvidenceSourceType.RENTAL_COMP
                if comp_type == "unit_comparables"
                else EvidenceSourceType.MARKET_COMP
            )
            provider = str(raw_item.get("provider") or "county_recorded_sales")
            source_url = str(raw_item.get("source_url") or "https://plotlot.local/market-comps")
            freshness_status = (
                FreshnessStatus.REQUIRES_OFFICIAL_VERIFICATION
                if bool(raw_item.get("user_supplied"))
                else FreshnessStatus.FRESH
            )
            structured_payload: JsonObject = {"comp_type": comp_type, **raw_item}
            provenance_tier = _comp_provenance_tier(
                provider=provider,
                source_url=source_url,
                raw_item=raw_item,
            )
            metadata: JsonObject = {
                "live": True,
                "land_comp_quality": land_comp_quality,
                "provenance_tier": provenance_tier,
            }
            normalized_text = (
                f"{raw_item.get('address', 'Comparable sale')} sold for "
                f"{raw_item.get('sale_price', 0)} on {raw_item.get('sale_date', '')}."
            )
            metadata["comp_quality_status"] = (
                _unit_comp_quality_status(raw_item)
                if comp_type == "unit_comparables"
                else _land_comp_quality_status(raw_item)
            )
            metadata["manual_override_used"] = bool(comps_payload.get("manual_comp_override"))
            score = _comp_qualification_score(raw_item)
            if score is not None:
                structured_payload["qualification_score"] = score
                metadata["qualification_score"] = score
                normalized_text = f"{normalized_text} Qualification score {score:.3f}."
            items.append(
                EvidenceItem(
                    evidence_id=EvidenceId(f"ev_{run_id}_{comp_type}_{index + 1}"),
                    run_id=run_id,
                    source_type=source_type,
                    source_name=f"{county} comparable sale",
                    source_url=source_url,
                    source_identifier=str(raw_item.get("address") or f"{comp_type}_{index + 1}"),
                    provider=provider,
                    jurisdiction=county,
                    county=CountyName(county),
                    municipality=municipality,
                    freshness_status=freshness_status,
                    applicability=ApplicabilityStatus.CONTEXTUAL,
                    normalized_text=normalized_text,
                    structured_payload=structured_payload,
                    confidence=0.74,
                    source_mode=source_mode,
                    metadata=metadata,
                )
            )
    web_listing_search = comps_payload.get("web_listing_search")
    web_listing_candidates = comps_payload.get("web_listing_candidates")
    if isinstance(web_listing_search, dict) and isinstance(web_listing_candidates, list):
        for index, raw_result in enumerate(web_listing_candidates):
            if not isinstance(raw_result, dict):
                continue
            source_url = str(raw_result.get("url") or "https://plotlot.local/web-search")
            title = str(raw_result.get("title") or raw_result.get("address_hint") or source_url)
            normalized_text = str(
                raw_result.get("description") or raw_result.get("address_hint") or title
            )
            candidate_classification = str(raw_result.get("classification") or "unknown")
            candidate_confidence = raw_result.get("confidence")
            items.append(
                EvidenceItem(
                    evidence_id=EvidenceId(f"ev_{run_id}_web_listing_{index + 1}"),
                    run_id=run_id,
                    source_type=EvidenceSourceType.MARKET_COMP,
                    source_name=title,
                    source_url=source_url,
                    source_identifier=source_url,
                    provider="exa_web_search",
                    jurisdiction=county,
                    county=CountyName(county),
                    municipality=municipality,
                    freshness_status=FreshnessStatus.UNKNOWN,
                    applicability=ApplicabilityStatus.CONTEXTUAL,
                    normalized_text=normalized_text,
                    structured_payload={
                        "comp_type": "web_listing_candidate",
                        "query": web_listing_search.get("query"),
                        **raw_result,
                    },
                    confidence=(
                        float(candidate_confidence)
                        if isinstance(candidate_confidence, int | float)
                        else 0.45
                    ),
                    source_mode=source_mode,
                    metadata={
                        "live": True,
                        "candidate_source": "web_search",
                        "listing_candidate": True,
                        "classification": candidate_classification,
                        "land_comp_quality": land_comp_quality,
                        "provenance_tier": "public_listing_parsed",
                    },
                )
            )
    contextual_land_verification = comps_payload.get("contextual_land_listing_verification")
    if isinstance(contextual_land_verification, dict):
        verified_candidates = contextual_land_verification.get("verified_candidates")
        if isinstance(verified_candidates, list):
            for index, raw_result in enumerate(verified_candidates):
                if not isinstance(raw_result, dict):
                    continue
                source_url = str(raw_result.get("url") or "https://plotlot.local/web-contents")
                title = str(raw_result.get("title") or raw_result.get("address_hint") or source_url)
                sale_price = raw_result.get("sale_price")
                lot_size_sqft = raw_result.get("lot_size_sqft")
                price_per_acre = raw_result.get("price_per_acre")
                normalized_text = (
                    f"{title} sold for {sale_price} with lot size {lot_size_sqft} sqft "
                    f"({price_per_acre} per acre)."
                )
                items.append(
                    EvidenceItem(
                        evidence_id=EvidenceId(f"ev_{run_id}_contextual_land_listing_{index + 1}"),
                        run_id=run_id,
                        source_type=EvidenceSourceType.MARKET_COMP,
                        source_name=title,
                        source_url=source_url,
                        source_identifier=source_url,
                        provider="exa_web_contents",
                        jurisdiction=county,
                        county=CountyName(county),
                        municipality=municipality,
                        freshness_status=FreshnessStatus.UNKNOWN,
                        applicability=ApplicabilityStatus.CONTEXTUAL,
                        normalized_text=normalized_text,
                        structured_payload={
                            "comp_type": "contextual_verified_land_listing",
                            **raw_result,
                        },
                        confidence=0.58,
                        source_mode=source_mode,
                        metadata={
                            "live": True,
                            "candidate_source": "web_contents",
                            "listing_candidate": True,
                            "listing_verified": True,
                            "land_comp_quality": land_comp_quality,
                            "provenance_tier": "public_listing_parsed",
                        },
                    )
                )
    contextual_land_reconciliation = comps_payload.get("contextual_land_listing_reconciliation")
    if isinstance(contextual_land_reconciliation, dict):
        reconciled_candidates = contextual_land_reconciliation.get("reconciled_candidates")
        if isinstance(reconciled_candidates, list):
            for index, raw_result in enumerate(reconciled_candidates):
                if not isinstance(raw_result, dict):
                    continue
                source_url = str(
                    raw_result.get("url") or "https://plotlot.local/county-reconciled-listing"
                )
                title = str(raw_result.get("title") or raw_result.get("address_hint") or source_url)
                normalized_text = (
                    f"{title} reconciled against county record at "
                    f"{raw_result.get('county_sale_price')} sale price and "
                    f"{raw_result.get('county_lot_size_sqft')} sqft lot size."
                )
                items.append(
                    EvidenceItem(
                        evidence_id=EvidenceId(
                            f"ev_{run_id}_county_reconciled_land_listing_{index + 1}"
                        ),
                        run_id=run_id,
                        source_type=EvidenceSourceType.MARKET_COMP,
                        source_name=title,
                        source_url=source_url,
                        source_identifier=str(raw_result.get("county_folio") or source_url),
                        provider="county_reconciled_public_listing",
                        jurisdiction=county,
                        county=CountyName(county),
                        municipality=municipality,
                        freshness_status=FreshnessStatus.FRESH,
                        applicability=ApplicabilityStatus.CONTEXTUAL,
                        normalized_text=normalized_text,
                        structured_payload={
                            "comp_type": "county_reconciled_land_listing",
                            **raw_result,
                        },
                        confidence=0.66,
                        source_mode=source_mode,
                        metadata={
                            "live": True,
                            "candidate_source": "county_property_record",
                            "listing_candidate": True,
                            "listing_verified": True,
                            "county_reconciled": True,
                            "land_comp_quality": land_comp_quality,
                            "provenance_tier": "public_listing_county_reconciled",
                        },
                    )
                )
    return items


def _comp_provenance_tier(
    *,
    provider: str,
    source_url: str,
    raw_item: JsonObject,
) -> str:
    provider_key = provider.strip().casefold()
    source_url_key = source_url.strip().casefold()
    if bool(raw_item.get("user_supplied")) or provider_key == "user_provided_comp":
        return "user_override"
    if provider_key == "county_reconciled_public_listing":
        return "public_listing_county_reconciled"
    if provider_key in {"exa_web_search", "exa_web_contents"}:
        return "public_listing_parsed"
    if (
        provider_key in {"county_recorded_sales", "county_property_appraiser"}
        or "arcgis/rest/services" in source_url_key
        or "gisweb.miamidade.gov" in source_url_key
        or "gisweb-adapters.bcpa.net" in source_url_key
        or "maps.co.palm-beach.fl.us" in source_url_key
    ):
        return "official_record"
    if "zillow.com" in source_url_key or "redfin.com" in source_url_key:
        return "public_listing_parsed"
    if source_url_key.startswith("https://plotlot.local/"):
        return "local_placeholder"
    return "unknown"


def _live_cost_assumption_payload(
    *,
    property_payload: JsonObject,
    underwriting_profile: JsonObject,
    pro_forma_payload: JsonObject,
) -> JsonObject:
    county = str(property_payload.get("county") or "").strip()
    municipality = str(property_payload.get("municipality") or "").strip()
    nested_result = pro_forma_payload.get("result")
    result = nested_result if isinstance(nested_result, dict) else pro_forma_payload
    overridden_fields = _string_list(underwriting_profile.get("overridden_fields"))
    income_inferred_fields = _string_list(underwriting_profile.get("income_inferred_fields"))
    return {
        "market": result.get("market") or underwriting_profile.get("market"),
        "source": underwriting_profile.get("source"),
        "state": underwriting_profile.get("state"),
        "county": county,
        "municipality": municipality,
        "construction_cost_psf": result.get(
            "construction_cost_psf",
            underwriting_profile.get("construction_cost_psf"),
        ),
        "avg_unit_size_sqft": result.get(
            "avg_unit_size_sqft",
            underwriting_profile.get("avg_unit_size_sqft"),
        ),
        "soft_cost_pct": result.get("soft_cost_pct", underwriting_profile.get("soft_cost_pct")),
        "builder_margin_pct": result.get(
            "builder_margin_pct",
            underwriting_profile.get("builder_margin_pct"),
        ),
        "impact_fees_per_unit": result.get(
            "impact_fees_per_unit",
            underwriting_profile.get("impact_fees_per_unit"),
        ),
        "adv_source": result.get("adv_source", ""),
        "adv_per_unit": result.get("adv_per_unit", underwriting_profile.get("adv_per_unit")),
        "monthly_rent_per_unit": underwriting_profile.get("monthly_rent_per_unit"),
        "vacancy_pct": underwriting_profile.get("vacancy_pct"),
        "operating_expense_pct": underwriting_profile.get("operating_expense_pct"),
        "cap_rate": underwriting_profile.get("cap_rate"),
        "income_assumption_source": underwriting_profile.get("income_assumption_source", ""),
        "overridden_fields": overridden_fields,
        "income_inferred_fields": income_inferred_fields,
        "requires_income_assumption_verification": bool(income_inferred_fields),
        "requires_official_verification": bool(
            underwriting_profile.get("requires_official_verification")
        ),
    }


def _manual_dimensional_assumptions_payload(assumptions: JsonObject) -> JsonObject | None:
    field_map = {
        "minLotAreaSf": "min_lot_area_sf",
        "maxDensityUnitsPerAcre": "max_density_units_per_acre",
        "minLotFrontageFt": "min_lot_frontage_ft",
        "lotFrontageFt": "lot_frontage_ft",
        "lotDepthFt": "lot_depth_ft",
        "frontSetbackFt": "front_setback_ft",
        "sideSetbackFt": "side_setback_ft",
        "rearSetbackFt": "rear_setback_ft",
        "maxLotCoveragePct": "max_lot_coverage_pct",
        "maxHeightFt": "max_height_ft",
        "maxStories": "max_stories",
        "waterSetbackFt": "water_setback_ft",
        "accessorySeparationFt": "accessory_separation_ft",
    }
    payload: JsonObject = {}
    for assumption_key, payload_key in field_map.items():
        value = _optional_float_assumption(assumptions, assumption_key)
        if value is not None:
            payload[payload_key] = value
    if not payload:
        return None
    payload["source"] = "user_input"
    payload["requires_official_verification"] = True
    return payload


def _live_ordinance_rules_payload(ordinance_payload: JsonObject) -> JsonObject | None:
    top_level_rules = ordinance_payload.get("rules")
    if isinstance(top_level_rules, dict) and top_level_rules:
        return dict(top_level_rules)
    results = _required_list(ordinance_payload, "results")
    if not results:
        return None
    first = results[0]
    nested_rules = first.get("rules")
    if not isinstance(nested_rules, dict) or not nested_rules:
        return None
    normalized_rules = dict(nested_rules)
    if "source_section_id" not in normalized_rules:
        normalized_rules["source_section_id"] = str(
            first.get("section_id") or first.get("section") or first.get("title") or ""
        )
    citation = first.get("citation")
    if isinstance(citation, dict) and "source_url" not in normalized_rules:
        normalized_rules["source_url"] = str(citation.get("url") or "").strip()
    if "source" not in normalized_rules:
        normalized_rules["source"] = "ordinance_search"
    if "requires_official_verification" not in normalized_rules:
        normalized_rules["requires_official_verification"] = bool(
            ordinance_payload.get("requires_official_verification")
        )
    for field_name in (
        "authority_source_type",
        "authority_resolution",
        "authority_confidence",
        "authority_jurisdiction",
        "authority_is_live",
        "authority_is_official",
    ):
        if field_name not in normalized_rules and field_name in ordinance_payload:
            normalized_rules[field_name] = ordinance_payload.get(field_name)
    source_name = str(normalized_rules.get("source") or "").strip()
    source_url = str(normalized_rules.get("source_url") or "").strip()
    authority_source_type = str(normalized_rules.get("authority_source_type") or "").strip()
    if not authority_source_type:
        inferred_source_type = source_name or "ordinance_search"
        normalized_rules["authority_source_type"] = inferred_source_type
        authority_source_type = inferred_source_type
    if "authority_resolution" not in normalized_rules:
        normalized_rules["authority_resolution"] = "query_result"
    if "authority_confidence" not in normalized_rules:
        if authority_source_type == "municode_live_table":
            normalized_rules["authority_confidence"] = "official_live_preliminary_extract"
        elif source_url:
            normalized_rules["authority_confidence"] = "indexed_official_reference"
        else:
            normalized_rules["authority_confidence"] = "unknown"
    if "authority_is_live" not in normalized_rules:
        normalized_rules["authority_is_live"] = authority_source_type in {
            "municode_live_search",
            "municode_live_table",
            "miami21_web_reference",
        }
    if "authority_is_official" not in normalized_rules:
        normalized_rules["authority_is_official"] = bool(source_url)
    return normalized_rules


def _live_manual_dimensional_evidence(
    *,
    run_id: RunId,
    property_payload: JsonObject,
    manual_dimensional_payload: JsonObject,
    source_mode: SourceMode,
) -> EvidenceItem:
    county = _county_name(str(property_payload.get("county") or "Unknown"))
    municipality = str(property_payload.get("municipality") or "") or None
    zoning_code = str(property_payload.get("zoning_code") or "").strip() or "unknown district"
    summary_parts = [
        f"lot area minimum {manual_dimensional_payload.get('min_lot_area_sf')} sf"
        if manual_dimensional_payload.get("min_lot_area_sf") is not None
        else None,
        f"density {manual_dimensional_payload.get('max_density_units_per_acre')} du/ac"
        if manual_dimensional_payload.get("max_density_units_per_acre") is not None
        else None,
        f"minimum frontage {manual_dimensional_payload.get('min_lot_frontage_ft')} ft"
        if manual_dimensional_payload.get("min_lot_frontage_ft") is not None
        else None,
        f"assumed lot frontage {manual_dimensional_payload.get('lot_frontage_ft')} ft"
        if manual_dimensional_payload.get("lot_frontage_ft") is not None
        else None,
        f"front setback {manual_dimensional_payload.get('front_setback_ft')} ft"
        if manual_dimensional_payload.get("front_setback_ft") is not None
        else None,
        f"side setback {manual_dimensional_payload.get('side_setback_ft')} ft"
        if manual_dimensional_payload.get("side_setback_ft") is not None
        else None,
        f"rear setback {manual_dimensional_payload.get('rear_setback_ft')} ft"
        if manual_dimensional_payload.get("rear_setback_ft") is not None
        else None,
        f"lot coverage {manual_dimensional_payload.get('max_lot_coverage_pct')}%"
        if manual_dimensional_payload.get("max_lot_coverage_pct") is not None
        else None,
        f"maximum height {manual_dimensional_payload.get('max_height_ft')} ft"
        if manual_dimensional_payload.get("max_height_ft") is not None
        else None,
        f"maximum stories {manual_dimensional_payload.get('max_stories')}"
        if manual_dimensional_payload.get("max_stories") is not None
        else None,
        f"water setback {manual_dimensional_payload.get('water_setback_ft')} ft"
        if manual_dimensional_payload.get("water_setback_ft") is not None
        else None,
        f"accessory separation {manual_dimensional_payload.get('accessory_separation_ft')} ft"
        if manual_dimensional_payload.get("accessory_separation_ft") is not None
        else None,
    ]
    summary = ", ".join(part for part in summary_parts if part is not None)
    return EvidenceItem(
        evidence_id=EvidenceId(f"ev_{run_id}_manual_dimensional_standards"),
        run_id=run_id,
        source_type=EvidenceSourceType.USER_ASSUMPTION,
        source_name="User-supplied dimensional standards",
        source_url="https://plotlot.local/user-input/dimensional-standards",
        source_identifier=zoning_code,
        provider="plotlot_user_input",
        jurisdiction=municipality or county,
        county=CountyName(county),
        municipality=municipality,
        freshness_status=FreshnessStatus.REQUIRES_OFFICIAL_VERIFICATION,
        applicability=ApplicabilityStatus.CONTEXTUAL,
        normalized_text=(
            f"User supplied dimensional standards for {zoning_code}: {summary}."
            if summary
            else f"User supplied dimensional standards for {zoning_code}."
        ),
        structured_payload=manual_dimensional_payload,
        confidence=0.95,
        source_mode=source_mode,
        metadata={"live": True, "user_supplied": True},
    )


def _live_cost_assumption_evidence(
    *,
    run_id: RunId,
    property_payload: JsonObject,
    cost_assumptions: JsonObject,
    source_mode: SourceMode,
) -> EvidenceItem:
    county = _county_name(str(property_payload.get("county") or "Unknown"))
    municipality = str(property_payload.get("municipality") or "") or None
    market = str(cost_assumptions.get("market") or "Regional cost model")
    source = str(cost_assumptions.get("source") or "regional_default")
    source_url = f"https://plotlot.local/cost-model/{source}"
    freshness = (
        FreshnessStatus.REQUIRES_OFFICIAL_VERIFICATION
        if bool(cost_assumptions.get("requires_official_verification"))
        else FreshnessStatus.UNKNOWN
    )
    return EvidenceItem(
        evidence_id=EvidenceId(f"ev_{run_id}_live_cost_assumptions"),
        run_id=run_id,
        source_type=EvidenceSourceType.COST_ASSUMPTION_CONFIG,
        source_name=f"{market} cost assumptions",
        source_url=source_url,
        source_identifier=source,
        provider="plotlot_cost_model",
        jurisdiction=municipality or county,
        county=CountyName(county),
        municipality=municipality,
        freshness_status=freshness,
        applicability=ApplicabilityStatus.CONTEXTUAL,
        normalized_text=(
            f"{market} cost model uses {cost_assumptions.get('construction_cost_psf')} hard cost psf, "
            f"{cost_assumptions.get('soft_cost_pct')}% soft costs, "
            f"{cost_assumptions.get('builder_margin_pct')}% builder margin, and "
            f"{cost_assumptions.get('impact_fees_per_unit')} impact fees per unit. "
            f"Income assumptions use rent {cost_assumptions.get('monthly_rent_per_unit')}, "
            f"vacancy {cost_assumptions.get('vacancy_pct')}, "
            f"opex {cost_assumptions.get('operating_expense_pct')}, and "
            f"cap rate {cost_assumptions.get('cap_rate')}."
        ),
        structured_payload=cost_assumptions,
        confidence=0.7,
        source_mode=source_mode,
        metadata={"live": True},
    )


def _underwriting_mode_payload(
    *,
    mode: str,
    status: str,
    reason: str,
    source_artifacts: list[str],
    pricing_source: str = "auto",
) -> JsonObject:
    return {
        "mode": mode,
        "status": status,
        "reason": reason,
        "source_artifacts": source_artifacts,
        "pricing_source": pricing_source,
    }


async def _live_feasibility_inputs(
    *,
    property_payload: JsonObject,
    assumptions: JsonObject,
    ordinance_rules: JsonObject,
) -> LiveFeasibilityResolution | None:
    lot_area = float(property_payload.get("lot_size_sqft") or 0.0)
    max_far = assumptions.get("maxFar")
    max_units = assumptions.get("maxUnits")
    max_density_units_per_acre = _optional_float_assumption(assumptions, "maxDensityUnitsPerAcre")
    min_lot_area_sqft = _optional_float_assumption(assumptions, "minLotAreaSf")
    ordinance_density_units_per_acre = ordinance_rules.get("max_density_units_per_acre")
    ordinance_min_lot_area_sqft = ordinance_rules.get("min_lot_area_sqft")
    property_lot_dimensions = str(property_payload.get("lot_dimensions") or "").strip()
    parsed_frontage_ft, parsed_depth_ft = parse_lot_dimensions(property_lot_dimensions)
    geometry_frontage_ft, geometry_depth_ft = derive_lot_dimensions_from_parcel_geometry(
        property_payload.get("parcel_geometry")
    )
    standard_defaults: DistrictDimensionalStandard | None = None
    warning: str | None = None
    if not isinstance(max_units, int | float) and lot_area > 0:
        if isinstance(max_density_units_per_acre, float) and max_density_units_per_acre > 0:
            max_units = floor((lot_area / 43_560.0) * max_density_units_per_acre)
        elif isinstance(min_lot_area_sqft, float) and min_lot_area_sqft > 0:
            max_units = floor(lot_area / min_lot_area_sqft)
        elif (
            isinstance(ordinance_density_units_per_acre, int | float)
            and float(ordinance_density_units_per_acre) > 0
        ):
            max_units = floor((lot_area / 43_560.0) * float(ordinance_density_units_per_acre))
        elif (
            isinstance(ordinance_min_lot_area_sqft, int | float)
            and float(ordinance_min_lot_area_sqft) > 0
        ):
            max_units = floor(lot_area / float(ordinance_min_lot_area_sqft))
    if not isinstance(max_far, int | float):
        ordinance_far = ordinance_rules.get("far")
        if isinstance(ordinance_far, int | float):
            max_far = float(ordinance_far)
    if (
        not isinstance(max_far, int | float) or not isinstance(max_units, int | float)
    ) and lot_area > 0:
        standard = await _lookup_live_dimensional_standard(property_payload=property_payload)
        if standard is not None:
            standard_defaults = standard
            max_far = standard.far
            if (
                standard.max_density_units_per_acre is not None
                and standard.max_density_units_per_acre > 0
            ):
                max_units = floor((lot_area / 43_560.0) * standard.max_density_units_per_acre)
            elif standard.min_lot_area_sqft is not None and standard.min_lot_area_sqft > 0:
                max_units = floor(lot_area / standard.min_lot_area_sqft)
            if not standard.is_verified_fact_source():
                warning = _preliminary_live_dimensional_standard_warning(
                    municipality=str(property_payload.get("municipality") or "").strip(),
                    district_code=str(
                        property_payload.get("ordinance_district_code")
                        or property_payload.get("zoning_code")
                        or ""
                    ).strip(),
                )
        else:
            preliminary = _lookup_preliminary_live_dimensional_standard(
                property_payload=property_payload
            )
            if preliminary is not None:
                standard_defaults = preliminary
                max_far = preliminary.far
                if (
                    preliminary.max_density_units_per_acre is not None
                    and preliminary.max_density_units_per_acre > 0
                ):
                    max_units = floor(
                        (lot_area / 43_560.0) * preliminary.max_density_units_per_acre
                    )
                elif (
                    preliminary.min_lot_area_sqft is not None and preliminary.min_lot_area_sqft > 0
                ):
                    max_units = floor(lot_area / preliminary.min_lot_area_sqft)
                warning = _preliminary_live_dimensional_standard_warning(
                    municipality=str(property_payload.get("municipality") or "").strip(),
                    district_code=str(
                        property_payload.get("ordinance_district_code")
                        or property_payload.get("zoning_code")
                        or ""
                    ).strip(),
                )
    used_ordinance_rules = False
    if (
        warning is None
        and bool(ordinance_rules)
        and bool(ordinance_rules.get("requires_official_verification"))
        and (isinstance(max_far, int | float) or isinstance(max_units, int | float))
    ):
        warning = (
            "Feasibility used ordinance-derived dimensional defaults from the live zoning search; "
            "verify the current municipal code section before relying on the capacity study."
        )
    feasibility_inputs: JsonObject = {
        "lot_area_sf": lot_area,
        "efficiency_factor": _float_assumption(assumptions, "efficiencyFactor", 0.85),
        "avg_unit_size_sf": _float_assumption(assumptions, "avgUnitSizeSf", 850.0),
        "parking_spaces_per_unit": _float_assumption(assumptions, "parkingSpacesPerUnit", 1.5),
    }
    if isinstance(max_far, int | float):
        feasibility_inputs["max_far"] = float(max_far)
    if isinstance(max_units, int | float):
        feasibility_inputs["max_units"] = int(max_units)
    if (
        _optional_float_assumption(assumptions, "lotFrontageFt") is None
        and parsed_frontage_ft is not None
        and parsed_frontage_ft > 0
    ):
        feasibility_inputs["lot_frontage_ft"] = parsed_frontage_ft
    elif (
        _optional_float_assumption(assumptions, "lotFrontageFt") is None
        and geometry_frontage_ft is not None
        and geometry_frontage_ft > 0
    ):
        feasibility_inputs["lot_frontage_ft"] = geometry_frontage_ft
        warning = (
            "Feasibility estimated lot frontage from parcel geometry; confirm surveyed parcel dimensions "
            "before relying on setback-envelope math."
        )
    if (
        _optional_float_assumption(assumptions, "lotDepthFt") is None
        and parsed_depth_ft is not None
        and parsed_depth_ft > 0
    ):
        feasibility_inputs["lot_depth_ft"] = parsed_depth_ft
    elif (
        _optional_float_assumption(assumptions, "lotDepthFt") is None
        and geometry_depth_ft is not None
        and geometry_depth_ft > 0
    ):
        feasibility_inputs["lot_depth_ft"] = geometry_depth_ft
        if warning is None:
            warning = (
                "Feasibility estimated lot depth from parcel geometry; confirm surveyed parcel dimensions "
                "before relying on setback-envelope math."
            )
    if (
        _optional_float_assumption(assumptions, "lotFrontageFt") is None
        and "lot_frontage_ft" not in feasibility_inputs
        and (min_lot_frontage_ft := _optional_float_assumption(assumptions, "minLotFrontageFt"))
        is not None
        and min_lot_frontage_ft > 0
    ):
        feasibility_inputs["lot_frontage_ft"] = min_lot_frontage_ft
        warning = (
            "Feasibility used the user-supplied minimum frontage as a conservative frontage proxy; "
            "confirm the actual parcel frontage before relying on setback-envelope math."
        )
    if (
        _optional_float_assumption(assumptions, "lotFrontageFt") is None
        and "lot_frontage_ft" not in feasibility_inputs
        and standard_defaults is not None
        and standard_defaults.is_verified_fact_source()
        and standard_defaults.min_lot_width_ft is not None
        and standard_defaults.min_lot_width_ft > 0
    ):
        feasibility_inputs["lot_frontage_ft"] = standard_defaults.min_lot_width_ft
        warning = (
            "Feasibility used the verified district minimum lot width as a conservative frontage proxy; "
            "confirm the actual parcel frontage before relying on setback-envelope math."
        )
    for assumption_key, payload_key in (
        ("lotFrontageFt", "lot_frontage_ft"),
        ("lotDepthFt", "lot_depth_ft"),
        ("frontSetbackFt", "setback_front_ft"),
        ("sideSetbackFt", "setback_side_ft"),
        ("rearSetbackFt", "setback_rear_ft"),
        ("maxLotCoveragePct", "max_lot_coverage_pct"),
    ):
        value = _optional_float_assumption(assumptions, assumption_key)
        if value is None and standard_defaults is not None:
            match payload_key:
                case "setback_front_ft":
                    value = standard_defaults.setback_front_ft
                case "setback_side_ft":
                    value = standard_defaults.setback_side_ft
                case "setback_rear_ft":
                    value = standard_defaults.setback_rear_ft
                case "max_lot_coverage_pct":
                    value = standard_defaults.max_lot_coverage_pct
                case _:
                    value = None
        if value is None and payload_key not in feasibility_inputs:
            match payload_key:
                case "lot_frontage_ft":
                    value = ordinance_rules.get("min_lot_width_ft")
                case "setback_front_ft":
                    value = ordinance_rules.get("setback_front_ft")
                case "setback_side_ft":
                    value = ordinance_rules.get("setback_side_ft")
                case "setback_rear_ft":
                    value = ordinance_rules.get("setback_rear_ft")
                case "max_lot_coverage_pct":
                    value = ordinance_rules.get("max_lot_coverage_pct")
                case _:
                    value = None
        if value is not None:
            feasibility_inputs[payload_key] = value
            if payload_key in {
                "setback_front_ft",
                "setback_side_ft",
                "setback_rear_ft",
                "max_lot_coverage_pct",
            } and not isinstance(_optional_float_assumption(assumptions, assumption_key), float):
                used_ordinance_rules = True
    if (
        warning is None
        and used_ordinance_rules
        and bool(ordinance_rules.get("requires_official_verification"))
    ):
        warning = (
            "Feasibility used ordinance-derived dimensional defaults from the live zoning search; "
            "verify the current municipal code section before relying on the capacity study."
        )
    has_area_control = any(
        key in feasibility_inputs for key in ("max_far", "max_lot_coverage_pct")
    ) or all(
        key in feasibility_inputs
        for key in ("lot_frontage_ft", "setback_front_ft", "setback_side_ft", "setback_rear_ft")
    )
    if "setback_front_ft" in feasibility_inputs and "lot_frontage_ft" not in feasibility_inputs:
        warning = (
            "Feasibility received setbacks without lot frontage or depth; envelope math is partial until parcel "
            "dimensions are confirmed."
        )
    if "setback_front_ft" in feasibility_inputs and "setback_rear_ft" not in feasibility_inputs:
        warning = (
            "Feasibility received front and side setbacks without a rear setback; lot-coverage limits still apply, "
            "but the setback envelope remains incomplete."
        )
    if lot_area <= 0 or not isinstance(max_units, int | float) or not has_area_control:
        return None
    return LiveFeasibilityResolution(
        inputs=feasibility_inputs,
        warning=warning,
    )


async def _lookup_live_dimensional_standard(
    *,
    property_payload: JsonObject,
) -> DistrictDimensionalStandard | None:
    municipality = str(property_payload.get("municipality") or "").strip()
    if not municipality:
        return None
    candidate_codes = [
        str(property_payload.get("ordinance_district_code") or "").strip(),
        str(property_payload.get("zoning_code") or "").strip(),
    ]
    seen: set[str] = set()
    for code in candidate_codes:
        normalized = code.upper()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        standard = await get_dimensional_standard(municipality, normalized)
        if standard is not None:
            return _prefer_more_complete_verified_standard(
                municipality=municipality,
                district_code=normalized,
                standard=standard,
            )
    return None


def _prefer_more_complete_verified_standard(
    *,
    municipality: str,
    district_code: str,
    standard: DistrictDimensionalStandard,
) -> DistrictDimensionalStandard:
    if not standard.is_verified_fact_source():
        return standard
    if standard.far is not None:
        return standard
    fixture_standard = get_dimensional_standard_from_fixture(municipality, district_code)
    if fixture_standard is None or not fixture_standard.is_verified_fact_source():
        return standard
    if fixture_standard.far is None:
        return standard
    return fixture_standard


def _lookup_preliminary_live_dimensional_standard(
    *,
    property_payload: JsonObject,
) -> DistrictDimensionalStandard | None:
    municipality = str(property_payload.get("municipality") or "").strip()
    zoning_code = str(
        property_payload.get("ordinance_district_code") or property_payload.get("zoning_code") or ""
    ).strip()
    if not _uses_miami21_special_authority(municipality) or not zoning_code:
        return None
    return get_dimensional_standard_from_fixture(municipality, zoning_code)


def _preliminary_live_dimensional_standard_warning(
    *,
    municipality: str,
    district_code: str,
) -> str:
    clean_municipality = municipality or "the selected municipality"
    clean_district = district_code or "the selected district"
    if _uses_miami21_special_authority(clean_municipality):
        return (
            f"Feasibility used preliminary Miami21 zoning standards for {clean_municipality} "
            f"{clean_district}; verify the current municipal development standards table "
            "before relying on the capacity study."
        )
    return (
        f"Feasibility used preliminary staged zoning standards for {clean_municipality} "
        f"{clean_district}; verify the current municipal development standards table "
        "before relying on the capacity study."
    )


def _normalize_web_listing_artifacts(comps_payload: JsonObject) -> JsonObject:
    web_listing_search = comps_payload.get("web_listing_search")
    web_listing_candidates = comps_payload.get("web_listing_candidates")
    if not isinstance(web_listing_search, dict) or not isinstance(web_listing_candidates, list):
        return comps_payload

    land_candidate_count = 0
    improved_candidate_count = 0
    for candidate in web_listing_candidates:
        if not isinstance(candidate, dict):
            continue
        classification = str(candidate.get("classification") or "unknown")
        match classification:
            case "likely_vacant_land":
                land_candidate_count += 1
            case "likely_improved_sale":
                improved_candidate_count += 1
            case _:
                continue

    normalized_search = dict(web_listing_search)
    normalized_search.setdefault("land_candidate_count", land_candidate_count)
    normalized_search.setdefault("improved_candidate_count", improved_candidate_count)
    comps_payload["web_listing_search"] = normalized_search
    return comps_payload


async def _merge_browser_listing_capture(
    *,
    run_id: RunId,
    request: FixtureDealRunRequest,
    context: ToolContext,
    events: list[PlotLotEvent],
    tool_calls: list[ToolCall],
    property_payload: JsonObject,
    comps_payload: JsonObject,
) -> JsonObject:
    if request.source_mode is not SourceMode.LIVE or _has_direct_land_comp_signal(comps_payload):
        return comps_payload
    address = str(property_payload.get("address") or request.address).strip()
    county = str(property_payload.get("county") or "").strip()
    if not address or not county:
        return comps_payload
    browser_call = await _tool_result(
        request=ToolExecutionRequest(
            run_id=run_id,
            tool_name="capture_public_listing_comps",
            args={
                "address": address,
                "county": county,
                "municipality": str(property_payload.get("municipality") or "").strip() or None,
                "state": "FL",
                "lot_size_sqft": float(property_payload.get("lot_size_sqft") or 0.0),
                "zoning_code": str(
                    property_payload.get("ordinance_district_code")
                    or property_payload.get("zoning_code")
                    or ""
                ).strip()
                or None,
            },
            execution_mode=request.execution_mode,
            source_mode=request.source_mode,
            context=context,
        )
    )
    _append_tool_result(events=events, tool_calls=tool_calls, result=browser_call)
    browser_payload = browser_call.payload
    browser_candidates = browser_payload.get("candidates")
    if not isinstance(browser_candidates, list) or not browser_candidates:
        return comps_payload
    existing_candidates = comps_payload.get("web_listing_candidates")
    merged_candidates = list(existing_candidates) if isinstance(existing_candidates, list) else []
    merged_candidates.extend(
        candidate for candidate in browser_candidates if isinstance(candidate, dict)
    )
    comps_payload["browser_listing_capture"] = browser_payload
    comps_payload["browser_listing_candidates"] = browser_candidates
    comps_payload["web_listing_candidates"] = rank_listing_candidates(merged_candidates)
    web_listing_search = comps_payload.get("web_listing_search")
    normalized_search = dict(web_listing_search) if isinstance(web_listing_search, dict) else {}
    normalized_search["browser_candidate_count"] = len(
        [candidate for candidate in browser_candidates if isinstance(candidate, dict)]
    )
    normalized_search["browser_capture_status"] = str(browser_payload.get("status") or "")
    normalized_search["browser_capture_provider"] = str(browser_payload.get("provider") or "")
    comps_payload["web_listing_search"] = normalized_search
    return _normalize_web_listing_artifacts(comps_payload)


def _derive_public_listing_land_comp_artifacts(comps_payload: JsonObject) -> JsonObject:
    contextual_land_reconciliation = _required_dict(
        comps_payload,
        "contextual_land_listing_reconciliation",
    )
    contextual_land_verification = _required_dict(
        comps_payload,
        "contextual_land_listing_verification",
    )

    public_listing_land_comparables: list[JsonObject] = []
    reconciled_candidates = _required_list(contextual_land_reconciliation, "reconciled_candidates")
    if reconciled_candidates:
        for raw_candidate in reconciled_candidates:
            source_url = str(raw_candidate.get("url") or "").strip()
            public_listing_land_comparables.append(
                {
                    "address": str(
                        raw_candidate.get("county_address")
                        or raw_candidate.get("address_hint")
                        or raw_candidate.get("title")
                        or ""
                    ).strip(),
                    "sale_price": raw_candidate.get("county_sale_price"),
                    "sale_date": raw_candidate.get("county_sale_date")
                    or raw_candidate.get("sale_date"),
                    "lot_size_sqft": raw_candidate.get("county_lot_size_sqft"),
                    "price_per_acre": raw_candidate.get("county_price_per_acre"),
                    "source_url": source_url,
                    "source_domain": _source_domain(source_url),
                    "provider": "public_listing_county_reconciled",
                    "verification_status": "county_reconciled",
                    "listing_title": raw_candidate.get("title"),
                    "county_folio": raw_candidate.get("county_folio"),
                    "fit_score": raw_candidate.get("fit_score"),
                    "lot_size_variance_ratio": raw_candidate.get("lot_size_variance_ratio"),
                    "municipality": raw_candidate.get("municipality"),
                    "municipality_match": raw_candidate.get("municipality_match"),
                    "zip_code": raw_candidate.get("zip_code"),
                    "zip_match": raw_candidate.get("zip_match"),
                    "parsing_confidence": raw_candidate.get("parsing_confidence"),
                }
            )
    else:
        verified_candidates = _required_list(contextual_land_verification, "verified_candidates")
        for raw_candidate in verified_candidates:
            if bool(raw_candidate.get("county_reconciliation_required")):
                continue
            source_url = str(raw_candidate.get("url") or "").strip()
            public_listing_land_comparables.append(
                {
                    "address": str(
                        raw_candidate.get("address_hint") or raw_candidate.get("title") or ""
                    ).strip(),
                    "sale_price": raw_candidate.get("sale_price"),
                    "sale_date": raw_candidate.get("sale_date"),
                    "lot_size_sqft": raw_candidate.get("lot_size_sqft"),
                    "price_per_acre": raw_candidate.get("price_per_acre"),
                    "source_url": source_url,
                    "source_domain": _source_domain(source_url),
                    "provider": "public_listing_contextual",
                    "verification_status": "contextual_verified",
                    "listing_title": raw_candidate.get("title"),
                    "fit_score": raw_candidate.get("fit_score"),
                    "lot_size_variance_ratio": raw_candidate.get("lot_size_variance_ratio"),
                    "municipality": raw_candidate.get("municipality"),
                    "municipality_match": raw_candidate.get("municipality_match"),
                    "zip_code": raw_candidate.get("zip_code"),
                    "zip_match": raw_candidate.get("zip_match"),
                    "parsing_confidence": raw_candidate.get("parsing_confidence"),
                }
            )

    if public_listing_land_comparables:
        comps_payload["public_listing_land_comparables"] = public_listing_land_comparables
    return comps_payload


def _uses_miami21_special_authority(municipality: str) -> bool:
    return municipality.strip().casefold() == "miami"


def _ordinance_payload_matches_requested_context(
    *,
    payload: JsonObject,
    municipality: str,
    zoning_code: str,
) -> bool:
    results = _required_list(payload, "results")
    if not results:
        return False
    municipality_key = municipality.strip().casefold()
    zoning_key = zoning_code.strip().upper()
    for result in results:
        citation = result.get("citation")
        jurisdiction = ""
        if isinstance(citation, dict):
            jurisdiction = str(citation.get("jurisdiction") or "").strip().casefold()
        title = str(result.get("title") or result.get("heading") or "").upper()
        text = str(result.get("text") or result.get("snippet") or "").upper()
        zone_codes = result.get("zone_codes")
        zone_code_list = (
            [str(item).upper() for item in zone_codes] if isinstance(zone_codes, list) else []
        )
        if _uses_miami21_special_authority(municipality):
            municipality_matches = not jurisdiction or (
                "miami" in jurisdiction and "unincorporated" not in jurisdiction
            )
        else:
            municipality_matches = bool(jurisdiction) and municipality_key in jurisdiction
        zoning_matches = (
            not zoning_key
            or zoning_key in zone_code_list
            or zoning_key in title
            or zoning_key in text
        )
        if municipality_matches and zoning_matches:
            return True
    return False


def _live_noi_inputs(
    *,
    property_payload: JsonObject,
    underwriting_profile: JsonObject,
    feasibility_payload: JsonObject,
) -> LiveNoiResolution:
    monthly_rent = underwriting_profile.get("monthly_rent_per_unit")
    vacancy_pct = underwriting_profile.get("vacancy_pct")
    operating_expense_pct = underwriting_profile.get("operating_expense_pct")
    cap_rate = underwriting_profile.get("cap_rate")
    if (
        not isinstance(monthly_rent, int | float)
        or not isinstance(vacancy_pct, int | float)
        or not isinstance(operating_expense_pct, int | float)
        or not isinstance(cap_rate, int | float)
    ):
        return LiveNoiResolution(inputs=None)
    assumptions = _required_dict(underwriting_profile, "assumptions_snapshot")
    unit_count = assumptions.get("unitCount")
    if not isinstance(unit_count, int | float):
        unit_count = property_payload.get("living_units")
    if isinstance(unit_count, int | float) and int(unit_count) <= 0:
        unit_count = None
    if not isinstance(unit_count, int | float):
        inferred_unit_count = _infer_vacant_single_family_unit_count(property_payload)
        if isinstance(inferred_unit_count, int) and inferred_unit_count > 0:
            unit_count = inferred_unit_count
    if not isinstance(unit_count, int | float):
        unit_count = _payload_number(feasibility_payload, "estimated_units")
    if not isinstance(unit_count, int | float) or int(unit_count) <= 0:
        return LiveNoiResolution(inputs=None)
    warning: str | None = None
    inferred_fields = _string_list(underwriting_profile.get("income_inferred_fields"))
    if inferred_fields:
        warning = (
            "NOI valuation used market underwriting defaults for "
            f"{', '.join(inferred_fields)}; verify rent, vacancy, opex, "
            "and cap rate before relying on income-approach pricing."
        )
    return LiveNoiResolution(
        inputs={
            "unit_count": int(unit_count),
            "monthly_rent_per_unit": float(monthly_rent),
            "vacancy_pct": float(vacancy_pct),
            "operating_expense_pct": float(operating_expense_pct),
            "cap_rate": float(cap_rate),
        },
        warning=warning,
    )


def _live_pro_forma_inputs(
    *,
    property_payload: JsonObject,
    assumptions: JsonObject,
    comps_payload: JsonObject,
    feasibility_payload: JsonObject,
    state: str,
    underwriting_profile: JsonObject,
) -> LiveProFormaResolution | None:
    max_units = assumptions.get("maxUnits")
    if not isinstance(max_units, int | float):
        estimated_units = _payload_number(feasibility_payload, "estimated_units")
        if isinstance(estimated_units, int | float):
            max_units = estimated_units
    if not isinstance(max_units, int | float):
        max_units = _infer_vacant_single_family_unit_count(property_payload)
    if not isinstance(max_units, int | float) or int(max_units) <= 0:
        return None
    max_units_int = int(max_units)
    if max_units_int >= 5:
        if not all(
            isinstance(underwriting_profile.get(key), int | float)
            for key in (
                "monthly_rent_per_unit",
                "operating_expense_pct",
                "cap_rate",
            )
        ):
            return LiveProFormaResolution(
                inputs=None,
                warning=(
                    "Pro forma skipped: projects with 5 or more units require income-approach underwriting inputs "
                    "(monthlyRentPerUnit, operatingExpensePct, and capRate) before a live max offer can be trusted."
                ),
            )
    payload: JsonObject = {
        "state": state,
        "county": str(property_payload.get("county") or "").strip(),
        "max_units": max_units_int,
        "avg_unit_size_sqft": _float_assumption(assumptions, "avgUnitSizeSf", 850.0),
    }
    assumption_adv_per_unit = assumptions.get("advPerUnit")
    if isinstance(assumption_adv_per_unit, int | float) and float(assumption_adv_per_unit) > 0:
        payload["adv_per_unit"] = float(assumption_adv_per_unit)
    adv_per_unit = comps_payload.get("adv_per_unit")
    if isinstance(adv_per_unit, int | float) and float(adv_per_unit) > 0:
        if _has_qualified_live_unit_comp_signal(comps_payload):
            payload["adv_per_unit"] = float(adv_per_unit)
    estimated_land_value = comps_payload.get("estimated_land_value")
    if isinstance(estimated_land_value, int | float) and float(estimated_land_value) > 0:
        payload["estimated_land_value"] = float(estimated_land_value)
    else:
        contextual_land_reconciliation = _required_dict(
            comps_payload,
            "contextual_land_listing_reconciliation",
        )
        county_estimated_land_value = contextual_land_reconciliation.get(
            "county_estimated_land_value"
        )
        if (
            isinstance(county_estimated_land_value, int | float)
            and float(county_estimated_land_value) > 0
        ):
            payload["estimated_land_value"] = float(county_estimated_land_value)
    optional_mappings = {
        "constructionCostPsf": "construction_cost_psf",
        "softCostPct": "soft_cost_pct",
        "builderMarginPct": "builder_margin_pct",
        "impactFeesPerUnit": "impact_fees_per_unit",
    }
    for assumption_key, payload_key in optional_mappings.items():
        value = assumptions.get(assumption_key)
        if isinstance(value, int | float):
            payload[payload_key] = float(value)
    if "adv_per_unit" not in payload:
        if "estimated_land_value" in payload:
            return LiveProFormaResolution(
                inputs=None,
                warning=(
                    "Pro forma skipped: comparable sales did not establish a qualified after-development "
                    "value per unit; provide recent sold-unit comps or an explicit advPerUnit assumption."
                ),
            )
        return None
    warning: str | None = None
    if (
        isinstance(assumption_adv_per_unit, int | float)
        and float(assumption_adv_per_unit) > 0
        and not _has_qualified_live_unit_comp_signal(comps_payload)
    ):
        warning = (
            "Pro forma used a user-supplied advPerUnit assumption because qualified sold-unit comps were not available; "
            "verify exit pricing with recent finished-product sales before relying on the max offer."
        )
    return LiveProFormaResolution(inputs=payload, warning=warning)


def _has_direct_land_comp_signal(comps_payload: JsonObject) -> bool:
    comparables = comps_payload.get("comparables")
    estimated_land_value = comps_payload.get("estimated_land_value")
    confidence = comps_payload.get("confidence")
    notes = _string_list(comps_payload.get("notes"))
    typed_comparables: list[JsonObject] = []
    if isinstance(comparables, list):
        for comparable in comparables:
            if not isinstance(comparable, dict):
                continue
            typed_comparables.append(comparable)
    independent_land_comp_count, strong_independent_land_comp_count = _independent_land_comp_counts(
        typed_comparables
    )
    best_fit_score, best_fit_variance_ratio, best_fit_qualification_score = (
        _best_land_comp_fit_metrics(comps_payload=comps_payload)
    )
    has_confidence = isinstance(confidence, int | float) and float(confidence) >= 0.5
    is_fallback_land_signal = any("fallback land comps" in note.lower() for note in notes)
    return (
        independent_land_comp_count >= 2
        and strong_independent_land_comp_count >= 2
        and best_fit_score >= 0.8
        and best_fit_variance_ratio <= 0.2
        and best_fit_qualification_score >= 0.7
        and isinstance(estimated_land_value, int | float)
        and float(estimated_land_value) > 0
        and has_confidence
        and not is_fallback_land_signal
    )


def _has_supported_relaxed_land_comp_signal(comps_payload: JsonObject) -> bool:
    comparables = comps_payload.get("comparables")
    estimated_land_value = comps_payload.get("estimated_land_value")
    confidence = comps_payload.get("confidence")
    notes = _string_list(comps_payload.get("notes"))
    typed_comparables: list[JsonObject] = []
    supported_cluster_keys: set[tuple[str, int, int]] = set()
    supported_independent_count = 0
    if isinstance(comparables, list):
        for comparable in comparables:
            if not isinstance(comparable, dict):
                continue
            typed_comparables.append(comparable)
            score = _comp_qualification_score(comparable)
            if score is None or score < 0.55:
                continue
            cluster_key = _land_comp_cluster_key(comparable)
            if cluster_key is None:
                supported_independent_count += 1
                continue
            if cluster_key not in supported_cluster_keys:
                supported_cluster_keys.add(cluster_key)
                supported_independent_count += 1
    independent_land_comp_count, strong_independent_land_comp_count = _independent_land_comp_counts(
        typed_comparables
    )
    has_confidence = isinstance(confidence, int | float) and float(confidence) >= 0.45
    is_relaxed_land_signal = bool(comps_payload.get("used_relaxed_land_comps")) or any(
        "fallback land comps" in note.lower() for note in notes
    )
    return (
        independent_land_comp_count >= 2
        and supported_independent_count >= 2
        and isinstance(estimated_land_value, int | float)
        and float(estimated_land_value) > 0
        and has_confidence
        and is_relaxed_land_signal
    )


def _merge_live_land_comp_payloads(
    *,
    primary_payload: JsonObject,
    attempt_payloads: list[JsonObject],
    subject_lot_size_sqft: float,
) -> JsonObject:
    merged_payload = dict(primary_payload)
    merged_comparables: list[JsonObject] = []
    seen_identity_keys: set[str] = set()
    for payload in attempt_payloads:
        comparables = payload.get("comparables")
        if not isinstance(comparables, list):
            continue
        for comparable in comparables:
            if not isinstance(comparable, dict):
                continue
            identity_key = _comparable_identity_key(comparable)
            if identity_key is None or identity_key in seen_identity_keys:
                continue
            seen_identity_keys.add(identity_key)
            merged_comparables.append(comparable)
    if not merged_comparables:
        return merged_payload
    merged_comparables.sort(
        key=lambda comparable: (
            -float(_comp_qualification_score(comparable) or 0.0),
            _comp_address_sort_penalty(comparable),
            float(comparable.get("distance_miles") or 0.0),
        )
    )
    merged_payload["comparables"] = merged_comparables
    merged_payload["used_relaxed_land_comps"] = any(
        bool(payload.get("used_relaxed_land_comps")) for payload in attempt_payloads
    )
    notes = _string_list(merged_payload.get("notes"))
    if (
        "Merged land comps across search radii for stronger county-backed land coverage."
        not in notes
    ):
        notes.append(
            "Merged land comps across search radii for stronger county-backed land coverage."
        )
    merged_payload["notes"] = notes
    price_per_acre_values = sorted(
        float(value)
        for comparable in merged_comparables
        for value in [comparable.get("price_per_acre")]
        if isinstance(value, int | float) and float(value) > 0
    )
    if price_per_acre_values and subject_lot_size_sqft > 0:
        subject_acres = subject_lot_size_sqft / 43_560.0
        low_ppa = _percentile_value(price_per_acre_values, 0.25)
        median_ppa = _median(price_per_acre_values)
        high_ppa = _percentile_value(price_per_acre_values, 0.75)
        merged_payload["price_per_acre_low"] = round(low_ppa, 2)
        merged_payload["median_price_per_acre"] = round(median_ppa, 2)
        merged_payload["price_per_acre_high"] = round(high_ppa, 2)
        merged_payload["estimated_land_value_low"] = round(low_ppa * subject_acres, 2)
        merged_payload["estimated_land_value"] = round(median_ppa * subject_acres, 2)
        merged_payload["estimated_land_value_high"] = round(high_ppa * subject_acres, 2)
    merged_payload["confidence"] = max(float(merged_payload.get("confidence") or 0.0), 0.45)
    return merged_payload


def _is_vacant_single_family_payload(property_payload: JsonObject) -> bool:
    zoning = str(property_payload.get("zoning_code") or "").upper().replace(" ", "")
    land_use_description = str(property_payload.get("land_use_description") or "").upper()
    return (
        any(zoning.startswith(prefix) for prefix in ("RS", "R-1", "R1", "RE", "RH", "SF", "SFR"))
        and "VACANT" in land_use_description
    )


def _infer_vacant_single_family_unit_count(property_payload: JsonObject) -> int | None:
    zoning = str(property_payload.get("zoning_code") or "").upper().replace(" ", "")
    zoning_description = str(property_payload.get("zoning_description") or "").upper()
    land_use_description = str(property_payload.get("land_use_description") or "").upper()
    if not any(
        zoning.startswith(prefix) for prefix in ("RS", "R-1", "R1", "RE", "RH", "SF", "SFR")
    ):
        return None
    if "SINGLE-FAMILY" in zoning_description or "SINGLE FAMILY" in zoning_description:
        return 1
    if "VACANT RESIDENTIAL" in land_use_description:
        return 1
    return None


def _live_residual_inputs(
    *,
    assumptions: JsonObject,
    noi_payload: JsonObject,
) -> JsonObject | None:
    required_values = {
        "hardCosts": assumptions.get("hardCosts"),
        "softCosts": assumptions.get("softCosts"),
        "contingency": assumptions.get("contingency"),
        "developerFee": assumptions.get("developerFee"),
        "closingCosts": assumptions.get("closingCosts"),
        "financingCosts": assumptions.get("financingCosts"),
        "holdingCosts": assumptions.get("holdingCosts"),
        "sellingCosts": assumptions.get("sellingCosts"),
    }
    required: dict[str, float] = {}
    for key, value in required_values.items():
        if not isinstance(value, int | float):
            return None
        required[key] = float(value)
    as_built_value = _payload_number(noi_payload, "as_built_value")
    if not isinstance(as_built_value, int | float):
        return None
    target_profit_pct = _float_assumption(assumptions, "targetProfitPct", 0.18)
    return {
        "as_built_value": float(as_built_value),
        "desired_profit": round(float(as_built_value) * target_profit_pct, 2),
        "hard_costs": float(required["hardCosts"]),
        "soft_costs": float(required["softCosts"]),
        "contingency": float(required["contingency"]),
        "developer_fee": float(required["developerFee"]),
        "closing_costs": float(required["closingCosts"]),
        "financing_costs": float(required["financingCosts"]),
        "holding_costs": float(required["holdingCosts"]),
        "selling_costs": float(required["sellingCosts"]),
        "asking_price": _float_assumption(assumptions, "askingPrice", 0.0),
    }


def _select_live_underwriting_strategy(
    *,
    property_payload: JsonObject,
    assumptions: JsonObject,
    comps_payload: JsonObject,
    feasibility_payload: JsonObject,
) -> LiveUnderwritingStrategy:
    explicit_mode = _explicit_underwriting_mode(assumptions)
    if explicit_mode is not None:
        return LiveUnderwritingStrategy(
            mode=explicit_mode,
            reason=f"Run used the user-requested {explicit_mode.replace('_', ' ')} underwriting mode.",
        )
    estimated_units = assumptions.get("maxUnits")
    if not isinstance(estimated_units, int | float):
        estimated_units = _payload_number(feasibility_payload, "estimated_units")
    if not isinstance(estimated_units, int | float):
        estimated_units = _infer_vacant_single_family_unit_count(property_payload)
    is_small_vacant_single_family = (
        _is_vacant_single_family_payload(property_payload)
        and isinstance(estimated_units, int | float)
        and int(estimated_units) <= 4
    )
    if (
        is_small_vacant_single_family
        and _has_qualified_live_unit_comp_signal(comps_payload)
        and not _has_explicit_income_underwriting_inputs(assumptions)
    ):
        return LiveUnderwritingStrategy(
            mode="sold_unit_exit",
            reason=(
                "Run used sold-unit exit underwriting because this appears to be a vacant low-density "
                "residential lot and the user did not provide explicit rental underwriting inputs."
            ),
        )
    return LiveUnderwritingStrategy(
        mode="income_cap_rate",
        reason="Run used income-based underwriting because rental underwriting inputs were available or the site did not fit the sold-unit exit shortcut.",
    )


def _explicit_underwriting_mode(assumptions: JsonObject) -> str | None:
    for key in ("underwritingMode", "underwritingStrategy", "exitStrategy"):
        raw_value = assumptions.get(key)
        if not isinstance(raw_value, str):
            continue
        normalized_value = raw_value.strip().lower().replace("-", "_").replace(" ", "_")
        match normalized_value:
            case "sold_unit_exit" | "for_sale" | "sales_comps" | "sale_exit":
                return "sold_unit_exit"
            case "income_cap_rate" | "rental_hold" | "build_to_rent" | "brrrr":
                return "income_cap_rate"
            case _:
                continue
    return None


def _has_explicit_income_underwriting_inputs(assumptions: JsonObject) -> bool:
    required_fields = ("monthlyRentPerUnit", "operatingExpensePct", "capRate")
    return all(
        isinstance(assumptions.get(field_name), int | float) for field_name in required_fields
    )


def _live_zoning_claims(
    *,
    run_id: RunId,
    report_id: ReportId,
    property_payload: JsonObject,
    evidence_items: list[EvidenceItem],
    artifacts: JsonObject,
    warnings: list[str],
) -> list[Claim]:
    claim_ids = [item.evidence_id for item in evidence_items]
    zoning_claim_evidence_ids = _claim_evidence_ids_for_source_types(
        evidence_items,
        (
            EvidenceSourceType.PARCEL_RECORD,
            EvidenceSourceType.ZONING_BOUNDARY,
            EvidenceSourceType.ORDINANCE_TEXT,
            EvidenceSourceType.MUNICODE_SECTION,
            EvidenceSourceType.GIS_LAYER,
        ),
    )
    if not zoning_claim_evidence_ids:
        zoning_claim_evidence_ids = claim_ids[:2]
    zoning_source_url = (
        str(property_payload.get("zoning_layer_url") or "").strip()
        or "https://plotlot.local/zoning-record"
    )
    claims = [
        Claim(
            claim_id=ClaimId(f"claim_{run_id}_live_zoning_code"),
            run_id=run_id,
            report_id=report_id,
            claim_text=(
                f"{property_payload.get('address', 'This site')} is currently treated as "
                f"{property_payload.get('zoning_code', 'unknown')} in "
                f"{property_payload.get('municipality', property_payload.get('county', 'the jurisdiction'))}."
            ),
            claim_type="zoning_code",
            field_key="zoning.current_district",
            kind=ClaimKind.HYPOTHESIS,
            origin=ClaimOrigin.LOCAL_AUTHORITY,
            status=ClaimStatus.PRELIMINARY,
            confidence=0.72,
            evidence_ids=zoning_claim_evidence_ids,
            source_url=zoning_source_url,
            next_verification_step="Confirm the controlling municipal zoning code section before issuing a final recommendation.",
            claim_freshness=ClaimFreshnessStatus.REQUIRES_OFFICIAL_VERIFICATION,
            source_mode=SourceMode.LIVE,
        )
    ]
    manual_dimensional = _required_dict(artifacts, "manual_dimensional_standards")
    if manual_dimensional:
        manual_evidence_ids = [
            item.evidence_id
            for item in evidence_items
            if item.source_type == EvidenceSourceType.USER_ASSUMPTION
        ]
        claim_text_parts = [
            f"minimum lot area {manual_dimensional.get('min_lot_area_sf')} sf"
            if manual_dimensional.get("min_lot_area_sf") is not None
            else None,
            f"density {manual_dimensional.get('max_density_units_per_acre')} du/ac"
            if manual_dimensional.get("max_density_units_per_acre") is not None
            else None,
            f"minimum frontage {manual_dimensional.get('min_lot_frontage_ft')} ft"
            if manual_dimensional.get("min_lot_frontage_ft") is not None
            else None,
            f"assumed lot frontage {manual_dimensional.get('lot_frontage_ft')} ft"
            if manual_dimensional.get("lot_frontage_ft") is not None
            else None,
            f"front setback {manual_dimensional.get('front_setback_ft')} ft"
            if manual_dimensional.get("front_setback_ft") is not None
            else None,
            f"side setback {manual_dimensional.get('side_setback_ft')} ft"
            if manual_dimensional.get("side_setback_ft") is not None
            else None,
            f"rear setback {manual_dimensional.get('rear_setback_ft')} ft"
            if manual_dimensional.get("rear_setback_ft") is not None
            else None,
            f"lot coverage {manual_dimensional.get('max_lot_coverage_pct')}%"
            if manual_dimensional.get("max_lot_coverage_pct") is not None
            else None,
            f"maximum height {manual_dimensional.get('max_height_ft')} ft"
            if manual_dimensional.get("max_height_ft") is not None
            else None,
            f"maximum stories {manual_dimensional.get('max_stories')}"
            if manual_dimensional.get("max_stories") is not None
            else None,
            f"water setback {manual_dimensional.get('water_setback_ft')} ft"
            if manual_dimensional.get("water_setback_ft") is not None
            else None,
            f"accessory separation {manual_dimensional.get('accessory_separation_ft')} ft"
            if manual_dimensional.get("accessory_separation_ft") is not None
            else None,
        ]
        claims.append(
            Claim(
                claim_id=ClaimId(f"claim_{run_id}_live_manual_dimensional_standards"),
                run_id=run_id,
                report_id=report_id,
                claim_text=(
                    "The current feasibility run uses user-supplied dimensional standards: "
                    + ", ".join(part for part in claim_text_parts if part is not None)
                    + "."
                ),
                claim_type="manual_dimensional_standards",
                field_key="zoning.manual_dimensional_standards",
                kind=ClaimKind.ASSUMPTION,
                origin=ClaimOrigin.USER_INPUT,
                status=ClaimStatus.PRELIMINARY,
                confidence=0.95,
                evidence_ids=manual_evidence_ids,
                next_verification_step="Confirm the dimensional standards against the controlling municipal code before relying on the feasibility or offer guidance.",
                claim_freshness=ClaimFreshnessStatus.REQUIRES_OFFICIAL_VERIFICATION,
                source_mode=SourceMode.LIVE,
            )
        )
    if warnings:
        claims.append(
            Claim(
                claim_id=ClaimId(f"claim_{run_id}_live_warning"),
                run_id=run_id,
                report_id=report_id,
                claim_text=warnings[0],
                claim_type="analysis_caveat",
                field_key="analysis.warning",
                kind=ClaimKind.CAVEAT,
                origin=ClaimOrigin.SYSTEM_POLICY,
                status=ClaimStatus.PRELIMINARY,
                confidence=0.95,
                evidence_ids=claim_ids[:1],
                next_verification_step="Resolve the missing evidence or assumptions before treating this as final.",
                claim_freshness=ClaimFreshnessStatus.UNKNOWN,
                source_mode=SourceMode.LIVE,
            )
        )
    return claims


def _live_acquisition_claims(
    *,
    run_id: RunId,
    report_id: ReportId,
    property_payload: JsonObject,
    artifacts: JsonObject,
    evidence_items: list[EvidenceItem],
    calculations: list[CalculationResult],
    comps_payload: JsonObject,
    comp_evidence: list[EvidenceItem],
    pro_forma_payload: JsonObject,
    residual_payload: JsonObject,
    underwriting_mode: JsonObject,
    warnings: list[str],
) -> list[Claim]:
    claims = _live_zoning_claims(
        run_id=run_id,
        report_id=report_id,
        property_payload=property_payload,
        evidence_items=evidence_items,
        artifacts=artifacts,
        warnings=[],
    )
    evidence_ids = [item.evidence_id for item in evidence_items]
    comp_claim_evidence_ids = _claim_evidence_ids_for_source_types(
        evidence_items,
        (EvidenceSourceType.MARKET_COMP, EvidenceSourceType.RENTAL_COMP),
    )
    if not comp_claim_evidence_ids:
        comp_claim_evidence_ids = evidence_ids
    calc_ids = [item.calculation_id for item in calculations]
    if _has_live_comp_signal(comps_payload=comps_payload, comp_evidence=comp_evidence):
        comp_value_basis = (
            "User-supplied comps"
            if bool(comps_payload.get("manual_comp_override"))
            else "Live comps"
        )
        land_comp_quality = _land_comp_quality_summary(comps_payload)
        unit_comp_quality = _unit_comp_quality_summary(comps_payload)
        claims.append(
            Claim(
                claim_id=ClaimId(f"claim_{run_id}_live_comp_value"),
                run_id=run_id,
                report_id=report_id,
                claim_text=(
                    f"{comp_value_basis} indicate an estimated land value of "
                    f"{comps_payload.get('estimated_land_value', 0)} and an ADV per unit of "
                    f"{comps_payload.get('adv_per_unit', 0)}."
                ),
                claim_type="comp_value_signal",
                field_key="market.comp_signal",
                kind=ClaimKind.CALCULATION,
                origin=(
                    ClaimOrigin.USER_INPUT
                    if bool(comps_payload.get("manual_comp_override"))
                    else ClaimOrigin.GIS_PROVIDER
                ),
                status=ClaimStatus.PRELIMINARY,
                confidence=0.74,
                evidence_ids=comp_claim_evidence_ids,
                source_url="https://plotlot.local/market-comps",
                next_verification_step="Review the comparable sales set and replace any weak comps before a final offer.",
                claim_freshness=ClaimFreshnessStatus.FRESH,
                metadata={
                    "pricing_source": (
                        "manual_comps"
                        if bool(comps_payload.get("manual_comp_override"))
                        else "auto_comps"
                    ),
                    "land_comp_quality": land_comp_quality,
                    "unit_comp_quality": unit_comp_quality,
                },
                source_mode=SourceMode.LIVE,
            )
        )
    pricing_payload = residual_payload if residual_payload else pro_forma_payload
    if pricing_payload:
        mode = str(underwriting_mode.get("mode") or "").strip()
        if mode == "income_cap_rate":
            claim_text = (
                "Deterministic income-approach underwriting yields a live preliminary max supportable land "
                f"price of {pricing_payload.get('max_supportable_land_price', 0)}."
            )
            confidence = 0.88
        elif mode == "sold_unit_exit":
            claim_text = (
                "Deterministic sold-unit exit pricing yields a live preliminary max supportable land "
                f"price of {pricing_payload.get('max_supportable_land_price', 0)}."
            )
            confidence = 0.78
        else:
            claim_text = (
                "Deterministic underwriting math yields a live preliminary max supportable land "
                f"price of {pricing_payload.get('max_supportable_land_price', 0)}."
            )
            confidence = 0.82
        claims.append(
            Claim(
                claim_id=ClaimId(f"claim_{run_id}_live_max_offer"),
                run_id=run_id,
                report_id=report_id,
                claim_text=claim_text,
                claim_type="max_supportable_land_price",
                field_key="underwriting.max_offer",
                kind=ClaimKind.CALCULATION,
                origin=ClaimOrigin.DETERMINISTIC_CALCULATION,
                status=ClaimStatus.PRELIMINARY,
                confidence=confidence,
                evidence_ids=evidence_ids,
                calculation_ids=calc_ids,
                next_verification_step="Re-run underwriting after confirming ordinance controls and final cost assumptions.",
                claim_freshness=ClaimFreshnessStatus.UNKNOWN,
                source_mode=SourceMode.LIVE,
            )
        )
    for index, warning in enumerate(warnings, start=1):
        claims.append(
            Claim(
                claim_id=ClaimId(f"claim_{run_id}_live_warning_{index}"),
                run_id=run_id,
                report_id=report_id,
                claim_text=warning,
                claim_type="analysis_caveat",
                field_key=f"analysis.warning.{index}",
                kind=ClaimKind.CAVEAT,
                origin=ClaimOrigin.SYSTEM_POLICY,
                status=ClaimStatus.PRELIMINARY,
                confidence=0.95,
                evidence_ids=evidence_ids[:1],
                next_verification_step="Provide the missing assumptions or source evidence before relying on this conclusion.",
                claim_freshness=ClaimFreshnessStatus.UNKNOWN,
                source_mode=SourceMode.LIVE,
            )
        )
    return claims


def _build_live_acquisition_guidance(
    *,
    property_payload: JsonObject,
    comps_payload: JsonObject,
    pro_forma_payload: JsonObject,
    residual_payload: JsonObject,
    underwriting_mode: JsonObject,
) -> JsonObject:
    max_offer = _payload_number(residual_payload, "max_supportable_land_price")
    if not isinstance(max_offer, int | float):
        max_offer = _payload_number(pro_forma_payload, "max_supportable_land_price")
    land_value = _payload_number(comps_payload, "estimated_land_value")
    land_value_low = _market_land_value_bound(comps_payload, "estimated_land_value_low", land_value)
    land_value_high = _market_land_value_bound(
        comps_payload, "estimated_land_value_high", land_value
    )
    has_land_signal = _has_direct_land_comp_signal(comps_payload)
    has_supported_relaxed_land_signal = _has_supported_relaxed_land_comp_signal(comps_payload)
    adv_per_unit = _payload_number(comps_payload, "adv_per_unit")
    has_exit_signal = isinstance(adv_per_unit, int | float) and float(adv_per_unit) > 0
    contextual_web_land_candidates = _web_listing_candidate_count(
        comps_payload,
        classification="likely_vacant_land",
    )
    contextual_web_improved_candidates = _web_listing_candidate_count(
        comps_payload,
        classification="likely_improved_sale",
    )
    mode = str(underwriting_mode.get("mode") or "")
    pricing_source = str(underwriting_mode.get("pricing_source") or "")
    contextual_land_verification = _required_dict(
        comps_payload,
        "contextual_land_listing_verification",
    )
    contextual_land_reconciliation = _required_dict(
        comps_payload,
        "contextual_land_listing_reconciliation",
    )
    contextual_land_value = _payload_number(contextual_land_verification, "estimated_land_value")
    contextual_land_value_low = _payload_number(
        contextual_land_verification,
        "estimated_land_value_low",
    )
    contextual_land_value_high = _payload_number(
        contextual_land_verification,
        "estimated_land_value_high",
    )
    contextual_verified_land_candidates = int(
        contextual_land_verification.get("verified_candidate_count") or 0
    )
    county_reconciled_land_candidates = int(
        contextual_land_reconciliation.get("reconciled_candidate_count") or 0
    )
    county_reconciled_land_value = _payload_number(
        contextual_land_reconciliation,
        "county_estimated_land_value",
    )
    county_reconciled_land_value_low = _payload_number(
        contextual_land_reconciliation,
        "county_estimated_land_value_low",
    )
    county_reconciled_land_value_high = _payload_number(
        contextual_land_reconciliation,
        "county_estimated_land_value_high",
    )
    land_signal_source = "none"
    land_signal_strength = "none"
    effective_land_value: float | None = None
    effective_land_value_low: float | None = None
    effective_land_value_high: float | None = None
    if isinstance(land_value, int | float) and float(land_value) > 0:
        if bool(comps_payload.get("manual_comp_override")):
            land_signal_source = "manual_land_comps"
            land_signal_strength = "manual_override"
        elif has_land_signal:
            land_signal_source = "direct_land_comps"
            land_signal_strength = "direct"
        elif has_supported_relaxed_land_signal:
            land_signal_source = "relaxed_land_comps"
            land_signal_strength = "supported_relaxed"
        else:
            land_signal_source = "direct_land_comps"
            land_signal_strength = "direct"
        effective_land_value = float(land_value)
        effective_land_value_low = land_value_low
        effective_land_value_high = land_value_high
    elif (
        county_reconciled_land_candidates > 0
        and isinstance(county_reconciled_land_value, int | float)
        and float(county_reconciled_land_value) > 0
    ):
        land_signal_source = "county_reconciled_public_listing"
        land_signal_strength = "county_reconciled"
        effective_land_value = float(county_reconciled_land_value)
        effective_land_value_low = (
            float(county_reconciled_land_value_low)
            if isinstance(county_reconciled_land_value_low, int | float)
            else float(county_reconciled_land_value)
        )
        effective_land_value_high = (
            float(county_reconciled_land_value_high)
            if isinstance(county_reconciled_land_value_high, int | float)
            else float(county_reconciled_land_value)
        )
    elif (
        contextual_verified_land_candidates > 0
        and isinstance(contextual_land_value, int | float)
        and float(contextual_land_value) > 0
    ):
        land_signal_source = "contextual_public_listing"
        land_signal_strength = "contextual"
        effective_land_value = float(contextual_land_value)
        effective_land_value_low = (
            float(contextual_land_value_low)
            if isinstance(contextual_land_value_low, int | float)
            else float(contextual_land_value)
        )
        effective_land_value_high = (
            float(contextual_land_value_high)
            if isinstance(contextual_land_value_high, int | float)
            else float(contextual_land_value)
        )
    comparables = comps_payload.get("comparables")
    has_manual_land_comp_override = (
        _has_minimum_manual_land_comp_support(comps_payload)
        and isinstance(land_value, int | float)
        and float(land_value) > 0
        and isinstance(comparables, list)
        and len(comparables) > 0
    )
    pricing_basis = (
        "user_supplied_comps"
        if bool(comps_payload.get("manual_comp_override"))
        else "auto_discovered_comps"
    )
    prior_sale = property_payload.get("last_sale_price")
    owner_basis_warning = (
        f"Prior recorded sale price was {float(prior_sale):.0f}; seller expectations may exceed supportable pricing."
        if isinstance(prior_sale, int | float) and float(prior_sale) > 0
        else ""
    )
    market_to_residual_gap = _market_to_residual_gap(
        land_value=effective_land_value,
        max_offer=max_offer if isinstance(max_offer, int | float) else None,
    )
    guidance_land_value_low = (
        effective_land_value_low if effective_land_value_low is not None else land_value_low
    )
    guidance_land_value_high = (
        effective_land_value_high if effective_land_value_high is not None else land_value_high
    )

    if mode == "blocked_by_comping_gate":
        return {
            "recommended_action": "insufficient_support",
            "basis": "comping_underwriting_not_ready",
            **_guidance_meta(
                recommended_action="insufficient_support",
                land_signal_strength=land_signal_strength,
            ),
            "recommended_offer": 0.0,
            "max_supportable_land_price": 0.0,
            "land_value_signal": float(land_value) if isinstance(land_value, int | float) else 0.0,
            "market_land_value_low": guidance_land_value_low,
            "market_land_value_high": guidance_land_value_high,
            "adv_per_unit": float(adv_per_unit) if isinstance(adv_per_unit, int | float) else 0.0,
            "underwriting_mode": mode,
            "pricing_source": pricing_source,
            "pricing_basis": pricing_basis,
            "land_signal_source": land_signal_source,
            "land_signal_strength": land_signal_strength,
            "land_comp_signal_available": has_land_signal,
            "exit_comp_signal_available": has_exit_signal,
            "contextual_web_land_candidate_count": contextual_web_land_candidates,
            "contextual_web_improved_candidate_count": contextual_web_improved_candidates,
            "contextual_verified_land_candidate_count": contextual_verified_land_candidates,
            "contextual_land_value_signal": (
                float(contextual_land_value)
                if isinstance(contextual_land_value, int | float)
                else 0.0
            ),
            "contextual_market_land_value_low": (
                float(contextual_land_value_low)
                if isinstance(contextual_land_value_low, int | float)
                else 0.0
            ),
            "contextual_market_land_value_high": (
                float(contextual_land_value_high)
                if isinstance(contextual_land_value_high, int | float)
                else 0.0
            ),
            "county_reconciled_land_candidate_count": county_reconciled_land_candidates,
            "county_reconciled_land_value_signal": (
                float(county_reconciled_land_value)
                if isinstance(county_reconciled_land_value, int | float)
                else 0.0
            ),
            "county_reconciled_market_land_value_low": (
                float(county_reconciled_land_value_low)
                if isinstance(county_reconciled_land_value_low, int | float)
                else 0.0
            ),
            "county_reconciled_market_land_value_high": (
                float(county_reconciled_land_value_high)
                if isinstance(county_reconciled_land_value_high, int | float)
                else 0.0
            ),
            "owner_basis_warning": owner_basis_warning,
            "market_to_residual_gap": market_to_residual_gap,
            "underwriting_blocker": str(underwriting_mode.get("reason") or ""),
        }

    if isinstance(max_offer, int | float) and float(max_offer) <= 0:
        return {
            "recommended_action": "no_offer",
            "basis": "negative_residual",
            **_guidance_meta(
                recommended_action="no_offer",
                land_signal_strength=land_signal_strength,
            ),
            "recommended_offer": 0.0,
            "max_supportable_land_price": float(max_offer),
            "land_value_signal": float(land_value) if isinstance(land_value, int | float) else 0.0,
            "market_land_value_low": guidance_land_value_low,
            "market_land_value_high": guidance_land_value_high,
            "adv_per_unit": float(adv_per_unit) if isinstance(adv_per_unit, int | float) else 0.0,
            "underwriting_mode": mode,
            "pricing_source": pricing_source,
            "pricing_basis": pricing_basis,
            "land_signal_source": land_signal_source,
            "land_signal_strength": land_signal_strength,
            "land_comp_signal_available": has_land_signal,
            "exit_comp_signal_available": has_exit_signal,
            "contextual_web_land_candidate_count": contextual_web_land_candidates,
            "contextual_web_improved_candidate_count": contextual_web_improved_candidates,
            "contextual_verified_land_candidate_count": contextual_verified_land_candidates,
            "contextual_land_value_signal": (
                float(contextual_land_value)
                if isinstance(contextual_land_value, int | float)
                else 0.0
            ),
            "contextual_market_land_value_low": (
                float(contextual_land_value_low)
                if isinstance(contextual_land_value_low, int | float)
                else 0.0
            ),
            "contextual_market_land_value_high": (
                float(contextual_land_value_high)
                if isinstance(contextual_land_value_high, int | float)
                else 0.0
            ),
            "county_reconciled_land_candidate_count": county_reconciled_land_candidates,
            "county_reconciled_land_value_signal": (
                float(county_reconciled_land_value)
                if isinstance(county_reconciled_land_value, int | float)
                else 0.0
            ),
            "county_reconciled_market_land_value_low": (
                float(county_reconciled_land_value_low)
                if isinstance(county_reconciled_land_value_low, int | float)
                else 0.0
            ),
            "county_reconciled_market_land_value_high": (
                float(county_reconciled_land_value_high)
                if isinstance(county_reconciled_land_value_high, int | float)
                else 0.0
            ),
            "owner_basis_warning": owner_basis_warning,
            "market_to_residual_gap": market_to_residual_gap,
        }
    if isinstance(max_offer, int | float) and float(max_offer) > 0:
        if not has_land_signal and not has_manual_land_comp_override:
            basis = "missing_direct_land_comp_signal"
            if contextual_web_land_candidates > 0:
                basis = "contextual_web_land_signal_requires_validation"
            if has_supported_relaxed_land_signal:
                return {
                    "recommended_action": "insufficient_support",
                    "basis": "supported_relaxed_land_signal_requires_validation",
                    **_guidance_meta(
                        recommended_action="insufficient_support",
                        land_signal_strength=land_signal_strength,
                    ),
                    "recommended_offer": 0.0,
                    "recommended_offer_low": 0.0,
                    "recommended_offer_high": 0.0,
                    "max_supportable_land_price": float(max_offer),
                    "land_value_signal": float(land_value)
                    if isinstance(land_value, int | float)
                    else 0.0,
                    "market_land_value_low": guidance_land_value_low,
                    "market_land_value_high": guidance_land_value_high,
                    "adv_per_unit": float(adv_per_unit)
                    if isinstance(adv_per_unit, int | float)
                    else 0.0,
                    "underwriting_mode": mode,
                    "pricing_source": pricing_source,
                    "pricing_basis": pricing_basis,
                    "land_signal_source": land_signal_source,
                    "land_signal_strength": land_signal_strength,
                    "land_comp_signal_available": False,
                    "exit_comp_signal_available": has_exit_signal,
                    "contextual_web_land_candidate_count": contextual_web_land_candidates,
                    "contextual_web_improved_candidate_count": contextual_web_improved_candidates,
                    "contextual_verified_land_candidate_count": contextual_verified_land_candidates,
                    "contextual_land_value_signal": (
                        float(contextual_land_value)
                        if isinstance(contextual_land_value, int | float)
                        else 0.0
                    ),
                    "contextual_market_land_value_low": (
                        float(contextual_land_value_low)
                        if isinstance(contextual_land_value_low, int | float)
                        else 0.0
                    ),
                    "contextual_market_land_value_high": (
                        float(contextual_land_value_high)
                        if isinstance(contextual_land_value_high, int | float)
                        else 0.0
                    ),
                    "county_reconciled_land_candidate_count": county_reconciled_land_candidates,
                    "county_reconciled_land_value_signal": (
                        float(county_reconciled_land_value)
                        if isinstance(county_reconciled_land_value, int | float)
                        else 0.0
                    ),
                    "county_reconciled_market_land_value_low": (
                        float(county_reconciled_land_value_low)
                        if isinstance(county_reconciled_land_value_low, int | float)
                        else 0.0
                    ),
                    "county_reconciled_market_land_value_high": (
                        float(county_reconciled_land_value_high)
                        if isinstance(county_reconciled_land_value_high, int | float)
                        else 0.0
                    ),
                    "owner_basis_warning": owner_basis_warning,
                    "market_to_residual_gap": market_to_residual_gap,
                }
            if land_signal_strength == "county_reconciled":
                capped_offer_low = _capped_offer_bound(
                    market_bound=float(guidance_land_value_low),
                    max_offer=float(max_offer),
                )
                capped_offer_high = _capped_offer_bound(
                    market_bound=float(guidance_land_value_high),
                    max_offer=float(max_offer),
                )
                return {
                    "recommended_action": "offer_range",
                    "basis": "county_reconciled_land_signal",
                    **_guidance_meta(
                        recommended_action="offer_range",
                        land_signal_strength=land_signal_strength,
                    ),
                    "recommended_offer": float(max_offer),
                    "recommended_offer_low": capped_offer_low,
                    "recommended_offer_high": capped_offer_high,
                    "max_supportable_land_price": float(max_offer),
                    "land_value_signal": float(effective_land_value)
                    if effective_land_value is not None
                    else 0.0,
                    "market_land_value_low": guidance_land_value_low,
                    "market_land_value_high": guidance_land_value_high,
                    "adv_per_unit": float(adv_per_unit)
                    if isinstance(adv_per_unit, int | float)
                    else 0.0,
                    "underwriting_mode": mode,
                    "pricing_source": pricing_source,
                    "pricing_basis": pricing_basis,
                    "land_signal_source": land_signal_source,
                    "land_signal_strength": land_signal_strength,
                    "land_comp_signal_available": False,
                    "exit_comp_signal_available": has_exit_signal,
                    "contextual_web_land_candidate_count": contextual_web_land_candidates,
                    "contextual_web_improved_candidate_count": contextual_web_improved_candidates,
                    "contextual_verified_land_candidate_count": contextual_verified_land_candidates,
                    "contextual_land_value_signal": (
                        float(contextual_land_value)
                        if isinstance(contextual_land_value, int | float)
                        else 0.0
                    ),
                    "contextual_market_land_value_low": (
                        float(contextual_land_value_low)
                        if isinstance(contextual_land_value_low, int | float)
                        else 0.0
                    ),
                    "contextual_market_land_value_high": (
                        float(contextual_land_value_high)
                        if isinstance(contextual_land_value_high, int | float)
                        else 0.0
                    ),
                    "county_reconciled_land_candidate_count": county_reconciled_land_candidates,
                    "county_reconciled_land_value_signal": (
                        float(county_reconciled_land_value)
                        if isinstance(county_reconciled_land_value, int | float)
                        else 0.0
                    ),
                    "county_reconciled_market_land_value_low": (
                        float(county_reconciled_land_value_low)
                        if isinstance(county_reconciled_land_value_low, int | float)
                        else 0.0
                    ),
                    "county_reconciled_market_land_value_high": (
                        float(county_reconciled_land_value_high)
                        if isinstance(county_reconciled_land_value_high, int | float)
                        else 0.0
                    ),
                    "owner_basis_warning": owner_basis_warning,
                    "market_to_residual_gap": market_to_residual_gap,
                }
            return {
                "recommended_action": "insufficient_support",
                "basis": basis,
                **_guidance_meta(
                    recommended_action="insufficient_support",
                    land_signal_strength=land_signal_strength,
                ),
                "recommended_offer": 0.0,
                "max_supportable_land_price": float(max_offer),
                "land_value_signal": 0.0,
                "market_land_value_low": guidance_land_value_low,
                "market_land_value_high": guidance_land_value_high,
                "adv_per_unit": float(adv_per_unit)
                if isinstance(adv_per_unit, int | float)
                else 0.0,
                "underwriting_mode": mode,
                "pricing_source": pricing_source,
                "pricing_basis": pricing_basis,
                "land_signal_source": land_signal_source,
                "land_signal_strength": land_signal_strength,
                "land_comp_signal_available": False,
                "exit_comp_signal_available": has_exit_signal,
                "contextual_web_land_candidate_count": contextual_web_land_candidates,
                "contextual_web_improved_candidate_count": contextual_web_improved_candidates,
                "contextual_verified_land_candidate_count": contextual_verified_land_candidates,
                "contextual_land_value_signal": (
                    float(contextual_land_value)
                    if isinstance(contextual_land_value, int | float)
                    else 0.0
                ),
                "contextual_market_land_value_low": (
                    float(contextual_land_value_low)
                    if isinstance(contextual_land_value_low, int | float)
                    else 0.0
                ),
                "contextual_market_land_value_high": (
                    float(contextual_land_value_high)
                    if isinstance(contextual_land_value_high, int | float)
                    else 0.0
                ),
                "county_reconciled_land_candidate_count": county_reconciled_land_candidates,
                "county_reconciled_land_value_signal": (
                    float(county_reconciled_land_value)
                    if isinstance(county_reconciled_land_value, int | float)
                    else 0.0
                ),
                "county_reconciled_market_land_value_low": (
                    float(county_reconciled_land_value_low)
                    if isinstance(county_reconciled_land_value_low, int | float)
                    else 0.0
                ),
                "county_reconciled_market_land_value_high": (
                    float(county_reconciled_land_value_high)
                    if isinstance(county_reconciled_land_value_high, int | float)
                    else 0.0
                ),
                "owner_basis_warning": owner_basis_warning,
                "market_to_residual_gap": market_to_residual_gap,
            }
        capped_offer_low = _capped_offer_bound(
            market_bound=land_value_low,
            max_offer=float(max_offer),
        )
        capped_offer_high = _capped_offer_bound(
            market_bound=land_value_high,
            max_offer=float(max_offer),
        )
        return {
            "recommended_action": "offer_range",
            "basis": "residual_and_market_signal",
            **_guidance_meta(
                recommended_action="offer_range",
                land_signal_strength=land_signal_strength,
            ),
            "recommended_offer": float(max_offer),
            "recommended_offer_low": capped_offer_low,
            "recommended_offer_high": capped_offer_high,
            "max_supportable_land_price": float(max_offer),
            "land_value_signal": float(land_value) if isinstance(land_value, int | float) else 0.0,
            "market_land_value_low": guidance_land_value_low,
            "market_land_value_high": guidance_land_value_high,
            "adv_per_unit": float(adv_per_unit) if isinstance(adv_per_unit, int | float) else 0.0,
            "underwriting_mode": mode,
            "pricing_source": pricing_source,
            "pricing_basis": pricing_basis,
            "land_signal_source": land_signal_source,
            "land_signal_strength": land_signal_strength,
            "land_comp_signal_available": has_land_signal,
            "exit_comp_signal_available": has_exit_signal,
            "contextual_web_land_candidate_count": contextual_web_land_candidates,
            "contextual_web_improved_candidate_count": contextual_web_improved_candidates,
            "contextual_verified_land_candidate_count": contextual_verified_land_candidates,
            "contextual_land_value_signal": (
                float(contextual_land_value)
                if isinstance(contextual_land_value, int | float)
                else 0.0
            ),
            "contextual_market_land_value_low": (
                float(contextual_land_value_low)
                if isinstance(contextual_land_value_low, int | float)
                else 0.0
            ),
            "contextual_market_land_value_high": (
                float(contextual_land_value_high)
                if isinstance(contextual_land_value_high, int | float)
                else 0.0
            ),
            "county_reconciled_land_candidate_count": county_reconciled_land_candidates,
            "county_reconciled_land_value_signal": (
                float(county_reconciled_land_value)
                if isinstance(county_reconciled_land_value, int | float)
                else 0.0
            ),
            "county_reconciled_market_land_value_low": (
                float(county_reconciled_land_value_low)
                if isinstance(county_reconciled_land_value_low, int | float)
                else 0.0
            ),
            "county_reconciled_market_land_value_high": (
                float(county_reconciled_land_value_high)
                if isinstance(county_reconciled_land_value_high, int | float)
                else 0.0
            ),
            "owner_basis_warning": owner_basis_warning,
            "market_to_residual_gap": market_to_residual_gap,
        }
    return {
        "recommended_action": "insufficient_support",
        "basis": "missing_market_or_underwriting_signal",
        **_guidance_meta(
            recommended_action="insufficient_support",
            land_signal_strength=land_signal_strength,
        ),
        "recommended_offer": 0.0,
        "max_supportable_land_price": 0.0,
        "land_value_signal": float(land_value) if isinstance(land_value, int | float) else 0.0,
        "market_land_value_low": guidance_land_value_low,
        "market_land_value_high": guidance_land_value_high,
        "adv_per_unit": float(adv_per_unit) if isinstance(adv_per_unit, int | float) else 0.0,
        "underwriting_mode": mode,
        "pricing_source": pricing_source,
        "pricing_basis": pricing_basis,
        "land_signal_source": land_signal_source,
        "land_signal_strength": land_signal_strength,
        "land_comp_signal_available": has_land_signal,
        "exit_comp_signal_available": has_exit_signal,
        "contextual_web_land_candidate_count": contextual_web_land_candidates,
        "contextual_web_improved_candidate_count": contextual_web_improved_candidates,
        "contextual_verified_land_candidate_count": contextual_verified_land_candidates,
        "contextual_land_value_signal": (
            float(contextual_land_value) if isinstance(contextual_land_value, int | float) else 0.0
        ),
        "contextual_market_land_value_low": (
            float(contextual_land_value_low)
            if isinstance(contextual_land_value_low, int | float)
            else 0.0
        ),
        "contextual_market_land_value_high": (
            float(contextual_land_value_high)
            if isinstance(contextual_land_value_high, int | float)
            else 0.0
        ),
        "county_reconciled_land_candidate_count": county_reconciled_land_candidates,
        "county_reconciled_land_value_signal": (
            float(county_reconciled_land_value)
            if isinstance(county_reconciled_land_value, int | float)
            else 0.0
        ),
        "county_reconciled_market_land_value_low": (
            float(county_reconciled_land_value_low)
            if isinstance(county_reconciled_land_value_low, int | float)
            else 0.0
        ),
        "county_reconciled_market_land_value_high": (
            float(county_reconciled_land_value_high)
            if isinstance(county_reconciled_land_value_high, int | float)
            else 0.0
        ),
        "owner_basis_warning": owner_basis_warning,
        "market_to_residual_gap": market_to_residual_gap,
    }


def _guidance_meta(*, recommended_action: str, land_signal_strength: str) -> JsonObject:
    verification_status = _market_signal_verification_status(land_signal_strength)
    requires_market_signal_validation = verification_status in {
        "contextual_verified",
        "supported_relaxed",
        "unverified",
    }
    return {
        "market_signal_verification_status": verification_status,
        "requires_market_signal_validation": requires_market_signal_validation,
        "recommendation_confidence": _recommendation_confidence(
            recommended_action=recommended_action,
            land_signal_strength=land_signal_strength,
        ),
    }


def _market_signal_verification_status(land_signal_strength: str) -> str:
    match land_signal_strength:
        case "manual_override":
            return "manual_override"
        case "direct":
            return "direct_verified"
        case "county_reconciled":
            return "county_reconciled"
        case "contextual":
            return "contextual_verified"
        case "supported_relaxed":
            return "supported_relaxed"
        case "none":
            return "unverified"
        case _:
            return "unverified"


def _recommendation_confidence(*, recommended_action: str, land_signal_strength: str) -> str:
    match recommended_action:
        case "offer_range":
            match land_signal_strength:
                case "manual_override" | "direct":
                    return "high"
                case "county_reconciled":
                    return "medium"
                case "contextual" | "supported_relaxed" | "none":
                    return "low"
                case _:
                    return "low"
        case "no_offer":
            return "high"
        case "insufficient_support":
            match land_signal_strength:
                case "contextual" | "supported_relaxed":
                    return "low"
                case "none":
                    return "none"
                case _:
                    return "low"
        case _:
            return "none"


def _market_land_value_bound(
    comps_payload: JsonObject,
    field_key: str,
    fallback: int | float | None,
) -> float:
    value = _payload_number(comps_payload, field_key)
    if isinstance(value, int | float) and float(value) > 0:
        return float(value)
    if isinstance(fallback, int | float) and float(fallback) > 0:
        return float(fallback)
    return 0.0


def _capped_offer_bound(*, market_bound: float, max_offer: float) -> float:
    if market_bound <= 0:
        return max_offer
    return min(market_bound, max_offer)


def _market_to_residual_gap(
    *,
    land_value: int | float | None,
    max_offer: int | float | None,
) -> float:
    if not isinstance(land_value, int | float) or float(land_value) <= 0:
        return 0.0
    if not isinstance(max_offer, int | float):
        return 0.0
    return max(float(land_value) - float(max_offer), 0.0)


def _has_live_comp_signal(
    *,
    comps_payload: JsonObject,
    comp_evidence: list[EvidenceItem],
) -> bool:
    if not comp_evidence:
        return False
    comparables = comps_payload.get("comparables")
    unit_comparables = comps_payload.get("unit_comparables")
    estimated_land_value = comps_payload.get("estimated_land_value")
    adv_per_unit = comps_payload.get("adv_per_unit")
    has_sales = isinstance(comparables, list) and len(comparables) > 0
    has_unit_sales = isinstance(unit_comparables, list) and len(unit_comparables) > 0
    has_value_signal = isinstance(estimated_land_value, int | float) and estimated_land_value > 0
    has_adv_signal = isinstance(adv_per_unit, int | float) and adv_per_unit > 0
    return (has_sales or has_unit_sales) and (has_value_signal or has_adv_signal)


def _has_qualified_live_unit_comp_signal(comps_payload: JsonObject) -> bool:
    unit_comparables = comps_payload.get("unit_comparables")
    adv_per_unit = comps_payload.get("adv_per_unit")
    confidence = comps_payload.get("confidence")
    strong_unit_scores = 0
    very_strong_unit_scores = 0
    if isinstance(unit_comparables, list):
        for comparable in unit_comparables:
            if not isinstance(comparable, dict):
                continue
            score = _comp_qualification_score(comparable)
            if score is None:
                continue
            if score >= 0.7:
                strong_unit_scores += 1
            if score >= 0.85:
                very_strong_unit_scores += 1
    has_unit_sales = isinstance(unit_comparables, list) and len(unit_comparables) > 0
    has_adv_signal = isinstance(adv_per_unit, int | float) and adv_per_unit > 0
    has_confidence = isinstance(confidence, int | float) and float(confidence) >= 0.45
    if bool(comps_payload.get("manual_comp_override")):
        return _has_minimum_manual_exit_comp_support(comps_payload) and has_adv_signal
    has_strong_exit_support = strong_unit_scores >= 2 or (
        very_strong_unit_scores >= 1
        and isinstance(unit_comparables, list)
        and len(unit_comparables) >= 1
    )
    return has_unit_sales and has_adv_signal and has_confidence and has_strong_exit_support


def _web_listing_candidate_count(
    comps_payload: JsonObject,
    *,
    classification: str,
) -> int:
    web_listing_candidates = comps_payload.get("web_listing_candidates")
    if not isinstance(web_listing_candidates, list):
        return 0
    return len(
        [
            candidate
            for candidate in web_listing_candidates
            if isinstance(candidate, dict)
            and str(candidate.get("classification") or "unknown") == classification
        ]
    )


def _has_minimum_manual_land_comp_support(comps_payload: JsonObject) -> bool:
    if not bool(comps_payload.get("manual_comp_override")):
        return False
    comparables = comps_payload.get("comparables")
    if not isinstance(comparables, list):
        return False
    usable_land_comps = [
        comparable
        for comparable in comparables
        if isinstance(comparable, dict)
        and bool(comparable.get("user_supplied"))
        and float(comparable.get("sale_price") or 0.0) > 0
        and float(comparable.get("lot_size_sqft") or 0.0) > 0
    ]
    return len(usable_land_comps) >= 2


def _has_minimum_manual_exit_comp_support(comps_payload: JsonObject) -> bool:
    if not bool(comps_payload.get("manual_comp_override")):
        return False
    unit_comparables = comps_payload.get("unit_comparables")
    if not isinstance(unit_comparables, list):
        return False
    usable_exit_comps = [
        comparable
        for comparable in unit_comparables
        if isinstance(comparable, dict)
        and bool(comparable.get("user_supplied"))
        and float(comparable.get("sale_price") or 0.0) > 0
        and float(comparable.get("price_per_unit") or 0.0) > 0
    ]
    return len(usable_exit_comps) >= 2


def _verification_status_label(verification) -> str:
    if verification.status.value == "passed" and verification.stale_evidence:
        return "passed_with_warnings"
    if verification.status.value == "passed" and any(
        value == "warning" for value in verification.checks.values()
    ):
        return "passed_with_warnings"
    return str(verification.status.value)


def _failed_live_result(
    *,
    request: FixtureDealRunRequest,
    run_id: RunId,
    report_id: ReportId,
    events: list[PlotLotEvent],
    tool_calls: list[ToolCall],
    message: str,
    artifacts: JsonObject,
) -> FixtureDealRunResult:
    events.append(
        _event(
            run_id=run_id,
            sequence=len(events) + 1,
            event_type=PlotLotEventType.RUN_FAILED,
            source=PlotLotEventSource.HARNESS,
            source_mode=request.source_mode,
            execution_mode=request.execution_mode,
            payload={"error": message},
        )
    )
    pipeline_stages = build_pipeline_stages(
        {**artifacts, "error": message},
        request.analysis_type.replace("-", "_"),
    )
    failed_artifacts = {**artifacts, "error": message}
    failed_artifacts.update(build_pipeline_stage_artifacts(pipeline_stages))
    return FixtureDealRunResult(
        run_id=run_id,
        analysis_type=request.analysis_type.replace("-", "_"),
        status="failed",
        events_url=f"/api/v1/harness/runs/{run_id}/events",
        report_id=str(report_id),
        evidence_ids=[],
        verification_status="failed",
        source_mode=request.source_mode,
        preliminary=True,
        events=events,
        tool_calls=tool_calls,
        artifacts=failed_artifacts,
        pipeline_stages=pipeline_stages,
    )


def _append_warning(artifacts: JsonObject, message: str) -> None:
    warnings = artifacts.setdefault("warnings", [])
    if isinstance(warnings, list):
        warnings.append(message)


def _county_name(value: str) -> str:
    cleaned = value.strip()
    return cleaned or "Unknown"


def _tool_call_from_result(result: HarnessToolCallResult) -> ToolCall:
    return ToolCall(
        tool_call_id=result.tool_call_id,
        run_id=result.run_id,
        event_id=result.events[0].event_id if result.events else None,
        tool_name=result.tool_name,
        args=result.args,
        result_summary=_tool_result_summary(result),
        result_payload=result.payload,
        status=result.status.value,
        permission_decision=result.policy_decision.model_dump(mode="json"),
        started_at=_tool_event_time(result, PlotLotEventType.TOOL_STARTED),
        completed_at=result.events[-1].created_at if result.events else datetime.now(timezone.utc),
        error=result.error,
        linked_evidence_ids=[EvidenceId(value) for value in result.evidence_ids],
    )


def _tool_event_time(
    result: HarnessToolCallResult,
    event_type: PlotLotEventType,
) -> datetime | None:
    for event in result.events:
        if event.type == event_type:
            return event.created_at
    return None


def _tool_result_summary(result: HarnessToolCallResult) -> str:
    if result.error is not None:
        return result.error.message
    return f"{result.tool_name} {result.status.value}"
