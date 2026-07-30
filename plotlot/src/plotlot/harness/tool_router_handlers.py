from __future__ import annotations

from dataclasses import asdict
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, TypeAlias
from uuid import NAMESPACE_URL, uuid4, uuid5

from plotlot.config import settings

from pydantic import Field

from plotlot.core.types import PropertyRecord
from plotlot.domain.types import (
    EvidenceConfidence,
    EvidenceItem,
    SourceType,
    ToolContext,
)
from plotlot.harness.calculation_runner import (
    calculation_output_json,
    execute_underwriting_calculation,
)
from plotlot.harness.browser_comp_capture import (
    BrowserCompCaptureSubject,
    capture_public_listing_comps,
)
from plotlot.harness.contracts import CountyName, GISSiteContext, JsonObject, ReportId, SourceMode
from plotlot.harness.contracts.base import HarnessContract
from plotlot.harness.comparable_listing_search import (
    build_comparable_listing_queries,
    comparable_listing_query_plan,
    listing_query_should_stop,
    normalize_listing_candidates,
    rank_listing_candidates,
)
from plotlot.harness.default_runtime import (
    _handle_create_document as runtime_handle_create_document,
    _handle_create_spreadsheet as runtime_handle_create_spreadsheet,
    _handle_discover_open_data_layers as runtime_handle_discover_open_data_layers,
    _handle_export_dataset as runtime_handle_export_dataset,
    _handle_filter_dataset as runtime_handle_filter_dataset,
    _handle_get_dataset_info as runtime_handle_get_dataset_info,
    _handle_generate_document as runtime_handle_generate_document,
    _handle_geocode_address as runtime_handle_geocode_address,
    _handle_lookup_property_info as runtime_handle_lookup_property_info,
    _handle_search_properties as runtime_handle_search_properties,
    _handle_search_municode_live as runtime_handle_search_municode_live,
    _handle_search_zoning_ordinance as runtime_handle_search_zoning_ordinance,
)
from plotlot.harness.fixture_runs import (
    FixtureDealRunRequest,
    _has_direct_land_comp_signal,
    run_deal_analysis_async,
)
from plotlot.harness.fixture_site_data import (
    fixture_comp_analysis,
    fixture_site_profile_for_address,
)
from plotlot.harness.municode_source import (
    extract_ordinance_rules,
    get_municode_section,
    search_municode,
)
from plotlot.harness.rental_market_evidence import (
    RentalMarketEvidenceRequest,
    resolve_rental_market_evidence,
)
from plotlot.harness.report_export import (
    ReportArtifactExportRequest,
    ReportExportFormat,
    export_report_artifact,
)
from plotlot.harness.south_florida_gis import (
    classify_gis_applicability,
    get_gis_source_metadata,
    query_gis_feature_service_async,
    resolve_site_boundary_context,
    search_south_florida_gis,
)
from plotlot.harness.training_ingestion import discover_training_video_sources
from plotlot.harness.underwriting_profiles import (
    UnderwritingMarketProfileRequest,
    resolve_underwriting_market_profile,
)
from plotlot.harness.web_lookup import (
    WebLookupStatus,
    WebSearchProvider,
    execute_web_contents,
    execute_web_search,
    web_contents_payload,
    web_search_payload,
)
from plotlot.land_use.citations import county_record_citation
from plotlot.pipeline.comps import find_comparables

if TYPE_CHECKING:
    from plotlot.harness.tool_router import HarnessToolCallRequest

ToolHandler: TypeAlias = Callable[["HarnessToolCallRequest"], Awaitable[JsonObject]]


class MunicodeSearchArgs(HarnessContract):
    jurisdiction: str = Field(min_length=1)
    query: str = Field(min_length=1)


class MunicodeSectionArgs(HarnessContract):
    section_id: str = Field(min_length=1)


class GISSearchArgs(HarnessContract):
    query: str = Field(min_length=1)
    county: str | None = Field(default=None, min_length=1)


class GISSourceArgs(HarnessContract):
    source_id: str = Field(min_length=1)


class GISQueryArgs(HarnessContract):
    source_id: str = Field(min_length=1)
    where: str = Field(min_length=1)
    limit: int = Field(default=5, ge=1, le=100)


class GISApplicabilityArgs(HarnessContract):
    source_id: str = Field(min_length=1)
    county: str = Field(min_length=1)
    municipality: str | None = None
    is_unincorporated_or_bmsd: bool | None = None


class GISBoundaryContextArgs(HarnessContract):
    county: str = Field(min_length=1)
    municipality: str | None = None


class FindComparablesArgs(HarnessContract):
    county: str = Field(min_length=1)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    address: str | None = None
    state: str = Field(default="FL", min_length=2, max_length=32)
    municipality: str | None = None
    zoning_code: str | None = None
    land_use_code: str | None = None
    land_use_description: str | None = None
    lot_size_sqft: float = Field(default=0.0, ge=0.0)
    living_units: int = Field(default=0, ge=0)
    radius_miles: float = Field(default=3.0, gt=0.0, le=25.0)
    months: int = Field(default=12, ge=1, le=60)
    max_comps: int = Field(default=5, ge=1, le=25)


class TrainingDiscoverArgs(HarnessContract):
    url: str | None = None
    category: str | None = None


class ExportReportArgs(HarnessContract):
    report_id: str = Field(min_length=1)
    export_format: ReportExportFormat = ReportExportFormat.MARKDOWN


class WebSearchArgs(HarnessContract):
    query: str = Field(min_length=1)


class WebContentsArgs(HarnessContract):
    urls: list[str] = Field(min_length=1, max_length=5)


class BrowserCompCaptureArgs(HarnessContract):
    address: str = Field(min_length=3)
    county: str = Field(min_length=1)
    municipality: str | None = None
    state: str = Field(default="FL", min_length=2, max_length=2)
    lot_size_sqft: float = Field(default=0.0, ge=0.0)
    zoning_code: str | None = None


def default_tool_handlers() -> dict[str, ToolHandler]:
    return {
        "geocode_address": _delegate_runtime_handler(runtime_handle_geocode_address),
        "lookup_property_info": _delegate_runtime_handler(runtime_handle_lookup_property_info),
        "search_zoning_ordinance": _delegate_runtime_handler(
            runtime_handle_search_zoning_ordinance
        ),
        "search_municode_live": _delegate_runtime_handler(runtime_handle_search_municode_live),
        "run_deal_analysis": _handle_run_deal_analysis,
        "discover_open_data_layers": _delegate_runtime_handler(
            runtime_handle_discover_open_data_layers
        ),
        "search_municode": _handle_search_municode,
        "get_municode_section": _handle_get_municode_section,
        "extract_ordinance_rules": _handle_extract_ordinance_rules,
        "search_south_florida_gis": _handle_search_south_florida_gis,
        "get_gis_source_metadata": _handle_get_gis_source_metadata,
        "query_gis_feature_service": _handle_query_gis_feature_service,
        "classify_gis_applicability": _handle_classify_gis_applicability,
        "resolve_site_boundary_context": _handle_resolve_site_boundary_context,
        "find_comparables": _handle_find_comparables,
        "load_rental_market_evidence": _handle_load_rental_market_evidence,
        "load_underwriting_market_profile": _handle_load_underwriting_market_profile,
        "discover_rehabvaluator_video_sections": _handle_training_discovery,
        "web_search": _handle_web_search,
        "fetch_web_contents": _handle_fetch_web_contents,
        "capture_public_listing_comps": _handle_capture_public_listing_comps,
        "compute_feasibility": _calculator_handler("feasibility"),
        "run_noi_valuation": _calculator_handler("noi-valuation"),
        "run_pro_forma": _calculator_handler("pro-forma"),
        "run_residual_land_value": _calculator_handler("residual-land-value"),
        "run_brrrr_refinance_analysis": _calculator_handler("brrrr"),
        "run_sensitivity_analysis": _calculator_handler("sensitivity"),
        "create_construction_budget": _calculator_handler("construction-budget"),
        "generate_document": _delegate_runtime_handler(runtime_handle_generate_document),
        "search_properties": _delegate_runtime_handler(runtime_handle_search_properties),
        "filter_dataset": _delegate_runtime_handler(runtime_handle_filter_dataset),
        "get_dataset_info": _delegate_runtime_handler(runtime_handle_get_dataset_info),
        "create_spreadsheet": _delegate_runtime_handler(runtime_handle_create_spreadsheet),
        "create_document": _delegate_runtime_handler(runtime_handle_create_document),
        "export_dataset": _delegate_runtime_handler(runtime_handle_export_dataset),
        "export_report": _handle_export_report,
    }


async def _handle_search_municode(request: HarnessToolCallRequest) -> JsonObject:
    args = MunicodeSearchArgs.model_validate(request.args)
    results = search_municode(
        jurisdiction=args.jurisdiction,
        query=args.query,
        source_mode=request.source_mode,
    )
    return {"results": [item.model_dump(mode="json") for item in results]}


async def _handle_get_municode_section(request: HarnessToolCallRequest) -> JsonObject:
    args = MunicodeSectionArgs.model_validate(request.args)
    section = get_municode_section(args.section_id, source_mode=request.source_mode)
    return {"section": section.model_dump(mode="json")}


async def _handle_extract_ordinance_rules(request: HarnessToolCallRequest) -> JsonObject:
    args = MunicodeSectionArgs.model_validate(request.args)
    section = get_municode_section(args.section_id, source_mode=request.source_mode)
    return extract_ordinance_rules(section).model_dump(mode="json")


async def _handle_search_south_florida_gis(request: HarnessToolCallRequest) -> JsonObject:
    args = GISSearchArgs.model_validate(request.args)
    county = CountyName(args.county) if args.county else None
    results = search_south_florida_gis(
        args.query,
        county=county,
        source_mode=request.source_mode,
    )
    return {"results": [item.model_dump(mode="json") for item in results]}


async def _handle_get_gis_source_metadata(request: HarnessToolCallRequest) -> JsonObject:
    args = GISSourceArgs.model_validate(request.args)
    source = get_gis_source_metadata(args.source_id, source_mode=request.source_mode)
    return {"source": source.model_dump(mode="json")}


async def _handle_query_gis_feature_service(request: HarnessToolCallRequest) -> JsonObject:
    args = GISQueryArgs.model_validate(request.args)
    result = await query_gis_feature_service_async(
        args.source_id,
        where=args.where,
        limit=args.limit,
        source_mode=request.source_mode,
    )
    return result.model_dump(mode="json")


async def _handle_classify_gis_applicability(request: HarnessToolCallRequest) -> JsonObject:
    args = GISApplicabilityArgs.model_validate(request.args)
    source = get_gis_source_metadata(args.source_id, source_mode=request.source_mode)
    result = classify_gis_applicability(
        source,
        GISSiteContext(
            county=CountyName(args.county),
            municipality=args.municipality,
            is_unincorporated_or_bmsd=args.is_unincorporated_or_bmsd,
        ),
    )
    return result.model_dump(mode="json")


async def _handle_resolve_site_boundary_context(request: HarnessToolCallRequest) -> JsonObject:
    args = GISBoundaryContextArgs.model_validate(request.args)
    return resolve_site_boundary_context(
        county=CountyName(args.county),
        municipality=args.municipality,
        source_mode=request.source_mode,
    )


async def _handle_find_comparables(request: HarnessToolCallRequest) -> JsonObject:
    args = FindComparablesArgs.model_validate(request.args)
    subject = PropertyRecord(
        address=(args.address or "").strip(),
        municipality=(args.municipality or "").strip(),
        county=args.county.strip(),
        zoning_code=(args.zoning_code or "").strip(),
        land_use_code=(args.land_use_code or "").strip(),
        land_use_description=(args.land_use_description or "").strip(),
        lot_size_sqft=args.lot_size_sqft,
        living_units=args.living_units,
        lat=args.lat,
        lng=args.lng,
    )
    if request.source_mode is SourceMode.FIXTURE and _is_fixture_comps_subject(args):
        analysis = fixture_comp_analysis(
            fixture_site_profile_for_address(args.address or args.county)
        )
    else:
        analysis = await find_comparables(
            subject,
            state=args.state,
            radius_miles=args.radius_miles,
            months=args.months,
            max_comps=args.max_comps,
        )
    payload: JsonObject = {
        "subject": {
            "address": subject.address,
            "municipality": subject.municipality,
            "county": subject.county,
            "state": args.state.upper(),
            "lat": subject.lat,
            "lng": subject.lng,
            "zoning_code": subject.zoning_code,
            "land_use_code": subject.land_use_code,
            "land_use_description": subject.land_use_description,
            "lot_size_sqft": subject.lot_size_sqft,
            "living_units": subject.living_units,
        },
        "analysis": asdict(analysis),
    }
    payload = await _enrich_comparables_with_web_candidates(
        payload,
        request=request,
        args=args,
    )
    return _enrich_comparables_payload(payload, request=request)


async def _handle_load_rental_market_evidence(request: HarnessToolCallRequest) -> JsonObject:
    args = RentalMarketEvidenceRequest.model_validate(request.args)
    evidence_payload = resolve_rental_market_evidence(
        state=args.state,
        county=args.county,
        municipality=args.municipality,
        assumptions=args.assumptions,
    )
    evidence = {
        "evidence_id": f"ev_rental_profile_{request.context.run_id}",
        "tool_name": "load_rental_market_evidence",
        "source_type": "cost_assumption_config",
        "source_name": f"{evidence_payload['market']} rental market evidence",
        "source_url": f"https://plotlot.local/cost-model/{evidence_payload['source']}",
        "source_identifier": str(evidence_payload["source"]),
        "county": args.county,
        "municipality": args.municipality,
        "state": args.state,
        "structured_payload": evidence_payload,
    }
    return {"rental_market_evidence": evidence_payload, "evidence": [evidence]}


async def _handle_load_underwriting_market_profile(request: HarnessToolCallRequest) -> JsonObject:
    args = UnderwritingMarketProfileRequest.model_validate(request.args)
    profile = resolve_underwriting_market_profile(
        state=args.state,
        county=args.county,
        municipality=args.municipality,
        assumptions=args.assumptions,
    )
    rental_market_evidence = profile.get("rental_market_evidence", {})
    evidence = {
        "evidence_id": f"ev_profile_{request.context.run_id}",
        "tool_name": "load_underwriting_market_profile",
        "source_type": "cost_assumption_config",
        "source_name": f"{profile['market']} underwriting market profile",
        "source_url": f"https://plotlot.local/cost-model/{profile['source']}",
        "source_identifier": str(profile["source"]),
        "county": args.county,
        "municipality": args.municipality,
        "state": args.state,
        "structured_payload": profile,
    }
    rental_evidence = {
        "evidence_id": f"ev_rental_profile_{request.context.run_id}",
        "tool_name": "load_rental_market_evidence",
        "source_type": "cost_assumption_config",
        "source_name": f"{profile['market']} rental market evidence",
        "source_url": f"https://plotlot.local/cost-model/{profile['source']}",
        "source_identifier": str(profile["source"]),
        "county": args.county,
        "municipality": args.municipality,
        "state": args.state,
        "structured_payload": rental_market_evidence,
    }
    return {
        "profile": profile,
        "rental_market_evidence": rental_market_evidence,
        "evidence": [evidence, rental_evidence],
    }


async def _handle_training_discovery(request: HarnessToolCallRequest) -> JsonObject:
    args = TrainingDiscoverArgs.model_validate(request.args)
    videos = discover_training_video_sources(
        source_mode=request.source_mode,
        url=args.url,
        category=args.category,
    )
    return {"videos": [video.model_dump(mode="json") for video in videos]}


async def _handle_web_search(request: HarnessToolCallRequest) -> JsonObject:
    args = WebSearchArgs.model_validate(request.args)
    result = await execute_web_search(
        args.query,
        provider=WebSearchProvider.EXA,
        exa_api_key=settings.exa_api_key,
    )
    return web_search_payload(result, query=args.query, context=request.context)


async def _handle_fetch_web_contents(request: HarnessToolCallRequest) -> JsonObject:
    args = WebContentsArgs.model_validate(request.args)
    result = await execute_web_contents(
        list(args.urls),
        provider=WebSearchProvider.EXA,
        exa_api_key=settings.exa_api_key,
    )
    return web_contents_payload(
        result,
        urls=list(args.urls),
        context=request.context,
    )


async def _handle_capture_public_listing_comps(request: HarnessToolCallRequest) -> JsonObject:
    args = BrowserCompCaptureArgs.model_validate(request.args)
    result = capture_public_listing_comps(
        BrowserCompCaptureSubject(
            address=args.address,
            county=args.county,
            municipality=args.municipality,
            state=args.state,
            lot_size_sqft=args.lot_size_sqft,
            zoning_code=args.zoning_code,
        ),
        source_mode=request.source_mode,
    )
    payload = dict(result.payload)
    raw_candidates = payload.get("candidates")
    if not isinstance(raw_candidates, list):
        return payload
    payload["evidence"] = [
        {
            "evidence_id": f"ev_browser_capture_{request.context.run_id}_{index + 1}",
            "tool_name": "capture_public_listing_comps",
            "source_type": "web_page",
            "source_name": str(candidate.get("title") or f"Browser comp candidate #{index + 1}"),
            "source_url": str(candidate.get("url") or ""),
            "source_identifier": str(candidate.get("address_hint") or candidate.get("url") or ""),
            "county": args.county,
            "municipality": args.municipality,
            "state": args.state,
            "structured_payload": candidate,
        }
        for index, candidate in enumerate(raw_candidates)
        if isinstance(candidate, dict)
    ]
    return payload


async def _handle_run_deal_analysis(request: HarnessToolCallRequest) -> JsonObject:
    run_request = FixtureDealRunRequest.model_validate(
        {
            "address": request.args.get("address", ""),
            "analysis_type": request.args.get("analysis_type")
            or request.args.get("analysisType")
            or "acquisition_memo",
            "source_mode": request.source_mode,
            "execution_mode": request.execution_mode,
            "assumptions": request.args.get("assumptions") or {},
            "workspace_id": request.context.workspace_id,
            "project_id": request.context.project_id,
            "site_id": request.context.site_id,
            "analysis_id": request.context.analysis_id,
        }
    )
    result = await run_deal_analysis_async(run_request)
    return result.model_dump(mode="json")


async def _handle_export_report(request: HarnessToolCallRequest) -> JsonObject:
    args = ExportReportArgs.model_validate(request.args)
    export = export_report_artifact(
        ReportArtifactExportRequest(
            report_id=ReportId(args.report_id),
            export_format=args.export_format,
        )
    )
    return {"export": export.model_dump(mode="json")}


def _calculator_handler(command: str) -> ToolHandler:
    async def handle(request: HarnessToolCallRequest) -> JsonObject:
        return calculation_output_json(execute_underwriting_calculation(command, request.args))

    return handle


def _delegate_runtime_handler(
    handler: Callable[[dict[str, Any], ToolContext], Awaitable[dict[str, Any]]],
) -> ToolHandler:
    async def delegated(request: HarnessToolCallRequest) -> JsonObject:
        return await handler(dict(request.args), request.context)

    return delegated


def _enrich_comparables_payload(
    payload: JsonObject,
    *,
    request: HarnessToolCallRequest,
) -> JsonObject:
    subject_payload = payload.get("subject")
    analysis_payload = payload.get("analysis")
    if not isinstance(subject_payload, dict) or not isinstance(analysis_payload, dict):
        return payload

    all_comp_lists: list[tuple[str, object]] = [
        ("comparables", analysis_payload.get("comparables")),
        ("unit_comparables", analysis_payload.get("unit_comparables")),
    ]
    evidence_payloads: list[JsonObject] = []
    for claim_key, comp_items in all_comp_lists:
        if not isinstance(comp_items, list):
            continue
        for position, comp in enumerate(comp_items):
            if not isinstance(comp, dict):
                continue
            evidence_id = str(uuid4())
            citation = county_record_citation(
                title=_comp_citation_title(subject_payload.get("county"), claim_key, position),
                url=None,
                jurisdiction=_string_or_none(subject_payload.get("county")),
                publisher="County recorder / property appraiser open data",
                raw_text_for_hash=(
                    f"{subject_payload.get('county')}|{claim_key}|{position}|"
                    f"{comp.get('address')}|{comp.get('sale_date')}|{comp.get('sale_price')}"
                ),
            )
            evidence = EvidenceItem(
                id=evidence_id,
                workspace_id=request.context.workspace_id,
                project_id=_project_id_for_context(request),
                site_id=request.context.site_id,
                analysis_id=request.context.analysis_id,
                analysis_run_id=request.context.analysis_run_id,
                tool_run_id=request.context.tool_run_id,
                claim_key=f"market_comps.{claim_key}",
                payload={
                    "subject": subject_payload,
                    "comp_type": claim_key,
                    "position": position,
                    **comp,
                },
                source_type=SourceType.COUNTY_RECORD,
                tool_name="find_comparables",
                confidence=EvidenceConfidence.MEDIUM,
                citation=citation,
            )
            comp["evidence_id"] = evidence_id
            comp["citation"] = citation.model_dump(mode="json")
            evidence_payloads.append(evidence.model_dump(mode="json"))

    if evidence_payloads:
        existing_evidence = payload.get("evidence")
        merged_evidence = list(existing_evidence) if isinstance(existing_evidence, list) else []
        merged_evidence.extend(evidence_payloads)
        payload["evidence"] = merged_evidence
    return payload


async def _enrich_comparables_with_web_candidates(
    payload: JsonObject,
    *,
    request: HarnessToolCallRequest,
    args: FindComparablesArgs,
) -> JsonObject:
    analysis_payload = payload.get("analysis")
    subject_payload = payload.get("subject")
    if not isinstance(analysis_payload, dict) or not isinstance(subject_payload, dict):
        return payload
    if request.source_mode is not SourceMode.LIVE:
        return payload
    if not args.address:
        return payload
    if _has_direct_land_comp_signal(analysis_payload):
        return payload
    aggregated_candidates: list[JsonObject] = []
    query_attempts: list[JsonObject] = []
    query_plan_entries = comparable_listing_query_plan(subject_payload)
    if not settings.exa_api_key:
        analysis_payload["web_listing_candidates"] = []
        analysis_payload["web_listing_search"] = _web_listing_search_payload(
            query_plan_entries=query_plan_entries,
            query_attempts=[],
            aggregated_candidates=[],
            selected_attempt=None,
            status="skipped_missing_exa_api_key",
        )
        return payload
    evidence_payload = payload.get("evidence")
    merged_evidence = list(evidence_payload) if isinstance(evidence_payload, list) else []
    for query_plan in build_comparable_listing_queries(subject_payload):
        result = await execute_web_search(
            query_plan.query,
            provider=WebSearchProvider.EXA,
            exa_api_key=settings.exa_api_key,
        )
        if result.status is not WebLookupStatus.SUCCESS or not result.results:
            query_attempts.append(
                {
                    "query": query_plan.query,
                    "purpose": query_plan.purpose,
                    "search_category": query_plan.search_category,
                    "search_window_months": query_plan.window_months,
                    "stop_rule": query_plan.stop_rule,
                    "status": result.status.value,
                    "result_count": 0,
                    "land_candidate_count": 0,
                    "improved_candidate_count": 0,
                }
            )
            continue
        search_payload = web_search_payload(result, query=query_plan.query, context=request.context)
        results_payload = search_payload.get("results")
        if not isinstance(results_payload, list) or not results_payload:
            query_attempts.append(
                {
                    "query": query_plan.query,
                    "purpose": query_plan.purpose,
                    "search_category": query_plan.search_category,
                    "search_window_months": query_plan.window_months,
                    "stop_rule": query_plan.stop_rule,
                    "status": WebLookupStatus.SUCCESS.value,
                    "result_count": 0,
                    "land_candidate_count": 0,
                    "improved_candidate_count": 0,
                }
            )
            continue
        query_candidates = normalize_listing_candidates(
            results_payload,
            query=query_plan,
            subject_payload=subject_payload,
        )
        land_candidate_count = len(
            [
                candidate
                for candidate in query_candidates
                if candidate.get("classification") == "likely_vacant_land"
            ]
        )
        improved_candidate_count = len(
            [
                candidate
                for candidate in query_candidates
                if candidate.get("classification") == "likely_improved_sale"
            ]
        )
        query_attempts.append(
            {
                "query": query_plan.query,
                "purpose": query_plan.purpose,
                "search_category": query_plan.search_category,
                "search_window_months": query_plan.window_months,
                "stop_rule": query_plan.stop_rule,
                "status": str(search_payload.get("status") or WebLookupStatus.SUCCESS.value),
                "result_count": len(results_payload),
                "land_candidate_count": land_candidate_count,
                "improved_candidate_count": improved_candidate_count,
            }
        )
        aggregated_candidates.extend(query_candidates)
        aggregated_candidates = rank_listing_candidates(aggregated_candidates)
        web_evidence = search_payload.get("evidence")
        if isinstance(web_evidence, list) and web_evidence:
            merged_evidence.extend(web_evidence)
        if listing_query_should_stop(aggregated_candidates, query=query_plan):
            break
    selected_attempt = next(
        (
            attempt
            for attempt in query_attempts
            if int(attempt.get("land_candidate_count") or 0) > 0
            or int(attempt.get("improved_candidate_count") or 0) > 0
        ),
        None,
    )
    analysis_payload["web_listing_candidates"] = aggregated_candidates
    analysis_payload["web_listing_search"] = _web_listing_search_payload(
        query_plan_entries=query_plan_entries,
        query_attempts=query_attempts,
        aggregated_candidates=aggregated_candidates,
        selected_attempt=selected_attempt,
        status="no_usable_listing_candidates" if selected_attempt is None else "",
    )
    if merged_evidence:
        payload["evidence"] = merged_evidence
    return payload


def _web_listing_search_payload(
    *,
    query_plan_entries: list[JsonObject],
    query_attempts: list[JsonObject],
    aggregated_candidates: list[JsonObject],
    selected_attempt: JsonObject | None,
    status: str,
) -> JsonObject:
    return {
        "provider": WebSearchProvider.EXA.value,
        "provider_policy": "exa_only",
        "strategy": "sold_land_then_improved_sales",
        "query_plan": query_plan_entries,
        "query": selected_attempt.get("query") if isinstance(selected_attempt, dict) else "",
        "selected_purpose": selected_attempt.get("purpose")
        if isinstance(selected_attempt, dict)
        else "",
        "status": status
        or (selected_attempt.get("status") if isinstance(selected_attempt, dict) else ""),
        "result_count": len(aggregated_candidates),
        "land_candidate_count": len(
            [
                candidate
                for candidate in aggregated_candidates
                if candidate.get("classification") == "likely_vacant_land"
            ]
        ),
        "improved_candidate_count": len(
            [
                candidate
                for candidate in aggregated_candidates
                if candidate.get("classification") == "likely_improved_sale"
            ]
        ),
        "selected_search_category": (
            selected_attempt.get("search_category") if isinstance(selected_attempt, dict) else ""
        ),
        "selected_search_window_months": (
            selected_attempt.get("search_window_months")
            if isinstance(selected_attempt, dict)
            else None
        ),
        "attempts": query_attempts,
    }


def _project_id_for_context(request: HarnessToolCallRequest) -> str:
    if request.context.project_id:
        return request.context.project_id
    return str(
        uuid5(
            NAMESPACE_URL,
            f"plotlot:{request.context.workspace_id}:default_project",
        )
    )


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _comp_citation_title(county: object, claim_key: str, position: int) -> str:
    county_label = _string_or_none(county) or "County"
    comp_type = "unit sale comp" if claim_key == "unit_comparables" else "land sale comp"
    return f"{county_label} {comp_type} #{position + 1}"


def _is_fixture_comps_subject(args: FindComparablesArgs) -> bool:
    if args.address is not None and "fixture" in args.address.casefold():
        return True
    if args.address is not None and "45 nw 209" in args.address.casefold():
        return True
    return "fixture" in args.county.casefold()
